from __future__ import annotations

import json
import os
import re
from pathlib import Path
import requests
from content_utils import normalize_pikoron_tips

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / 'config/settings.json').read_text(encoding='utf-8'))
API_URL = 'https://models.github.ai/inference/chat/completions'


def headers():
    return {
        'Authorization': f"Bearer {os.environ['GITHUB_TOKEN']}",
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }


def api(method: str, path: str, payload=None):
    repo = os.environ['GITHUB_REPOSITORY']
    r = requests.request(method, f'https://api.github.com/repos/{repo}{path}',
                         headers=headers(), json=payload, timeout=120)
    r.raise_for_status()
    return r.json() if r.content else {}


def model(prompt: str) -> dict:
    r = requests.post(API_URL, headers={**headers(), 'Content-Type': 'application/json'}, json={
        'model': SETTINGS['model'],
        'messages': [
            {'role': 'system', 'content': '修正指示を正確に反映し、有効なJSONだけを返してください。'},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.3,
        'max_tokens': 4500,
    }, timeout=180)
    r.raise_for_status()
    content = re.sub(r'^```json\s*|\s*```$', '', r.json()['choices'][0]['message']['content'].strip(), flags=re.S)
    return json.loads(content)


def main():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
    comment = event['comment']['body'].strip()
    command = SETTINGS.get('revision_command', '/revise')
    if not comment.startswith(command):
        return
    instruction = comment[len(command):].strip()
    if not instruction:
        raise RuntimeError('修正内容がありません。/revise の後に指示を書いてください。')

    issue = event['issue']
    if event.get('comment', {}).get('user', {}).get('login') != event.get('repository', {}).get('owner', {}).get('login'):
        raise RuntimeError('リポジトリ所有者以外は修正を実行できません')
    match = re.search(r'`(drafts/[^`]+\.json)`', issue.get('body', ''))
    if not match:
        raise RuntimeError('下書きファイルを特定できません')
    draft_path = ROOT / match.group(1)
    draft = json.loads(draft_path.read_text(encoding='utf-8'))

    revised = model(f'''以下の公開候補JSONを、ユーザーの修正指示に従って修正してください。

修正指示：
{instruction}

公開候補：
{json.dumps(draft, ensure_ascii=False)}

条件：
- 一般読者向けの記事として完成させる
- 内部運用情報は本文に含めない
- 未確認情報を断定しない
- JSONの主要フィールドを維持する
- pikoron_tipsは重要な要点だけ0〜3件とし、対象の##見出しへ完全一致させる
- 関係のない章や全段落へ吹き出しを追加しない
- _meta はそのまま維持する
- _validation は削除し、再校閲待ちにする
''')
    revised['_meta'] = draft.get('_meta', {})
    revised['_meta']['status'] = 'review'
    maximum_review = int(SETTINGS.get('max_review_minutes', 10))
    try:
        review_minutes = int(revised.get('estimated_review_minutes', maximum_review))
    except (TypeError, ValueError):
        review_minutes = maximum_review
    revised['estimated_review_minutes'] = max(1, min(review_minutes, maximum_review))
    normalize_pikoron_tips(revised)
    revised.pop('_validation', None)
    draft_path.write_text(json.dumps(revised, ensure_ascii=False, indent=2), encoding='utf-8')

    api('POST', f"/issues/{issue['number']}/comments", {
        'body': '修正指示を下書きへ反映しました。Actions の `Revalidate revised drafts` を実行してください。'
    })
    labels = [x['name'] for x in issue.get('labels', []) if x['name'] != 'approve']
    if 'needs-fix' not in labels:
        labels.append('needs-fix')
    api('PUT', f"/issues/{issue['number']}/labels", {'labels': labels})


if __name__ == '__main__':
    main()
