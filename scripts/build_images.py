"""Build the site's web images from assets-src/ into static/img/.

Run after adding or replacing a source photo:  python scripts/build_images.py
Each photo becomes WebP files at a few widths (never upscaled) so templates can use srcset.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'assets-src'
OUT = ROOT / 'static' / 'img'

# name -> widths to emit (the largest is capped at the source width)
PHOTOS = {
    'kia-k5-front': (480, 960, 1440),
    'kia-k5-rear': (480, 960, 1440),
    'altima-before': (480, 960, 1440),
    'altima-after': (480, 960, 1440),
    'altima-console-before': (480, 960, 1440),
    'altima-console-after': (480, 960, 1440),
    'f150-before': (480, 960, 1440),
    'f150-after': (480, 960, 1440),
    'g37-before': (360, 401),
    'grand-cherokee': (360, 453),
    'owner-senna': (480, 800, 1200),
}


def save_widths(img: Image.Image, name: str, widths: tuple[int, ...]) -> None:
    for w in widths:
        w = min(w, img.width)
        h = round(img.height * w / img.width)
        out = img.resize((w, h), Image.LANCZOS) if w != img.width else img
        out.save(OUT / 'work' / f'{name}-{w}.webp', 'WEBP', quality=82, method=6)


def build_logo() -> None:
    logo = Image.open(SRC / 'gem-logo.png').convert('RGBA')
    logo.save(OUT / 'gem-logo.webp', 'WEBP', quality=90, method=6)
    logo.resize((310, round(logo.height * 310 / logo.width)), Image.LANCZOS).save(OUT / 'gem-logo-310.webp', 'WEBP', quality=90)
    # the diamond mark, cut from the logo itself (never redrawn), on its native dark tile
    mark = logo.crop((139, 14, 472, 250))
    side = 300
    tile = Image.new('RGBA', (side, side), (11, 15, 20, 255))
    m = mark.copy()
    m.thumbnail((int(side * .78), int(side * .78)), Image.LANCZOS)
    tile.alpha_composite(m, ((side - m.width) // 2, (side - m.height) // 2 + 6))
    tile.save(OUT / 'gem-mark-tile.png')
    for s in (32, 64, 96, 180):
        tile.resize((s, s), Image.LANCZOS).save(OUT / f'gem-mark-{s}.png')
    tile.resize((96, 96), Image.LANCZOS).save(OUT / 'gem-mark-96.webp', 'WEBP', quality=90)


def main() -> None:
    (OUT / 'work').mkdir(parents=True, exist_ok=True)
    for name, widths in PHOTOS.items():
        src = next(SRC.glob(f'{name}.*'))
        img = ImageOps.exif_transpose(Image.open(src)).convert('RGB')
        save_widths(img, name, widths)
    build_logo()
    print('images built into', OUT)


if __name__ == '__main__':
    main()
