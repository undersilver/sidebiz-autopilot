from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / 'config/settings.json').read_text(encoding='utf-8'))

def now_local():
    return datetime.now(ZoneInfo(SETTINGS.get('timezone', 'Asia/Tokyo')))

def main():
    now = now_local()
    month = (now.replace(day=1).month - 1) or 12
    year = now.year if now.month > 1 else now.year - 1
    prefix = f'{year:04d}-{month:02d}'
    chapters = []
    for path in sorted((ROOT / 'docs/posts').glob(f'{prefix}-*.html')):
        soup = BeautifulSoup(path.read_text(encoding='utf-8'), 'html.parser')
        title, article = soup.find('h1'), soup.select_one('.article')
        if not title or not article: continue
        for selector in ['.category','.lead','.article-thumbnail','.disclosure','.affiliate-box','hr']:
            for node in article.select(selector): node.decompose()
        chapters.append(f"# {title.get_text(strip=True)}\n\n{article.get_text(chr(10), strip=True)}")
    if not chapters:
        print('対象記事なし'); return
    out_dir = ROOT / 'products/monthly'; out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f'{prefix}-manuscript.md'
    front = f'''# AIゲーム制作実践記録 {prefix}

## はじめに

この原稿は、当月に公開した記事を電子書籍・有料記事向けに再編集するための下書きです。
重複、表現、章順、出典、権利関係を確認してから販売してください。

'''
    output.write_text(front + '\n\n---\n\n'.join(chapters), encoding='utf-8')
    repo, token = os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_TOKEN']
    requests.post(f'https://api.github.com/repos/{repo}/issues', headers={'Authorization':f'Bearer {token}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}, json={'title':f'【月次商品候補】{prefix}','body':f'月次原稿を作成しました。\n\n`{output.relative_to(ROOT)}`\n\n販売前に章構成・重複・出典・権利を確認してください。','labels':['monthly-product','review']}, timeout=60).raise_for_status()

if __name__ == '__main__': main()
