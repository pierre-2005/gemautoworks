# GEM Autoworks website (v2)

Website, online booking, customer garage and admin panel for **GEM Autoworks**, mobile car detailing in Central Massachusetts.
Self-hosted on a Raspberry Pi: FastAPI, SQLite and server-rendered pages in one small Docker container. No paid services.

## What it does

**For customers**
- Home, Services and prices, Work (before and after sliders), About Pavly, Reviews, Contact and Instagram posts
- Booking in five steps: package, car, where, a real open day and time, and contact details. It shows a live estimate, including the 10% first-detail offer
- Every booking gets an emailed link to see, move or cancel it, up to a cut-off you set
- **Garage accounts:** save cars and addresses, see every visit, book a saved car in two taps
- **Cleaning plans:** every 2, 4, 6 or 8 weeks on a chosen day and time. You approve a plan, and the next visits (3 by default) are kept on the calendar automatically. Customers can skip a visit, pause or cancel.

**For Pavly (`/admin`)**
- **Today:** the day's jobs as a timeline with Call, Text and Directions buttons, plus requests waiting for you
- **Calendar, Bookings** (search, filters, CSV) and **Customers**, with garages and private notes
- **Plans:** approve, pause, resume or cancel
- **Prices:** each package's price and time for sedan, SUV and truck, plus add-ons
- **Hours:** weekly hours, days off, blocked time, travel time between jobs, how far ahead people can book, a cancellation cut-off, and confirm-every-booking or instant mode
- **Website:**
  - The mobile / shop / both switch, which changes the booking flow and the wording everywhere
  - Service area, offer, contact details and the main text on the site
- **Photos** (before and after uploads), **Instagram posts**, **Reviews** (approve first), **Messages**
- **System:** email outbox with retry, admin accounts, password change, database backup download

## Deploying (GitHub → GHCR → Portainer on the Pi)

1. Merge to `main`. GitHub Actions runs the tests and Chromium checks, then publishes `ghcr.io/pierre-2005/gemautoworks:latest` for ARM64 and AMD64.
2. In Portainer, the stack uses `docker-compose.yml`. Set these environment variables:

| Variable | Needed | Notes |
|---|---|---|
| `SECRET_KEY` | yes | 48+ random characters: `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | first boot only | Only used if no admin exists. **v1's admin login is imported**, so the old login keeps working |
| `PUBLIC_BASE_URL` | yes | e.g. `https://gemautoworks.com`, used for links in emails |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | for email | A Gmail app password works (`smtp.gmail.com`, `465`, `ssl`). Without these, emails wait in Admin → System |
| `BUSINESS_TIMEZONE` | default fine | `America/New_York` |

3. Pull the new image and redeploy the stack.
4. Keep the site reachable **only through the Cloudflare tunnel** (the compose file binds it to `127.0.0.1:8092`). The rate limits trust Cloudflare's `CF-Connecting-IP` header from local or private addresses, so don't expose port 8092 to your LAN or put another proxy in front without removing that header.

### Your existing data is safe

- v2 uses a **new** database file, `gem_v2.sqlite3`, in the same `gem_data` volume.
- On its first start it **copies** the v1 admin login, bookings, reviews and uploaded photos from `gem.sqlite3`. It opens the old file read-only and never changes it.
- To roll back, redeploy the previous image. Its data is exactly as you left it.
- Back up the `gem_data` volume, or use **Admin → System → Download database backup**.

### Things to set after the first deploy (Admin)

- **Hours:** the weekly hours start as Mon–Sat 8 am–6 pm. Set the real ones.
- **Prices:** times per package and size start as estimates (Exterior 1.5–2 h, Interior 2.5–3.5 h, GEM 4–5 h). Adjust them, because they decide how much calendar each booking takes.
- **Website → How you work:** mobile, shop or both, the shop address, and the towns you cover.
- **System:** confirm that email shows as Connected.

## Running locally

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m playwright install chromium
export SECRET_KEY=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))") DATA_DIR=./data COOKIE_SECURE=false \
       ADMIN_EMAIL=admin@example.test ADMIN_PASSWORD=change-me-please-123
uvicorn app.main:app --reload
python -m pytest -q tests/test_app.py   # flow tests
python tests/visual_smoke.py            # every page at 1440 and 390, screenshots in visual-artifacts/
python tests/flow_smoke.py              # books a detail in Chromium
python tests/admin_shots.py             # garage and admin screens
```

New photos: put the original in `assets-src/`, add it to `scripts/build_images.py`, and run `python scripts/build_images.py`. Photos uploaded in the admin are processed automatically.

## Design notes

- `SPEC.md` is what was built and why. `PRODUCT.md` and `DESIGN.md` hold the product facts and the visual system.
- The public pages are built on the Taste skill's kit (`static/kit/`) and pass its finish gate.
- Booking, account and admin follow Impeccable's "operate" rules.
- Every photo is GEM's own, from their Instagram. The owner photo is from the v1 site.
