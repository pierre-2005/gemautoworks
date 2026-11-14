"""Sign in as a customer and as the admin in Chromium and screenshot the working screens at desktop and phone.
Needs the dev server with ADMIN_EMAIL=admin@example.test / ADMIN_PASSWORD=change-me-please-123."""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'
OUT = Path('visual-artifacts')


def main() -> None:
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for label, (w, h) in {'desktop': (1440, 900), 'phone': (390, 844)}.items():
            errors = []
            ctx = b.new_context(viewport={'width': w, 'height': h})
            page = ctx.new_page()
            page.on('pageerror', lambda e: errors.append(str(e)))
            # customer
            page.goto(f'{BASE}/account/signup')
            page.fill('#a-name', 'Shots Customer'); page.fill('#a-email', f'shots-{label}-{int(__import__("time").time())}@example.test'); page.fill('#a-password', 'shots-password-1')
            page.click('button[type="submit"]')
            page.wait_for_url('**/account**')
            page.fill('#new-year', '2022'); page.fill('#new-make', 'Toyota'); page.fill('#new-model', 'Highlander')
            page.select_option('#new-size', 'suv'); page.fill('#new-color', 'Silver')
            page.locator('form[action="/account/vehicles"] button[type="submit"]').click()
            page.wait_for_load_state('networkidle')
            page.screenshot(path=str(OUT / f'{label}-account.png'), full_page=True)
            # admin
            page.goto(f'{BASE}/admin/login')
            page.fill('#ad-email', 'admin@example.test'); page.fill('#ad-pw', 'change-me-please-123')
            page.click('button[type="submit"]')
            page.wait_for_url(f'{BASE}/admin')
            for path in ('', '/calendar', '/appointments', '/services', '/availability', '/site', '/gallery', '/plans'):
                page.goto(f'{BASE}/admin{path}')
                page.wait_for_load_state('networkidle')
                page.screenshot(path=str(OUT / f'{label}-admin{path.replace("/", "-") or "-today"}.png'), full_page=True)
            over = page.evaluate('document.documentElement.scrollWidth - innerWidth')
            print(label, 'errors:', errors, 'sideways:', over)
            ctx.close()
        b.close()


if __name__ == '__main__':
    main()
