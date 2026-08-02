from __future__ import annotations

import json
import os
import random
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from content_utils import format_pikoron_tips_for_issue, normalize_pikoron_tips
from gemini_client import call_json_model

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / "config/settings.json").read_text(encoding="utf-8"))
SEEDS = json.loads((ROOT / "config/topic_seeds.json").read_text(encoding="utf-8"))
CONTEXT = (ROOT / "config/context.md").read_text(encoding="utf-8")

def now_local() -> datetime:
    return datetime.now(ZoneInfo(SETTINGS.get("timezone", "Asia/Tokyo")))


def choose_seed() -> dict:
    history_file = ROOT / "data/history.json"
    history = json.loads(history_file.read_text(encoding="utf-8")) if history_file.exists() else []
    used = {item.get("title") for item in history[-30:]}
    candidates = [seed for seed in SEEDS if seed["title"] not in used] or SEEDS
    return random.choice(candidates)


def call_model(messages: list[dict], temperature: float = 0.4, max_tokens: int = 4000) -> dict:
    return call_json_model(
        messages=messages,
        model=SETTINGS["model"],
        temperature=temperature,
        max_tokens=max_tokens,
    )


def build_writer_prompt(seed: dict) -> str:
    return f"""
あなたは一般読者向けWebメディアの編集者兼ライターです。
以下の運営者コンテキストは、テーマ選定の参考にだけ使ってください。
運営者の確認時間、95％自動化、承認作業、内部チェック項目などは記事本文に絶対に書かないでください。

{CONTEXT}

テーマ：{seed['title']}
カテゴリー：{seed['category']}
独自の切り口：{seed['original_angle']}

読者：
- AIを使ったゲーム・漫画・創作に関心がある初心者〜中級者
- 実際に試せる具体的な方法を知りたい人

記事要件：
- 読者に直接役立つ内容だけを書く
- 内部運用、承認、確認時間、収益目標、自動化率は書かない
- 抽象論だけで終わらず、具体例、手順、失敗例、改善例を入れる
- 不明な事実、未検証の仕様、根拠のない数値は書かない
- 外部情報が必要な主張は本文から外すか、「要検証事項」としてJSON側にだけ記録する
- 既存作品名・キャラクター名・ブランド名は必要がない限り出さない
- マスコット「ピコロン」は記事内で0〜1回。内容に不要なら登場させない
- 1,500〜2,200字程度
- 人間の確認時間は最大{SETTINGS['max_review_minutes']}分として設計する
- ピコロンの吹き出しは、本当に重要な要点がある章だけ0〜3件にする
- 吹き出しを全章や全段落へ付けない。要点がなければ空配列にする
- after_headingはarticle_markdown内の「## 」見出しと完全に一致させる
- messageはその章の内容だけを短くまとめ、新しい事実や内部情報を追加しない
- JSONだけを返す

JSON形式：
{{
  "title": "...",
  "slug": "半角英数字とハイフン",
  "category": "...",
  "summary": "読者向けの要約",
  "article_markdown": "...",
  "social_post": "...",
  "short_video_script": "...",
  "thumbnail_prompt": "...",
  "pikoron_tips": [
    {{"after_heading": "記事内の##見出し（##を除く）", "message": "80〜120字以内の重要な要点"}}
  ],
  "human_checks": [
    {{"type": "画像|事実|権利|表現", "item": "...", "risk": "低|中|高"}}
  ],
  "sources_needed": [],
  "affiliate_candidates": [],
  "quality_score": 0,
  "estimated_review_minutes": 0
}}
""".strip()


def build_validator_prompt(draft: dict) -> str:
    return f"""
あなたは厳格な編集校閲AIです。以下の公開候補を検証してください。

検証基準：
1. 一般読者向けになっているか
2. 運営者向け内部情報（確認時間、承認作業、95％自動化、内部チェック）が本文に漏れていないか
3. 未検証の事実や根拠のない断定がないか
4. 「要出典」「今後調査が必要」など未完成表現が本文に残っていないか
5. 読者が実行できる具体性があるか
6. タイトルと本文が一致しているか
7. 既存作品・ブランド・権利侵害の懸念がないか
8. 不自然な宣伝文、過度なマスコット挿入、AIらしい冗長表現がないか
9. 同じ主張の繰り返しがないか
10. 公開可能な完成度か
11. ピコロンの吹き出しが0〜3件で、対象章の重要な要点に直接関係しているか

公開候補：
{json.dumps(draft, ensure_ascii=False)}

JSONだけを返してください。

{{
  "status": "pass|rewrite|block",
  "score": 0,
  "issues": [
    {{"severity": "low|medium|high", "category": "...", "detail": "..."}}
  ],
  "rewrite_instructions": ["..."],
  "publishable": true
}}
""".strip()


def build_rewrite_prompt(draft: dict, validation: dict) -> str:
    return f"""
あなたは編集長です。以下の原稿を、校閲結果に従って全面修正してください。

原稿：
{json.dumps(draft, ensure_ascii=False)}

校閲結果：
{json.dumps(validation, ensure_ascii=False)}

必須条件：
- 一般読者向けに統一
- 運営内部の確認時間、承認作業、95％自動化、内部チェックは本文から削除
- 未検証事項や「要出典」は本文に残さない
- 具体例と実践手順を増やす
- 不要なピコロン言及を削除
- pikoron_tipsは重要な要点だけ0〜3件とし、対象の##見出しに完全一致させる
- 元のJSON形式を維持
- JSONだけを返す
""".strip()



def normalize_validation_score(validation: dict) -> dict:
    """10点満点で返された可能性が高い採点だけを100点満点へ補正する。"""
    try:
        score = int(validation.get("score", 0))
    except (TypeError, ValueError):
        score = 0

    issues = validation.get("issues", [])
    has_high = any(
        isinstance(issue, dict) and issue.get("severity") == "high"
        for issue in issues
    )

    if (
        1 <= score <= 10
        and validation.get("status") == "pass"
        and validation.get("publishable") is True
        and not has_high
    ):
        score *= 10

    validation["score"] = max(0, min(score, 100))
    return validation


def is_publishable(draft: dict, validation: dict) -> bool:
    """公開候補Issueへ出せる条件を一か所で厳格に判定する。"""
    try:
        score = int(validation.get("score", 0))
    except (TypeError, ValueError):
        return False

    issues = validation.get("issues", [])
    has_high = any(
        isinstance(issue, dict) and issue.get("severity") == "high"
        for issue in issues
    )
    minimum = int(SETTINGS.get("validation", {}).get("minimum_score", 80))
    article = str(draft.get("article_markdown", ""))
    has_incomplete_marker = any(
        marker in article for marker in ("要出典", "今後調査が必要")
    )

    return (
        validation.get("status") == "pass"
        and validation.get("publishable") is True
        and score >= minimum
        and not has_high
        and not draft.get("sources_needed")
        and not has_incomplete_marker
    )


def validate_and_rewrite(draft: dict) -> tuple[dict, dict]:
    normalize_pikoron_tips(draft)
    validation = call_model(
        [
            {"role": "system", "content": "厳格に判定し、有効なJSONだけを返してください。scoreは必ず0〜100の整数で返してください。90点なら90と返し、9とは返さないでください。"},
            {"role": "user", "content": build_validator_prompt(draft)},
        ],
        temperature=0.1,
        max_tokens=1800,
    )
    validation = normalize_validation_score(validation)

    if validation.get("status") == "rewrite":
        draft = call_model(
            [
                {"role": "system", "content": "校閲結果に従って修正し、有効なJSONだけを返してください。"},
                {"role": "user", "content": build_rewrite_prompt(draft, validation)},
            ],
            temperature=0.3,
            max_tokens=4200,
        )
        normalize_pikoron_tips(draft)
        validation = call_model(
            [
                {"role": "system", "content": "再校閲し、有効なJSONだけを返してください。scoreは必ず0〜100の整数で返してください。90点なら90と返し、9とは返さないでください。"},
                {"role": "user", "content": build_validator_prompt(draft)},
            ],
            temperature=0.1,
            max_tokens=1800,
        )
        validation = normalize_validation_score(validation)

    return draft, validation


def fallback(seed: dict, error: Exception) -> dict:
    slug = now_local().strftime("%Y-%m-%d-fallback")
    return {
        "title": seed["title"],
        "slug": slug,
        "category": seed["category"],
        "summary": "AI生成または校閲に失敗したため、公開不可のテンプレートです。",
        "article_markdown": "# 公開保留\n\n生成または校閲に失敗しました。再生成してください。",
        "social_post": "",
        "short_video_script": "",
        "thumbnail_prompt": "",
        "pikoron_tips": [],
        "human_checks": [{"type": "システム", "item": f"{type(error).__name__}: {error}", "risk": "高"}],
        "sources_needed": [],
        "affiliate_candidates": [],
        "quality_score": 0,
        "estimated_review_minutes": 1,
        "_validation": {
            "status": "block",
            "score": 0,
            "issues": [{"severity": "high", "category": "system", "detail": str(error)}],
            "rewrite_instructions": [],
            "publishable": False,
        },
    }


def save_draft(data: dict, seed: dict) -> Path:
    now = now_local()
    today = now.strftime("%Y-%m-%d")
    maximum_review = int(SETTINGS.get("max_review_minutes", 10))
    try:
        review_minutes = int(data.get("estimated_review_minutes", maximum_review))
    except (TypeError, ValueError):
        review_minutes = maximum_review
    data["estimated_review_minutes"] = max(1, min(review_minutes, maximum_review))
    normalize_pikoron_tips(data)
    draft_dir = ROOT / "drafts"
    draft_dir.mkdir(exist_ok=True)
    path = draft_dir / f"{today}-{data['slug']}.json"
    publishable = is_publishable(data, data.get("_validation", {}))
    data["_meta"] = {
        "created_at": now.isoformat(),
        "seed": seed,
        "status": "review" if publishable else "blocked",
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    history_file = ROOT / "data/history.json"
    history_file.parent.mkdir(exist_ok=True)
    history = json.loads(history_file.read_text(encoding="utf-8")) if history_file.exists() else []
    history.append({"date": today, "title": seed["title"], "draft": str(path.relative_to(ROOT))})
    history_file.write_text(json.dumps(history[-365:], ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def create_issue(data: dict, draft_path: Path) -> None:
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        return

    validation = data.get("_validation", {})
    checks = "\n".join(
        f"- [{c['risk']}] **{c['type']}**：{c['item']}" for c in data.get("human_checks", [])
    ) or "- なし"
    issues = "\n".join(
        f"- [{i.get('severity','')}] **{i.get('category','')}**：{i.get('detail','')}"
        for i in validation.get("issues", [])
    ) or "- なし"
    pikoron_tips = format_pikoron_tips_for_issue(data)

    publishable = is_publishable(data, validation)
    label = "review" if publishable else "needs-fix"
    body = f"""## 本日の公開候補

**タイトル**：{data['title']}

**カテゴリー**：{data['category']}

**概要**：{data['summary']}

**編集校閲スコア**：{validation.get('score', 0)} / 100

**公開可否**：{"公開候補" if publishable else "公開不可・要修正"}

**推定確認時間**：{data.get('estimated_review_minutes', 0)}分

### AI校閲で検出した問題

{issues}

### 人間が確認する項目

{checks}

### SNS投稿案

{data.get('social_post', '')}

### ショート動画台本

{data.get('short_video_script', '')}

### サムネイル生成指示

{data.get('thumbnail_prompt', '')}

### ピコロンの要点吹き出し

{pikoron_tips}

### 下書きファイル

`{draft_path.relative_to(ROOT)}`

---

{"問題なければ `approve` ラベルを追加してください。" if publishable else "`approve` は付けず、修正または再生成してください。"}
"""
    response = requests.post(
        f"https://api.github.com/repos/{repo}/issues",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"title": f"【確認】{data['title']}", "body": body, "labels": [label]},
        timeout=60,
    )
    response.raise_for_status()


def main() -> None:
    seed = choose_seed()
    try:
        draft = call_model(
            [
                {"role": "system", "content": "一般読者向け記事を作り、有効なJSONだけを返してください。"},
                {"role": "user", "content": build_writer_prompt(seed)},
            ],
            temperature=0.6,
            max_tokens=4200,
        )
        draft, validation = validate_and_rewrite(draft)
        draft["quality_score"] = validation.get("score", 0)
        draft["_validation"] = validation
    except Exception as exc:
        print(f"生成または校閲失敗: {exc}")
        draft = fallback(seed, exc)

    draft_path = save_draft(draft, seed)
    create_issue(draft, draft_path)
    print(f"作成完了: {draft_path}")


if __name__ == "__main__":
    main()
