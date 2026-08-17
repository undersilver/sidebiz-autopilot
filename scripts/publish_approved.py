from __future__ import annotations

import json
import os
import re
from datetime import datetime
from email.utils import format_datetime
from html import unescape
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

import requests
from content_utils import normalize_pikoron_tips

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / "config/settings.json").read_text(encoding="utf-8"))
THUMBNAIL_VERSION = str(SETTINGS.get("thumbnail", {}).get("cache_version", "1"))
SITE_URL = str(SETTINGS.get("site_url", "")).rstrip("/")


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
        pattern = re.compile(rf"(<h2>\s*{re.escape(heading_html)}\s*</h2>)")
        aside = (
            '<aside class="pikoron-tip" aria-label="ピコロンの要点">'
            '<img class="pikoron-tip-avatar" src="../assets/pikolon.png" alt="ピコロン">'
            '<div class="pikoron-tip-bubble"><strong>ピコロンの要点</strong>'
            f'<p>{escape(tip["message"])}</p></div></aside>'
        )
        result, replaced = pattern.subn(rf"\1{aside}", result, count=1)
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
    canonical_url = f"{SITE_URL}/posts/{post_path.name}"
    image_url = f"{SITE_URL}/assets/thumbnails/{date}-{data['slug']}.png?v={THUMBNAIL_VERSION}"
    published_at = data.get("_meta", {}).get("published_at") or now_local().isoformat()
    modified_at = now_local().isoformat()

    article_html = insert_pikoron_tips(markdown_to_html(data["article_markdown"]), data)
    structured_data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": data["title"],
        "description": data["summary"],
        "image": [image_url],
        "datePublished": published_at,
        "dateModified": modified_at,
        "author": {"@type": "Person", "name": SETTINGS.get("author", "")},
        "publisher": {"@type": "Organization", "name": SETTINGS["site_name"]},
        "mainEntityOfPage": canonical_url,
    }
    html = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{escape(data['title'])} | {escape(SETTINGS['site_name'])}</title>
  <meta name="description" content="{escape(data['summary'])}">
  <link rel="canonical" href="{escape(canonical_url)}">
  <meta property="og:type" content="article">
  <meta property="og:site_name" content="{escape(SETTINGS['site_name'])}">
  <meta property="og:title" content="{escape(data['title'])}">
  <meta property="og:description" content="{escape(data['summary'])}">
  <meta property="og:url" content="{escape(canonical_url)}">
  <meta property="og:image" content="{escape(image_url)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{escape(data['title'])}">
  <meta name="twitter:description" content="{escape(data['summary'])}">
  <meta name="twitter:image" content="{escape(image_url)}">
  <script type="application/ld+json">{json.dumps(structured_data, ensure_ascii=False)}</script>
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
</html>
"""
    post_path.write_text(html, encoding="utf-8")
    data["_meta"]["status"] = "published"
    data["_meta"]["published_at"] = published_at
    data["_meta"]["updated_at"] = modified_at
    draft_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return post_path


def parse_post(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    title_match = re.search(r"<h1>(.*?)</h1>", text, re.DOTALL)
    lead_match = re.search(r'<p class="lead">(.*?)</p>', text, re.DOTALL)
    canonical_match = re.search(r'<link rel="canonical" href="([^"]+)">', text)
    json_ld_match = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', text, re.DOTALL
    )
    if not title_match:
        return None
    published_at = f"{path.stem[:10]}T00:00:00+09:00"
    if json_ld_match:
        try:
            published_at = json.loads(json_ld_match.group(1)).get(
                "datePublished", published_at
            )
        except (json.JSONDecodeError, TypeError):
            pass
    relative_path = f"posts/{path.name}"
    return {
        "path": relative_path,
        "url": canonical_match.group(1) if canonical_match else f"{SITE_URL}/{relative_path}",
        "title": unescape(title_match.group(1).strip()),
        "lead": unescape(lead_match.group(1).strip()) if lead_match else "",
        "thumbnail": f"assets/thumbnails/{path.stem}.png?v={THUMBNAIL_VERSION}",
        "published_at": published_at,
    }


def write_feed(posts: list[dict]) -> None:
    items = []
    for post in posts[:30]:
        try:
            dt = datetime.fromisoformat(post["published_at"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo(SETTINGS.get("timezone", "Asia/Tokyo")))
            pub_date = format_datetime(dt)
        except (TypeError, ValueError):
            pub_date = format_datetime(now_local())
        items.append(
            "    <item>\n"
            f"      <title>{xml_escape(post['title'])}</title>\n"
            f"      <link>{xml_escape(post['url'])}</link>\n"
            f"      <guid isPermaLink=\"true\">{xml_escape(post['url'])}</guid>\n"
            f"      <pubDate>{xml_escape(pub_date)}</pubDate>\n"
            f"      <description>{xml_escape(post['lead'])}</description>\n"
            "    </item>"
        )
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n'
        '  <channel>\n'
        f"    <title>{xml_escape(SETTINGS['site_name'])}</title>\n"
        f"    <link>{xml_escape(SITE_URL + '/')}</link>\n"
        f"    <description>{xml_escape(SETTINGS['site_description'])}</description>\n"
        '    <language>ja</language>\n'
        + ("\n".join(items) + "\n" if items else "")
        + "  </channel>\n</rss>\n"
    )
    (ROOT / "docs/feed.xml").write_text(feed, encoding="utf-8")


def write_sitemap(posts: list[dict]) -> None:
    urls = [
        "  <url>\n"
        f"    <loc>{xml_escape(SITE_URL + '/')}</loc>\n"
        "    <changefreq>daily</changefreq>\n"
        "    <priority>1.0</priority>\n"
        "  </url>"
    ]
    for post in posts:
        lastmod = str(post["published_at"])[:10]
        urls.append(
            "  <url>\n"
            f"    <loc>{xml_escape(post['url'])}</loc>\n"
            f"    <lastmod>{xml_escape(lastmod)}</lastmod>\n"
            "    <changefreq>monthly</changefreq>\n"
            "    <priority>0.8</priority>\n"
            "  </url>"
        )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )
    (ROOT / "docs/sitemap.xml").write_text(sitemap, encoding="utf-8")


def rebuild_index() -> None:
    posts = []
    for path in sorted((ROOT / "docs/posts").glob("*.html"), reverse=True):
        post = parse_post(path)
        if post:
            posts.append(post)

    cards = "\n".join(
        f'<article class="card"><a href="{escape(p["path"])}"><img src="{escape(p["thumbnail"])}" alt="{escape(p["title"])}"></a><div><h2><a href="{escape(p["path"])}">{escape(p["title"])}</a></h2><p>{escape(p["lead"])}</p></div></article>'
        for p in posts
    ) or "<p>最初の記事を準備中です。</p>"
    canonical_url = f"{SITE_URL}/"

    html = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{escape(SETTINGS['site_name'])}</title>
  <meta name="description" content="{escape(SETTINGS['site_description'])}">
  <link rel="canonical" href="{escape(canonical_url)}">
  <link rel="alternate" type="application/rss+xml" title="{escape(SETTINGS['site_name'])}" href="{escape(SITE_URL + '/feed.xml')}">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{escape(SETTINGS['site_name'])}">
  <meta property="og:description" content="{escape(SETTINGS['site_description'])}">
  <meta property="og:url" content="{escape(canonical_url)}">
  <meta name="twitter:card" content="summary">
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
</html>
"""
    (ROOT / "docs/index.html").write_text(html, encoding="utf-8")
    write_feed(posts)
    write_sitemap(posts)


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
