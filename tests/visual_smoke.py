"""Open pages in real Chromium at phone and desktop widths, save full-page screenshots and fail on console
errors or sideways scrolling.  Usage: python tests/visual_smoke.py [base_url] [path ...]"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'
PATHS = sys.argv[2:] or ['/', '/services', '/work', '/about', '/contact', '/reviews', '/book', '/account/login', '/account/signup',
                         '/privacy', '/admin/login', '/nope']
OUT = Path('visual-artifacts')
SIZES = {'desktop': (1440, 900), 'phone': (390, 844)}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for label, (w, h) in SIZES.items():
            ctx = browser.new_context(viewport={'width': w, 'height': h}, device_scale_factor=1, reduced_motion='reduce')
            page = ctx.new_page()
            errors: list[str] = []
            page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
            page.on('pageerror', lambda e: errors.append(str(e)))
            for path in PATHS:
                errors.clear()
                page.goto(BASE + path, wait_until='networkidle')
                page.wait_for_timeout(300)
                name = (path.strip('/').replace('/', '_') or 'home')
                page.screenshot(path=str(OUT / f'{label}-{name}.png'), full_page=True)
                over = page.evaluate('document.documentElement.scrollWidth - innerWidth')
                if over > 1:
                    problems.append(f'{label} {path}: scrolls sideways by {over}px')
                real = [e for e in errors if '404' not in e or path != '/nope']
                if real:
                    problems.append(f'{label} {path}: console errors: {real[:3]}')
            ctx.close()
        browser.close()
    print('\n'.join(problems) or 'visual smoke: no console errors, no sideways scroll')
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
