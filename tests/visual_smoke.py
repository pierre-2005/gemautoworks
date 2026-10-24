"""Browser smoke checks for responsive layouts and the simplified admin interface.

Runs in CI with Playwright Chromium; uses an isolated temporary database.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOT_DIR = ROOT / "visual-artifacts"
SHOT_DIR.mkdir(exist_ok=True)
SCREENS = [
    ("small-phone", 360, 780),
    ("phone", 390, 844),
    ("tablet", 768, 1024),
    ("laptop", 1024, 768),
    ("desktop", 1440, 900),
]
PAGES = ["/", "/services", "/gallery", "/reviews", "/contact", "/book", "/admin/login"]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    port = free_port()
    env = os.environ.copy()
    env.update({
        "DATA_DIR": tempfile.mkdtemp(prefix="gem-ui-test-"),
        "SECRET_KEY": "Gem-visual-tests-use-this-long-isolated-secret-123456",
        "ADMIN_EMAIL": "owner@example.com",
        "ADMIN_PASSWORD": "StrongVisualTestPassword-2026",
        "COOKIE_SECURE": "false",
        "BUSINESS_TIMEZONE": "America/New_York",
    })
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        import urllib.request
        for _ in range(100):
            if server.poll() is not None:
                raise RuntimeError("Server exited unexpectedly before tests started")
            try:
                with urllib.request.urlopen(base + "/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(.15)
        else:
            raise RuntimeError("Local test server did not start")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for name, width, height in SCREENS:
                    page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
                    for route in PAGES:
                        response = page.goto(base + route, wait_until="domcontentloaded")
                        if not response or response.status != 200:
                            raise AssertionError(f"{name} {route}: page did not return HTTP 200")
                        page.locator("body").wait_for()
                        metrics = page.evaluate("""() => ({
                            docWidth: document.documentElement.scrollWidth,
                            viewport: document.documentElement.clientWidth
                        })""")
                        if metrics["docWidth"] > metrics["viewport"] + 2:
                            raise AssertionError(f"{name} {route}: horizontal overflow {metrics}")
                    page.goto(base, wait_until="domcontentloaded")
                    page.screenshot(path=str(SHOT_DIR / f"home-{name}.png"), full_page=True, animations="disabled")
                    if width <= 920:
                        menu = page.locator(".menu-toggle")
                        menu.click()
                        assert page.locator("#main-nav").is_visible(), f"{name}: mobile menu did not open"
                        menu.click()
                        assert not page.locator("#main-nav").is_visible(), f"{name}: mobile menu did not close"
                    page.goto(base + "/book", wait_until="domcontentloaded")
                    if name in ("small-phone", "phone"):
                        page.screenshot(path=str(SHOT_DIR / f"booking-{name}.png"), full_page=True, animations="disabled")
                    page.goto(base + "/admin/login", wait_until="domcontentloaded")
                    page.locator('input[name="email"]').fill("owner@example.com")
                    page.locator('input[name="password"]').fill("StrongVisualTestPassword-2026")
                    page.locator('button[type="submit"]').click()
                    page.wait_for_url("**/admin")
                    page.locator('[data-admin-section="settings"]').click()
                    assert page.locator("#settings").is_visible(), f"{name}: website editor tab not visible"
                    assert not page.locator("#appointments").is_visible(), f"{name}: appointments should be hidden in website tab"
                    page.locator('[data-admin-section="appointments"]').click()
                    assert page.locator("#appointments").is_visible(), f"{name}: appointments tab not visible"
                    if name in ("phone", "desktop"):
                        page.screenshot(path=str(SHOT_DIR / f"admin-{name}.png"), full_page=True, animations="disabled")
                    page.close()
            finally:
                browser.close()
        print(f"Responsive browser checks passed: {len(SCREENS)} widths x {len(PAGES)} pages, menus and admin navigation.")
    finally:
        server.terminate()
        try:
            server.wait(timeout=8)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
