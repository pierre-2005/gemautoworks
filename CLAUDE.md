# CLAUDE.md — GEM Autoworks

## Stack
- Python 3.12 · FastAPI · Jinja2 server-rendered templates · SQLite (WAL) · Argon2 · itsdangerous sessions
- Frontend: hand-written CSS (design tokens in `static/css/tokens.css`) + small vanilla JS modules. No build step, no framework.
- Fonts self-hosted in `static/fonts/` (no third-party requests).
- Deploy: push to `main` → GitHub Actions runs tests → publishes `ghcr.io/pierre-2005/gemautoworks:latest` (arm64 + amd64) → Portainer stack on the Raspberry Pi pulls it. Data lives in the `gem_data` volume at `/data`.

## Layout
```
app/            main.py (app + middleware), db.py (schema/migrations), auth.py, booking.py (availability, plans), mail.py, routes/{public,account,admin}.py
templates/      base.html, partials/, public/, account/, admin/, email/
static/         css/, js/, img/ (optimized webp/avif + srcset sizes), fonts/
tests/          pytest unit/integration; visual_smoke.py (Playwright screenshots 390/1440)
```

## Conventions
- Every POST form carries a CSRF token; every public form has a honeypot + rate limit.
- All times stored as UTC ISO strings; displayed in `BUSINESS_TIMEZONE`.
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
python -m pytest -q
python tests/visual_smoke.py        # screenshots → visual-artifacts/
python scripts/build_images.py      # regenerate responsive images
```
