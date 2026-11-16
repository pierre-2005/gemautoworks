# CLAUDE.md — GEM Autoworks

## Stack
- Python 3.12 · FastAPI · Jinja2 server-rendered templates · SQLite (WAL) · Argon2 · itsdangerous sessions
- Frontend: the Taste kit (`static/kit/`) + page CSS (`static/css/site.css`, `app.css`, `admin.css`; tokens in the `:root` block of `templates/base.html`) + small vanilla JS. No build step, no framework.
- Fonts self-hosted in `static/fonts/` (no third-party requests).
- Deploy: push to `main` → GitHub Actions runs tests → publishes `ghcr.io/pierre-2005/gemautoworks:latest` (arm64 + amd64) → Portainer stack on the Raspberry Pi pulls it. Data lives in the `gem_data` volume at `/data`.

## Layout
```
app/            main.py (app, middleware, picture()), config.py, db.py (schema, migrations, seed, v1 import), security.py,
                booking.py (prices, availability, plans), mail.py (outbox, reminders, worker), routes/{public,account,admin}.py
templates/      base.html, app_base.html, partials/, public/, book/, account/, admin/
static/         kit/ (Taste, do not edit), css/, js/, img/ (WebP srcset widths), fonts/
tests/          test_app.py (pytest flows); visual_smoke.py, flow_smoke.py, admin_shots.py (Chromium, need a running server)
```

## Conventions
- Every POST form carries a CSRF token; every public form has a honeypot + rate limit.
- Appointment times are stored as local wall-clock strings (`YYYY-MM-DDTHH:MM` in `BUSINESS_TIMEZONE`): one detailer, one calendar. Audit timestamps (`created_at`) are UTC.
- Public pages use the Taste kit (`static/kit/`, do not edit it) and must keep passing its gate; app pages extend `app_base.html` (normal flow).
- Settings are key/value in `settings`; read via `get_settings()`; never hard-code business copy in templates.
- Schema changes go through numbered migrations in `db.py` (`schema_version`).
- No lorem ipsum. No invented reviews, prices, or claims.
- Images: add originals to `assets-src/`, run `python scripts/build_images.py`.
- Motion: CSS transitions ≤ 300ms, transform/opacity only, always honor `prefers-reduced-motion`.

## Commands
```bash
pip install -r requirements.txt -r requirements-dev.txt
SECRET_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(48))") COOKIE_SECURE=false DATA_DIR=./data \
  ADMIN_EMAIL=admin@example.test ADMIN_PASSWORD=change-me-please-123 uvicorn app.main:app --reload
python -m pytest -q tests/test_app.py
python tests/visual_smoke.py        # screenshots → visual-artifacts/
python scripts/build_images.py      # regenerate responsive images
```
