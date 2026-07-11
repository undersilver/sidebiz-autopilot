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


def wrap_japanese(text: str, draw: ImageDraw.ImageDraw, font, max_width: int) -> list[str]:
    lines, current = [], ''
    for char in text:
        candidate = current + char
        box = draw.textbbox((0, 0), candidate, font=font)
        if current and box[2] - box[0] > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def fit_title(text: str, draw: ImageDraw.ImageDraw, max_width: int, max_height: int):
    for size in (52, 48, 44, 40, 36, 32):
        font = get_font(size)
        lines = wrap_japanese(text, draw, font, max_width)
        line_height = int(size * 1.3)
        if len(lines) <= 6 and len(lines) * line_height <= max_height:
            return font, lines, line_height
    font = get_font(30)
    return font, wrap_japanese(text, draw, font, max_width)[:6], 39


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
    mascot_panel = (65, 60, 520, height - 60)
    draw.rounded_rectangle(mascot_panel, radius=28,
                           fill=(238, 242, 255))

    mascot = Image.open(ROOT / THUMB['mascot_path']).convert('RGBA')
    mascot.thumbnail((300, 400))
    mascot_x = (mascot_panel[0] + mascot_panel[2] - mascot.width) // 2
    mascot_y = (height - mascot.height) // 2
    canvas.paste(mascot, (mascot_x, mascot_y), mascot)

    title_x = 575
    draw.text((title_x, 95), data.get('category', 'AIゲーム制作'),
              font=get_font(36), fill=(79, 70, 229))
    y = 165
    title_font, title_lines, line_height = fit_title(
        data['title'], draw, width - title_x - 85, height - 165 - 175
    )
    for line in title_lines:
        draw.text((title_x, y), line, font=title_font, fill=(27, 37, 53))
        y += line_height
    draw.rounded_rectangle((title_x, height - 145, width - 90, height - 90),
                           radius=18, fill=(79, 70, 229))
    draw.text((title_x + 30, height - 137), SETTINGS['site_name'],
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
