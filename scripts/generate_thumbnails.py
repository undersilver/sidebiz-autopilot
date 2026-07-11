from __future__ import annotations

import json
import re
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


def wrap_title_naturally(text: str, draw: ImageDraw.ImageDraw, font, max_width: int) -> list[str] | None:
    """単語途中を避け、助詞・述語・記号など意味の区切りでタイトルを折り返す。"""
    break_points = {0, len(text)}
    patterns = (
        r'：|:|！|!|？|\?|　| ',
        r'した|する|できる|活かす|使った|作る|方法|手順|設計|問題|原因|ポイント|コツ|活用|使い方|作り方|まとめ',
        r'から|まで|とは|について|を|に|で|が|は',
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            break_points.add(match.end())

    positions = sorted(break_points)
    best: dict[int, tuple[float, list[str]]] = {0: (0.0, [])}
    forbidden_starts = '、。・：:！？!?）】」』'

    for end in positions[1:]:
        for start in positions:
            if start >= end or start not in best:
                continue
            segment = text[start:end].strip()
            if not segment or segment[0] in forbidden_starts:
                continue
            box = draw.textbbox((0, 0), segment, font=font)
            rendered_width = box[2] - box[0]
            if rendered_width > max_width:
                continue
            unused = max_width - rendered_width
            # 余白が均等になる構成を優先し、細かすぎる改行を避ける。
            score = best[start][0] + unused * unused + 2000
            if end not in best or score < best[end][0]:
                best[end] = (score, best[start][1] + [segment])

    return best.get(len(text), (0.0, []))[1] or None


def fit_title(text: str, draw: ImageDraw.ImageDraw, max_width: int, max_height: int):
    for size in (60, 56, 52, 48, 44, 40, 36, 32):
        font = get_font(size)
        lines = wrap_title_naturally(text, draw, font, max_width)
        if not lines:
            continue
        line_height = int(size * 1.3)
        if len(lines) <= 5 and len(lines) * line_height <= max_height:
            return font, lines, line_height
    font = get_font(30)
    return font, wrap_japanese(text, draw, font, max_width)[:6], 39


def refresh_html_thumbnail_versions() -> int:
    version = str(THUMB.get('cache_version', '1'))
    pattern = re.compile(
        r'(src="(?:\.\./)?assets/thumbnails/[^"?]+\.png)(?:\?v=[^"]*)?(")'
    )
    updated = 0
    html_paths = [ROOT / 'docs/index.html', *(ROOT / 'docs/posts').glob('*.html')]
    for path in html_paths:
        if not path.exists():
            continue
        original = path.read_text(encoding='utf-8')
        revised = pattern.sub(rf'\1?v={version}\2', original)
        if revised != original:
            path.write_text(revised, encoding='utf-8')
            updated += 1
    return updated


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
    site_bar = (title_x, height - 145, width - 90, height - 90)
    draw.rounded_rectangle(site_bar, radius=18, fill=(79, 70, 229))
    site_font = get_font(27)
    site_text = SETTINGS['site_name']
    site_box = draw.textbbox((0, 0), site_text, font=site_font)
    site_text_width = site_box[2] - site_box[0]
    site_text_height = site_box[3] - site_box[1]
    site_x = site_bar[0] + (site_bar[2] - site_bar[0] - site_text_width) // 2
    site_y = site_bar[1] + (site_bar[3] - site_bar[1] - site_text_height) // 2 - site_box[1]
    draw.text((site_x, site_y), site_text, font=site_font, fill=(255, 255, 255))
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
    updated_html = refresh_html_thumbnail_versions()
    print(f'サムネイル作成件数: {created}')
    print(f'画像URL更新HTML件数: {updated_html}')


if __name__ == '__main__':
    main()
