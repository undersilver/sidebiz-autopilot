from __future__ import annotations

import json
import os
import re
from pathlib import Path
import requests
from content_utils import format_pikoron_tips_for_issue, normalize_pikoron_tips
from gemini_client import call_json_model

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / 'config/settings.json').read_text(encoding='utf-8'))
def headers():
    return {
        'Authorization': f"Bearer {os.environ['GITHUB_TOKEN']}",
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }


def call_model(draft: dict) -> dict:
    prompt = f'''次の原稿を0〜100点で厳格に校閲してください。
scoreは必ず0〜100の整数。90点なら90と返し、9とは返さないでください。

基準：一般読者向け、内部運用情報なし、未検証断定なし、未完成表現なし、具体性、タイトルとの一致、権利侵害懸念、不自然な宣伝や冗長さ。pikoron_tipsは0〜3件で対象章の重要な要点に直接関係し、余計な場所へ表示されないこと。

原稿：
{json.dumps(draft, ensure_ascii=False)}

JSONだけを返してください。
{{"status":"pass|rewrite|block","score":0,"issues":[{{"severity":"low|medium|high","category":"...","detail":"..."}}],"rewrite_instructions":["..."],"publishable":true}}'''
    result = call_json_model(
        messages=[
            {'role': 'system', 'content': '有効なJSONだけを返してください。'},
            {'role': 'user', 'content': prompt},
        ],
        model=SETTINGS['model'],
        temperature=0.1,
        max_tokens=1800,
    )
    score = int(result.get('score', 0))
    if 1 <= score <= 10 and result.get('status') == 'pass' and result.get('publishable') is True:
        if not any(i.get('severity') == 'high' for i in result.get('issues', [])):
            result['score'] = score * 10
    return result


def is_publishable(draft: dict, validation: dict) -> bool:
    try:
        score = int(validation.get('score', 0))
    except (TypeError, ValueError):
        return False
    has_high = any(
        isinstance(item, dict) and item.get('severity') == 'high'
        for item in validation.get('issues', [])
    )
    article = str(draft.get('article_markdown', ''))
    has_incomplete_marker = any(
        marker in article for marker in ('要出典', '今後調査が必要')
    )
    return (
        validation.get('status') == 'pass'
        and validation.get('publishable') is True
        and score >= int(SETTINGS['validation']['minimum_score'])
        and not has_high
        and not draft.get('sources_needed')
        and not has_incomplete_marker
    )


def build_issue_body(draft: dict, path: Path, validation: dict, publishable: bool) -> str:
    checks = '\n'.join(
        f"- [{item.get('risk', '')}] **{item.get('type', '')}**：{item.get('item', '')}"
        for item in draft.get('human_checks', [])
    ) or '- なし'
    issues = '\n'.join(
        f"- [{item.get('severity', '')}] **{item.get('category', '')}**：{item.get('detail', '')}"
        for item in validation.get('issues', [])
    ) or '- なし'
    pikoron_tips = format_pikoron_tips_for_issue(draft)
    status_text = '公開候補' if publishable else '公開不可・要修正'
    instruction = (
        '問題なければ `approve` ラベルを追加してください。'
        if publishable else
        '`approve` は付けず、コメント欄から `/revise 修正内容` を送信してください。'
    )
    return f'''## 本日の公開候補

**タイトル**：{draft.get('title', '')}

**カテゴリー**：{draft.get('category', '')}

**概要**：{draft.get('summary', '')}

**編集校閲スコア**：{validation.get('score', 0)} / 100

**公開可否**：{status_text}

**推定確認時間**：{draft.get('estimated_review_minutes', 10)}分

### AI校閲で検出した問題

{issues}

### 人間が確認する項目

{checks}

### SNS投稿案

{draft.get('social_post', '')}

### ショート動画台本

{draft.get('short_video_script', '')}

### サムネイル生成指示

{draft.get('thumbnail_prompt', '')}

### ピコロンの要点吹き出し

{pikoron_tips}

### 下書きファイル

`{path.relative_to(ROOT)}`

---

{instruction}
'''


def main():
    repo = os.environ['GITHUB_REPOSITORY']
    issues = requests.get(f'https://api.github.com/repos/{repo}/issues?state=open&labels=needs-fix&per_page=20', headers=headers(), timeout=60)
    issues.raise_for_status()
    for issue in issues.json():
        match = re.search(r'`(drafts/[^`]+\.json)`', issue.get('body', ''))
        if not match:
            continue
        path = ROOT / match.group(1)
        if not path.exists():
            continue
        draft = json.loads(path.read_text(encoding='utf-8'))
        # /revise 後は _validation が削除される。未修正のneeds-fix原稿は再校閲しない。
        if '_validation' in draft:
            continue
        normalize_pikoron_tips(draft)
        validation = call_model(draft)
        draft['_validation'] = validation
        maximum_review = int(SETTINGS.get('max_review_minutes', 10))
        try:
            review_minutes = int(draft.get('estimated_review_minutes', maximum_review))
        except (TypeError, ValueError):
            review_minutes = maximum_review
        draft['estimated_review_minutes'] = max(1, min(review_minutes, maximum_review))
        publishable = is_publishable(draft, validation)
        draft.setdefault('_meta', {})['status'] = 'review' if publishable else 'blocked'
        path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding='utf-8')

        status_text = '公開候補' if publishable else '引き続き要修正'
        details = '\n'.join(f"- [{i.get('severity')}] {i.get('category')}：{i.get('detail')}" for i in validation.get('issues', [])) or '- 問題なし'
        requests.post(f"https://api.github.com/repos/{repo}/issues/{issue['number']}/comments", headers=headers(), json={
            'body': f"再校閲完了：**{validation.get('score', 0)} / 100**、判定：**{status_text}**\n\n{details}"
        }, timeout=60).raise_for_status()

        requests.patch(
            f"https://api.github.com/repos/{repo}/issues/{issue['number']}",
            headers=headers(),
            json={'body': build_issue_body(draft, path, validation, publishable)},
            timeout=60,
        ).raise_for_status()

        labels = [x['name'] for x in issue.get('labels', []) if x['name'] not in {'needs-fix', 'approve'}]
        labels.append('review' if publishable else 'needs-fix')
        requests.put(f"https://api.github.com/repos/{repo}/issues/{issue['number']}/labels", headers=headers(), json={'labels': labels}, timeout=60).raise_for_status()


if __name__ == '__main__':
    main()
