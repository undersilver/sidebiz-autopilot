from __future__ import annotations

import re


def article_h2_headings(markdown_text: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in re.finditer(r'^##\s+(.+?)\s*$', str(markdown_text), flags=re.M)
    ]


def normalize_pikoron_tips(draft: dict, maximum: int = 3) -> list[dict[str, str]]:
    """実在する章に紐づく短い要点だけを残す。本文から自動推測はしない。"""
    headings = set(article_h2_headings(draft.get('article_markdown', '')))
    normalized: list[dict[str, str]] = []
    used_headings: set[str] = set()

    for item in draft.get('pikoron_tips', []):
        if not isinstance(item, dict):
            continue
        heading = str(item.get('after_heading', '')).strip()
        message = str(item.get('message', '')).strip()
        if heading not in headings or heading in used_headings or not message:
            continue
        if len(message) > 120:
            message = message[:119].rstrip() + '…'
        normalized.append({'after_heading': heading, 'message': message})
        used_headings.add(heading)
        if len(normalized) >= maximum:
            break

    draft['pikoron_tips'] = normalized
    return normalized


def format_pikoron_tips_for_issue(draft: dict) -> str:
    tips = normalize_pikoron_tips(draft)
    return '\n'.join(
        f"- **{item['after_heading']}**：{item['message']}" for item in tips
    ) or '- なし'
