from __future__ import annotations

import json
from pathlib import Path

from publish_approved import publish, rebuild_index

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    rebuilt = 0
    for path in sorted((ROOT / 'drafts').glob('*.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('_meta', {}).get('status') != 'published':
            continue
        published_at = data.get('_meta', {}).get('published_at')
        publish(path)
        refreshed = json.loads(path.read_text(encoding='utf-8'))
        if published_at:
            refreshed['_meta']['published_at'] = published_at
            path.write_text(json.dumps(refreshed, ensure_ascii=False, indent=2), encoding='utf-8')
        rebuilt += 1
    rebuild_index()
    print(f'公開記事再構築件数: {rebuilt}')


if __name__ == "__main__":
    main()
