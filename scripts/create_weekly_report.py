from __future__ import annotations
import json, os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]

def main():
    history_path = ROOT / 'data/history.json'
    history = json.loads(history_path.read_text(encoding='utf-8')) if history_path.exists() else []
    cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    recent = [x for x in history if x.get('date', '') >= cutoff]
    published, scores, categories = [], [], Counter()
    for item in recent:
        path = ROOT / item.get('draft', '')
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        categories[data.get('category', '未分類')] += 1
        score = data.get('_validation', {}).get('score')
        if isinstance(score, int): scores.append(score)
        if data.get('_meta', {}).get('status') == 'published': published.append(data.get('title', ''))
    avg = round(sum(scores) / len(scores), 1) if scores else 0
    body = f'''## 週次運用レポート

期間：直近7日

- 生成件数：{len(recent)}
- 公開件数：{len(published)}
- 平均校閲スコア：{avg}
- カテゴリー内訳：{dict(categories)}

### 公開記事
''' + ('\n'.join(f'- {x}' for x in published) or '- なし') + '''

### 来週の方針
- スコア80未満のテーマは具体例を増やす
- 同一カテゴリーが続きすぎないよう調整する
- 公開件数より品質を優先する
'''
    repo, token = os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_TOKEN']
    r = requests.post(f'https://api.github.com/repos/{repo}/issues', headers={'Authorization':f'Bearer {token}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}, json={'title':f'【週次レポート】{datetime.now():%Y-%m-%d}','body':body,'labels':['weekly-report']}, timeout=60)
    r.raise_for_status()

if __name__ == '__main__': main()
