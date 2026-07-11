from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from content_utils import normalize_pikoron_tips

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / "config/settings.json").read_text(encoding="utf-8"))
THUMBNAIL_VERSION = str(SETTINGS.get("thumbnail", {}).get("cache_version", "1"))


def now_local() -> datetime:
    return datetime.now(ZoneInfo(SETTINGS.get("timezone", "Asia/Tokyo")))


def github_get(path: str):
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    response = requests.get(
        f"https://api.github.com/repos/{repo}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def github_patch(path: str, payload: dict):
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    response = requests.patch(
        f"https://api.github.com/repos/{repo}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def extract_draft_path(body: str) -> Path | None:
    match = re.search(r"`(drafts/[^`]+\.json)`", body)
    return ROOT / match.group(1) if match else None


def assert_publishable(data: dict) -> None:
    validation = data.get("_validation", {})
    if not validation.get("publishable"):
        raise RuntimeError("AI校閲で公開不可と判定されています")
    if validation.get("status") != "pass":
        raise RuntimeError("AI校閲がpassではありません")
    minimum = int(SETTINGS.get("validation", {}).get("minimum_score", 80))
    if int(validation.get("score", 0)) < minimum:
        raise RuntimeError("AI校閲スコアが80未満です")
    if any(
        isinstance(issue, dict) and issue.get("severity") == "high"
        for issue in validation.get("issues", [])
    ):
        raise RuntimeError("highリスクの問題が残っています")
    if data.get("sources_needed"):
        raise RuntimeError("未解決の出典確認項目が残っています")
    article = str(data.get("article_markdown", ""))
    markers = [marker for marker in ("要出典", "今後調査が必要") if marker in article]
    if markers:
        raise RuntimeError(f"未完成表現が本文に残っています：{', '.join(markers)}")


def escape(text: str) -> str:
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;")
        .replace(">", "&gt;").replace('"', "&quot;")
    )


def markdown_to_html(md: str) -> str:
    import markdown
    return markdown.markdown(md, extensions=["fenced_code", "tables"])


def insert_pikoron_tips(article_html: str, data: dict) -> str:
    """明示的に選ばれた章だけへピコロンの要点吹き出しを挿入する。"""
    tips = normalize_pikoron_tips(data)
    if not tips:
        return article_html

    result = article_html
    for tip in tips:
        heading_html = escape(tip["after_heading"])
        pattern = re.compile(rf'(<h2>\s*{re.escape(heading_html)}\s*</h2>)')
        aside = (
            '<aside class="pikoron-tip" aria-label="ピコロンの要点">'
            '<img class="pikoron-tip-avatar" src="../assets/pikolon.png" alt="ピコロン">'
            '<div class="pikoron-tip-bubble"><strong>ピコロンの要点</strong>'
            f'<p>{escape(tip["message"])}</p></div></aside>'
        )
        result, replaced = pattern.subn(rf'\1{aside}', result, count=1)
        if replaced != 1:
            print(f'吹き出し挿入対象の見出しが見つかりません: {tip["after_heading"]}')
    return result


def publish(draft_path: Path) -> Path:
    data = json.loads(draft_path.read_text(encoding="utf-8"))
    assert_publishable(data)

    date = data["_meta"]["created_at"][:10]
    post_dir = ROOT / "docs/posts"
    post_dir.mkdir(parents=True, exist_ok=True)
    post_path = post_dir / f"{date}-{data['slug']}.html"

    article_html = insert_pikoron_tips(markdown_to_html(data["article_markdown"]), data)
    html = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{escape(data['title'])} | {escape(SETTINGS['site_name'])}</title>
  <meta name="description" content="{escape(data['summary'])}">
  <link rel="stylesheet" href="../assets/style.css">
</head>
<body>
<header class="site-header">
  <a href="../index.html"><img src="../assets/pikolon.png" alt="ピコロン"></a>
  <div><strong>{escape(SETTINGS['site_name'])}</strong><small>{escape(SETTINGS['site_description'])}</small></div>
</header>
<main class="article">
  <p class="category">{escape(data['category'])}</p>
  <h1>{escape(data['title'])}</h1>
  <p class="lead">{escape(data['summary'])}</p>
  <img class="article-thumbnail" src="../assets/thumbnails/{date}-{data['slug']}.png?v={THUMBNAIL_VERSION}" alt="{escape(data['title'])}">
  {article_html}
  <hr>
  <p class="disclosure">{escape(SETTINGS['affiliate_disclosure'])}</p>
  <p>{escape(SETTINGS['default_cta'])}</p>
</main>
</body>
</html>"""
    post_path.write_text(html, encoding="utf-8")
    data["_meta"]["status"] = "published"
    data["_meta"]["published_at"] = now_local().isoformat()
    draft_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return post_path


def rebuild_index() -> None:
    posts = []
    for path in sorted((ROOT / "docs/posts").glob("*.html"), reverse=True):
        text = path.read_text(encoding="utf-8")
        title_match = re.search(r"<h1>(.*?)</h1>", text)
        lead_match = re.search(r'<p class="lead">(.*?)</p>', text)
        if title_match:
            posts.append({
                "path": f"posts/{path.name}",
                "title": title_match.group(1),
                "lead": lead_match.group(1) if lead_match else "",
                "thumbnail": f"assets/thumbnails/{path.stem}.png?v={THUMBNAIL_VERSION}",
            })

    cards = "\n".join(
        f'<article class="card"><a href="{p["path"]}"><img src="{p["thumbnail"]}" alt="{p["title"]}"></a><div><h2><a href="{p["path"]}">{p["title"]}</a></h2><p>{p["lead"]}</p></div></article>'
        for p in posts
    ) or '<p>最初の記事を準備中です。</p>'

    html = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{escape(SETTINGS['site_name'])}</title>
  <meta name="description" content="{escape(SETTINGS['site_description'])}">
  <link rel="stylesheet" href="assets/style.css">
</head>
<body>
<header class="hero">
  <img src="assets/pikolon.png" alt="ピコロン">
  <div>
    <p class="eyebrow">AI × GAME DEVELOPMENT</p>
    <h1>{escape(SETTINGS['site_name'])}</h1>
    <p>{escape(SETTINGS['site_description'])}</p>
  </div>
</header>
<main class="posts">{cards}</main>
<footer>{escape(SETTINGS['affiliate_disclosure'])}</footer>
</body>
</html>"""
    (ROOT / "docs/index.html").write_text(html, encoding="utf-8")


def main() -> None:
    issues = github_get("/issues?state=open&labels=approve&per_page=20")
    published = 0

    for issue in issues:
        draft_path = extract_draft_path(issue.get("body", ""))
        if not draft_path or not draft_path.exists():
            continue
        data = json.loads(draft_path.read_text(encoding="utf-8"))
        if data.get("_meta", {}).get("status") == "published":
            continue

        try:
            post_path = publish(draft_path)
        except Exception as exc:
            labels = [
                label["name"] for label in issue.get("labels", [])
                if label["name"] not in {"approve", "review"}
            ]
            if "needs-fix" not in labels:
                labels.append("needs-fix")
            github_patch(
                f"/issues/{issue['number']}",
                {
                    "body": issue["body"] + f"\n\n⚠️ 公開を停止しました：{exc}",
                    "labels": labels,
                },
            )
            continue

        github_patch(
            f"/issues/{issue['number']}",
            {
                "state": "closed",
                "body": issue["body"] + f"\n\n公開処理完了：`{post_path.relative_to(ROOT)}`",
            },
        )
        published += 1

    rebuild_index()
    print(f"公開件数: {published}")


if __name__ == "__main__":
    main()
