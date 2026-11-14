"""Drive the real booking flow in Chromium: pick a package, size, day and time, book as a guest, then
check the manage page. Saves screenshots to visual-artifacts/. Usage: python tests/flow_smoke.py [base_url]"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'
OUT = Path('visual-artifacts')


def run(width: int, height: int, label: str, email: str) -> None:
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={'width': width, 'height': height})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(f'{BASE}/book')
        page.locator('#step-package label.choice', has_text='Interior Detail').click()
        page.locator('#step-car label.choice', has_text='SUV or crossover').click()
        page.fill('#b-year', '2020'); page.fill('#b-make', 'Honda'); page.fill('#b-model', 'Pilot')
        page.fill('#b-street', '20 Pine St'); page.fill('#b-town', 'Worcester')
        first_day = page.locator('[name="day_pick"]:not([disabled])').first
        first_day.wait_for(state='attached', timeout=10000)
        first_day.locator('xpath=..').click()
        page.locator('[name="time"]').first.wait_for(state='attached', timeout=10000)
        page.locator('[name="time"]').first.locator('xpath=..').click()
        page.fill('#b-name', 'Flow Tester'); page.fill('#b-phone', '508-555-0123'); page.fill('#b-email', email)
        expect(page.locator('[data-t-total]')).not_to_have_text('–')
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT / f'flow-{label}-book-filled.png'), full_page=True)
        page.locator('aside button[type="submit"]').click()
        page.wait_for_url('**/booking/**')
        expect(page.get_by_text('Your request is in')).to_be_visible()
        page.screenshot(path=str(OUT / f'flow-{label}-manage.png'), full_page=True)
        assert not errors, errors
        b.close()
    print(f'{label}: booked and reached the manage page')


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    run(1440, 900, 'desktop', 'flow-desktop@example.test')
    run(390, 844, 'phone', 'flow-phone@example.test')
