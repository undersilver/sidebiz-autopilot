from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / "config/settings.json").read_text(encoding="utf-8"))
SEEDS = json.loads((ROOT / "config/topic_seeds.json").read_text(encoding="utf-8"))
CONTEXT = (ROOT / "config/context.md").read_text(encoding="utf-8")

API_URL = "https://models.github.ai/inference/chat/completions"


def choose_seed() -> dict:
    history_file = ROOT / "data/history.json"
    history = []
    if history_file.exists():
        history = json.loads(history_file.read_text(encoding="utf-8"))

    used = {item.get("title") for item in history[-30:]}
    candidates = [seed for seed in SEEDS if seed["title"] not in used] or SEEDS
    return random.choice(candidates)


def build_prompt(seed: dict) -> str:
    return f"""
あなたはゲーム制作・AI活用メディアの編集長です。
次のコンテキストとテーマを使い、日本語の公開候補を1件だけ作成してください。

{CONTEXT}

テーマ：{seed['title']}
カテゴリー：{seed['category']}
独自の切り口：{seed['original_angle']}

制約：
- 読者はAIやゲーム制作に興味がある初心者から中級者
- 誇大な収益表現をしない
- 実在ゲーム、キャラクター、ブランドの権利を侵害しない
- 不明な事実を断定しない
- 外部情報が必要な箇所は「要出典」と明記する
- 本人の確認時間が10分以内になるよう、確認項目は最大5件
- マスコット「ピコロン」を自然に1回だけ登場させる
- 記事は1,200〜1,800字程度
- SNS文は140字程度
- ショート動画台本は45〜60秒
- JSONだけを返す

JSON形式：
{{
  "title": "...",
  "slug": "半角英数字とハイフン",
  "category": "...",
  "summary": "...",
  "article_markdown": "...",
  "social_post": "...",
  "short_video_script": "...",
  "thumbnail_prompt": "...",
  "human_checks": [
    {{"type": "画像", "item": "...", "risk": "低|中|高"}}
  ],
  "sources_needed": ["..."],
  "affiliate_candidates": ["..."],
  "quality_score": 0,
  "estimated_review_minutes": 0
}}
""".strip()


def call_model(prompt: str) -> dict:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN がありません")

    payload = {
        "model": SETTINGS["model"],
        "messages": [
            {"role": "system", "content": "必ず有効なJSONだけを返してください。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 3500,
    }
    response = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    content = re.sub(r"^```json\s*|\s*```$", "", content.strip(), flags=re.S)
    return json.loads(content)


def fallback(seed: dict, error: Exception) -> dict:
    slug = datetime.now().strftime("%Y-%m-%d-fallback")
    return {
        "title": seed["title"],
        "slug": slug,
        "category": seed["category"],
        "summary": "AI生成に失敗したため、確認用テンプレートを作成しました。",
        "article_markdown": f"""# {seed['title']}

## 今回の目的

{seed['original_angle']}

## 検証すること

- 問題の整理
- AIへの指示方法
- 改善前後の比較
- 初心者が再現できる手順

## ピコロンのメモ

このテーマは下書き生成に失敗しました。次回ワークフローで再生成してください。

## エラー情報

`{type(error).__name__}: {error}`
""",
        "social_post": f"{seed['title']}を検証予定です。AIとゲーム制作の実践記録として公開します。",
        "short_video_script": "今回は生成エラーのため、動画台本は保留です。",
        "thumbnail_prompt": "マスコットのピコロンが設計図を確認している、オリジナルのゲーム研究所、文字なし",
        "human_checks": [
            {"type": "システム", "item": "AI生成エラーのため再生成が必要", "risk": "高"}
        ],
        "sources_needed": [],
        "affiliate_candidates": [],
        "quality_score": 20,
        "estimated_review_minutes": 2,
    }


def save_draft(data: dict, seed: dict) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    draft_dir = ROOT / "drafts"
    draft_dir.mkdir(exist_ok=True)
    path = draft_dir / f"{today}-{data['slug']}.json"
    data["_meta"] = {
        "created_at": datetime.now().isoformat(),
        "seed": seed,
        "status": "review",
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
        print("GitHub環境外のためIssue作成をスキップ")
        return

    checks = "\n".join(
        f"- [{c['risk']}] **{c['type']}**：{c['item']}" for c in data.get("human_checks", [])
    ) or "- なし"

    sources = "\n".join(f"- {s}" for s in data.get("sources_needed", [])) or "- なし"
    body = f"""## 本日の公開候補

**タイトル**：{data['title']}

**カテゴリー**：{data['category']}

**概要**：{data['summary']}

**品質スコア**：{data['quality_score']} / 100

**推定確認時間**：{data['estimated_review_minutes']}分

### 人間が確認する項目

{checks}

### 出典が必要な項目

{sources}

### SNS投稿案

{data['social_post']}

### ショート動画台本

{data['short_video_script']}

### サムネイル生成指示

{data['thumbnail_prompt']}

### 下書きファイル

`{draft_path.relative_to(ROOT)}`

---

問題なければ `approve` ラベルを追加してください。
修正が必要ならコメントを書いて `needs-fix` を追加してください。
公開しない場合は `reject` を追加してください。
"""
    response = requests.post(
        f"https://api.github.com/repos/{repo}/issues",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={
            "title": f"【確認】{data['title']}",
            "body": body,
            "labels": ["review"],
        },
        timeout=60,
    )
    response.raise_for_status()


def main() -> None:
    seed = choose_seed()
    try:
        data = call_model(build_prompt(seed))
    except Exception as exc:
        print(f"AI生成失敗: {exc}")
        data = fallback(seed, exc)

    draft_path = save_draft(data, seed)
    create_issue(data, draft_path)
    print(f"作成完了: {draft_path}")


if __name__ == "__main__":
    main()
