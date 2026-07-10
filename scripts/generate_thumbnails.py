from __future__ import annotations

import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / 'config/settings.json').read_text(encoding='utf-8'))
THUMB = SETTINGS['thumbnail']


def get_font(size: int):
    try:
        return ImageFont.truetype(THUMB['font_path'], size)
    except OSError:
        return ImageFont.load_default()


def wrap_japanese(text: str, width: int) -> list[str]:
    lines, current = [], ''
    for char in text:
        if len(current + char) > width:
            lines.append(current)
            current = char
        else:
            current += char
    if current:
        lines.append(current)
    return lines[:4]


def create_thumbnail(draft_path: Path) -> Path:
    data = json.loads(draft_path.read_text(encoding='utf-8'))
    date = data['_meta']['created_at'][:10]
    output_dir = ROOT / 'docs/assets/thumbnails'
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{date}-{data['slug']}.png"

    width, height = int(THUMB['width']), int(THUMB['height'])
    canvas = Image.new('RGB', (width, height), (244, 247, 251))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((50, 45, width - 50, height - 45), radius=36,
                           fill=(255, 255, 255), outline=(219, 226, 236), width=4)
    draw.rounded_rectangle((65, 60, 790, height - 60), radius=28,
                           fill=(238, 242, 255))

    mascot = Image.open(ROOT / THUMB['mascot_path']).convert('RGBA')
    mascot.thumbnail((390, 500))
    canvas.paste(mascot, (255 - mascot.width // 2, height // 2 - mascot.height // 2), mascot)

    draw.text((835, 95), data.get('category', 'AIゲーム制作'),
              font=get_font(34), fill=(79, 70, 229))
    y = 165
    for line in wrap_japanese(data['title'], 15):
        draw.text((835, y), line, font=get_font(58), fill=(27, 37, 53))
        y += 78
    draw.rounded_rectangle((835, height - 145, width - 90, height - 90),
                           radius=18, fill=(79, 70, 229))
    draw.text((865, height - 137), SETTINGS['site_name'],
              font=get_font(27), fill=(255, 255, 255))
    canvas.save(output, quality=95)
    return output


def main() -> None:
    created = 0
    for draft_path in sorted((ROOT / 'drafts').glob('*.json')):
        data = json.loads(draft_path.read_text(encoding='utf-8'))
        if data.get('_meta', {}).get('status') not in {'review', 'published'}:
            continue
        print(create_thumbnail(draft_path))
        created += 1
    print(f'サムネイル作成件数: {created}')


if __name__ == '__main__':
    main()
