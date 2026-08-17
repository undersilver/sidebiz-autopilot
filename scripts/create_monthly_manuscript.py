from __future__ import annotations

import json
import os
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / "config/settings.json").read_text(encoding="utf-8"))


def now_local() -> datetime:
    return datetime.now(ZoneInfo(SETTINGS.get("timezone", "Asia/Tokyo")))


def previous_month(now: datetime) -> tuple[int, int]:
    if now.month == 1:
        return now.year - 1, 12
    return now.year, now.month - 1


def normalized_theme_key(data: dict) -> str:
    seed = data.get("_meta", {}).get("seed", {})
    if isinstance(seed, dict) and seed.get("title"):
        source = str(seed["title"])
    else:
        source = str(data.get("slug") or data.get("title") or "")
    return re.sub(r"[^0-9a-zA-Zぁ-んァ-ヶ一-龠]+", "", source).lower()


def collect_published(prefix: str) -> tuple[list[dict], list[dict]]:
    selected: OrderedDict[str, dict] = OrderedDict()
    duplicates: list[dict] = []
    for path in sorted((ROOT / "drafts").glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        meta = data.get("_meta", {})
        created_at = str(meta.get("created_at", ""))
        if meta.get("status") != "published" or not created_at.startswith(prefix):
            continue
        key = normalized_theme_key(data)
        if not key:
            key = path.stem
        record = {"path": path, "data": data}
        if key in selected:
            duplicates.append(record)
            continue
        selected[key] = record
    return list(selected.values()), duplicates


def build_manuscript(prefix: str, records: list[dict], duplicates: list[dict]) -> str:
    grouped: OrderedDict[str, list[dict]] = OrderedDict()
    for record in records:
        category = str(record["data"].get("category", "未分類"))
        grouped.setdefault(category, []).append(record)

    lines = [
        f"# AIゲーム制作実践記録 {prefix}",
        "",
        "> この原稿は販売前の編集用下書きです。章構成、重複、出典、権利、画像を確認するまで販売しません。",
        "",
        "## はじめに",
        "",
        "この原稿は、当月に公開した記事をテーマ別に整理したものです。"
        "同じ制作テーマから生成された記事は1件に統合し、公開記事の本文をMarkdownのまま収録しています。",
        "",
        "## 収録内容",
        "",
    ]
    for chapter_number, (category, items) in enumerate(grouped.items(), 1):
        lines.append(f"- 第{chapter_number}章 {category}（{len(items)}本）")

    lines.extend(["", "---", ""])
    article_number = 1
    for chapter_number, (category, items) in enumerate(grouped.items(), 1):
        lines.extend([f"## 第{chapter_number}章　{category}", ""])
        for record in items:
            data = record["data"]
            lines.extend(
                [
                    f"### {article_number}. {data.get('title', '無題')}",
                    "",
                    str(data.get("article_markdown", "")).strip(),
                    "",
                    "---",
                    "",
                ]
            )
            article_number += 1

    duplicate_titles = [
        str(record["data"].get("title", record["path"].stem)) for record in duplicates
    ]
    lines.extend(
        [
            "## 販売前チェック",
            "",
            "- [ ] 章のつながりと説明順を確認",
            "- [ ] 類似説明を統合",
            "- [ ] 数値・仕様・サービス名の出典を再確認",
            "- [ ] 著作権・商標・画像の利用条件を再確認",
            "- [ ] Kindle・note・PDFなど販売先の規約を確認",
            "- [ ] 表紙・目次・奥付を作成",
            "- [ ] 最終承認後にのみ販売",
            "",
            "## 自動編集記録",
            "",
            f"- 収録記事数：{len(records)}",
            f"- 重複除外数：{len(duplicates)}",
        ]
    )
    if duplicate_titles:
        lines.extend(["- 除外した重複候補：", *[f"  - {x}" for x in duplicate_titles]])
    else:
        lines.append("- 除外した重複候補：なし")
    return "\n".join(lines).rstrip() + "\n"


def github_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def upsert_issue(prefix: str, output: Path, count: int, duplicate_count: int) -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    headers = github_headers(token)
    title = f"【月次商品候補】{prefix}"
    body = f"""## 月次商品化レビュー

月次原稿を再編集しました。

- 原稿：`{output.relative_to(ROOT)}`
- 収録記事数：{count}
- 重複除外数：{duplicate_count}
- 状態：販売前の下書き

### 人間が確認する項目

- 章構成と重複
- 数値・仕様・サービス名の出典
- 著作権・商標・画像の利用条件
- 販売先の規約
- 表紙・目次・奥付

販売用の最終承認が完了するまで、外部販売や自動投稿は行いません。
"""
    response = requests.get(
        f"https://api.github.com/repos/{repo}/issues",
        headers=headers,
        params={"state": "all", "labels": "monthly-product", "per_page": 100},
        timeout=60,
    )
    response.raise_for_status()
    existing = next(
        (issue for issue in response.json() if issue.get("title") == title), None
    )
    if existing:
        update = requests.patch(
            f"https://api.github.com/repos/{repo}/issues/{existing['number']}",
            headers=headers,
            json={
                "body": body,
                "state": "open",
                "labels": ["monthly-product", "review"],
            },
            timeout=60,
        )
        update.raise_for_status()
        return
    created = requests.post(
        f"https://api.github.com/repos/{repo}/issues",
        headers=headers,
        json={
            "title": title,
            "body": body,
            "labels": ["monthly-product", "review"],
        },
        timeout=60,
    )
    created.raise_for_status()


def main() -> None:
    year, month = previous_month(now_local())
    prefix = f"{year:04d}-{month:02d}"
    records, duplicates = collect_published(prefix)
    if not records:
        print("対象記事なし")
        return
    out_dir = ROOT / "products/monthly"
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{prefix}-manuscript.md"
    output.write_text(
        build_manuscript(prefix, records, duplicates),
        encoding="utf-8",
    )
    upsert_issue(prefix, output, len(records), len(duplicates))
    print(f"月次原稿: {output.relative_to(ROOT)}")
    print(f"収録記事数: {len(records)}")
    print(f"重複除外数: {len(duplicates)}")


if __name__ == "__main__":
    main()
