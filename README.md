# GEM Autoworks | Website V2

The public site now uses a cinematic, scroll-controlled 3D concept supercar, opening doors, live paint previews, ivory editorial sections, and the original GEM logo and blue identity. Gallery images enlarge in a keyboard-accessible dialog. Booking includes a live summary, calendar retry states, duplicate-submit protection, and errors that retain entered details. Service FAQs, contact routes, moderated reviews, and all admin capabilities remain available.

The model and textures are self-hosted under `static/models/supercar/`; the CC BY 4.0 attribution is under `static/licenses/`. They use separate same-origin textures so the existing Content Security Policy stays intact. Reduced motion holds the car still; unavailable WebGL and data-saving browsers receive the photographic fallback. There is no animation loop while the scene is idle or off-screen.

Frontend assets are committed, so Docker deployment still requires Python only. For frontend changes, use Node 22+, `npm ci`, then `npm run build:car`. `npm run prepare:car` re-downloads and optimizes the credited upstream concept model. `npm run check:js` checks application JavaScript syntax. PRs now run the existing test and responsive-browser CI; image publication still runs only outside PRs.

## Current website design and admin management

The redesigned public site keeps the original GEM logo, black and electric-blue branding, contact information, and automotive photographs. A responsive layout is used for small phones, tablets, and desktop screens. The same booking and content-management endpoints are retained.

Open **/admin/login** to sign in. The dashboard is organized into eight focused sections: Appointments, Availability, Services, Gallery, Reviews, Website, Emails, and Security. Use the left-side menu on desktop or swipeable section tabs on mobile. Manual appointment creation is under **Appointments → Add a booking manually**. Changes save back to the same dashboard section.

The site includes automated real-Chromium viewport tests at **360, 390, 768, 1024, and 1440 pixels**. The test job uploads downloadable preview screenshots to GitHub Actions under **gem-responsive-previews**.

### Deploying from private GitHub to Portainer

- The production Compose file uses the container image **`ghcr.io/pierre-2005/gemautoworks:latest`**, not a local Docker build or a committed `.env` file.
- Each push to `main` runs Python tests, responsive browser checks, and publishes ARM64 and AMD64 container images to GHCR.
- In Portainer, deploy a Git repository stack using `docker-compose.yml`. Set at least `SECRET_KEY`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` in the stack environment, plus the correct `BUSINESS_TIMEZONE`.
- SMTP credentials also belong in Portainer environment settings; they are required for real email notifications.
- Portainer must have pull access to a private GHCR package, or the package must be made public. Your Git repository can stay private either way.
- Persistent booking data and uploaded photos are stored in the Docker `gem_data` volume. Back it up; GitHub commits do not contain the customer database.
- After a successful image publish, use Portainer's image re-pull/redeploy action to pick up the latest image; Git polling for source changes alone is not proof that a newer image was pulled.
- `setup.py` and local `.env` examples are for local Docker installations only. Do **not** upload a populated `.env` file or other secrets to GitHub.


A bespoke dark/blue automotive website, self-hosted booking calendar, and website control room for GEM Autoworks. Built for the Raspberry Pi with FastAPI, SQLite, Jinja2, Docker, and a Cloudflare Tunnel. **No subscription booking platform is needed.**

## What's included

- Custom responsive home, services, photo gallery, customer reviews, contact, and appointment booking pages
- Original supplied transparent GEM logo and automotive showcase photograph, optimized for the web
- Auto-checked time slots for each service; durations, minimum notice, booking horizon, weekly opening hours, date overrides, and partial-day blocks
- Atomic booking transactions to prevent simultaneous visitors from reserving overlapping time
- Automatically confirmed bookings, or optional admin-approval mode
- Emails queued to owner and customer (after SMTP is configured); background retries and admin delivery logs
- Secure admin sign-in, dashboard, manual booking, rescheduling, status updates, service editor, photo uploads, homepage editor, review moderation, CSV download, and password change
- Mobile navigation, accessible labels, social links, search description, robots.txt, HTTPS-ready secure session cookies, CSRF protection, basic rate limiting, privacy page, and terms page
- Persistent database and uploads stored in a Docker volume so container updates do not erase business data

## IMPORTANT: Accurate content before public launch

The phone **(774) 291-1596**, email **gemautoworksllc@gmail.com**, Instagram handle **@gemautoworksllc**, and supplied logo/photo are from the images provided. The Facebook name "GEM Autoworks" was provided, but its exact Facebook page URL was not. Add its verified URL in Admin > Website. The existing Canva page could not reliably expose its additional photographs or service descriptions, so **no unprovided services, past customer feedback, prices, location, credentials, or results have been invented**. The three starting service names are editable consultation placeholders, not claims that GEM offers particular car services. The photo is shown as an automotive showcase, not as proof of a completed customer project.

**Before going live:** replace consultation services with your real offerings and prices, enter your confirmed business location/contact area (if public), replace/add photos with permission from their owners, and verify your timezone and weekly hours. Verify the jurisdiction-specific privacy policy and terms with an appropriate adviser. No payment processing is enabled.

## Quick setup on a Raspberry Pi (Docker + Portainer optional)

### 1. Copy and configure

```bash
unzip gem-autoworks-website.zip
cd gem-autoworks
python3 setup.py
```

The setup wizard creates `.env`, asks for admin email/password and **business timezone**, and optionally configures Gmail SMTP. Keep `.env` private. DO NOT commit `.env` to GitHub. If using Portainer's Git-stack deployment, add environment variables in Portainer instead of committing secrets. For Portainer Git-based builds, use a Docker Compose stack with a build-capable deployment or prebuild a registry image, depending on your Portainer setup.

If `python3 setup.py` fails because Python is unavailable on the Pi host, copy `.env.example` to `.env` and edit the `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` and timezone. Generate `SECRET_KEY` by running:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Initial admin password must be at least **14** characters. The database creates the first admin account on first boot. Changing `ADMIN_PASSWORD` later does **not** change the existing admin login; use Admin > Security. For a lost password, restore your admin account from a backup, or follow a controlled admin recovery procedure. Do not delete your database.

### 2. Launch

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f gem-autoworks
```

Locally on the Pi, test `curl http://127.0.0.1:8092/health` and expect `{"ok":true}`.

The web UI is served at `http://127.0.0.1:8092` ON THE PI. Because the Compose configuration binds only to loopback, other devices cannot connect via `http://PI-LAN-IP:8092`. This is intentional so you can use the Cloudflare Tunnel for public access. To inspect locally from a separate computer before connecting the tunnel, use SSH forwarding:

```bash
ssh -L 8092:127.0.0.1:8092 pi@YOUR_PI_IP
```

Then browse `http://localhost:8092` on your computer. For **local testing over HTTP only**, change `COOKIE_SECURE=false` in `.env` and restart the container (`docker compose up -d`). Restore it to `true` before publishing behind Cloudflare HTTPS.

### 3. Use your current Cloudflare Tunnel to publish a NEW subdomain

Recommended **temporary** URL: `https://gemautoworks.overvault.ca` (only after you create the route). It is independent of your existing `organizer.overvault.ca` app.

**If cloudflared runs directly on the Raspberry Pi host:**

1. Sign in to Cloudflare Dashboard > **Networking > Tunnels** and select your existing healthy tunnel.
2. Under **Routes**, select **Add route > Published application**.
3. Set hostname: **gemautoworks** + **overvault.ca**.
4. Set service type **HTTP**, URL **`localhost:8092`** (in some UIs enter `http://localhost:8092`).
5. Save. Cloudflare generally creates the necessary DNS record for a remotely-managed tunnel. Confirm DNS has the corresponding proxied CNAME if needed.
6. Test `https://gemautoworks.overvault.ca/health`, then open the homepage and `/admin/login`.

**If cloudflared runs in a Docker container on the same Pi:** `localhost` inside cloudflared points to the **cloudflared container**, not the GEM website. Attach your existing cloudflared container to GEM's Docker network, without reinstalling or replacing your existing tunnel:

```bash
docker network ls
docker ps --format 'table {{.Names}}\t{{.Image}}'
docker network connect gem-autoworks-net YOUR_EXISTING_CLOUDFLARED_CONTAINER_NAME
```

Use Cloudflare service URL **`http://gem-autoworks:8000`** instead. Make this network attachment permanent in the cloudflared container/Portainer stack network configuration, otherwise it may be lost if you recreate that container. Do **not** deploy a second cloudflared service just for this app if your existing tunnel is healthy. Your existing MLO/Organizer route should remain unchanged.

**If you manage the tunnel using a local config.yml instead of Cloudflare dashboard:** add an ingress rule ahead of the catch-all, and restart/reload cloudflared using your existing service:

```yaml
ingress:
  - hostname: organizer.overvault.ca
    service: http://YOUR_EXISTING_ORGANIZER_SERVICE
  - hostname: gemautoworks.overvault.ca
    service: http://localhost:8092       # Host-based cloudflared
  - service: http_status:404
```

This is an illustrative excerpt; **keep all your existing ingress rules, credentials, and tunnel ID**. For cloudflared in Docker, use `http://gem-autoworks:8000` instead. Local YAML changes are NOT needed for remotely managed dashboard tunnels.

### 4. Configure email notifications

Email does not work until SMTP is configured. Bookings are stored whether or not SMTP works. You can use Gmail with a Google **App Password**, assuming the account supports it:

1. Enable 2-Step Verification on the sender Gmail account.
2. Create an App Password via Google Account security settings (not your ordinary Gmail password).
3. Add the following lines to `.env` (or configure them in the wizard):

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_SECURITY=ssl
SMTP_USER=YOUR_SENDER_GMAIL@gmail.com
SMTP_PASSWORD=YOUR_GOOGLE_APP_PASSWORD
SMTP_FROM=YOUR_SENDER_GMAIL@gmail.com
```

4. Restart: `docker compose up -d`.
5. Use `/book` to make a *test* booking, then Admin > **Emails** to confirm `sent`. The owner notification goes to the editable public business email in Admin > Website (default `gemautoworksllc@gmail.com`). The customer also receives a booking email. For real-world deliverability, consider a domain-based SMTP service when you buy your own domain, with SPF, DKIM, and DMARC.

If SMTP is unavailable, messages remain pending; once configured, the worker attempts them. Failed messages can be retried in Admin > Emails. No email is sent by ChatGPT and this package does not log into a personal inbox.

### 5. Sign in, then personalize everything

Admin login: `https://gemautoworks.overvault.ca/admin/login`

- **Appointments**: confirm, cancel, complete, reschedule, create appointments manually, export CSV
- **Availability**: set weekly hours; create vacation-day overrides; block one-off periods
- **Services**: rename, add, archive, reorder, price notes, durations
- **Gallery**: upload photo files and remove gallery entries
- **Reviews**: approve or reject customer submissions before they go public
- **Website**: phone, email, Instagram/Facebook URLs, homepage copy, headings, booking rules, and hero/gallery featured image
- **Emails**: see pending, sent, or failed emails and retry failures
- **Security**: change admin password

For extra security, optionally put a **Cloudflare Access** policy on `/admin/*`, in addition to the built-in password. Make sure the path-scoped policy covers admin actions and excludes customer pages. The app itself already requires an admin session on all write endpoints.

### 6. Later: move to a brand-new domain (not overvault)

You **do not need to change the application code** when you buy a new domain. Add the domain to Cloudflare, point the registrar's authoritative nameservers to Cloudflare, wait for verification, and ensure SSL/HTTPS is enabled. Then go to your **existing tunnel > Routes > Add route > Published application**, use `www` or your chosen root hostname on the new domain, and send it to the **same** local service. You can keep both hostnames during migration. If you want apex and `www`, create appropriate hostname routes or configure an HTTPS redirect for one canonical version. Update your business profiles and outbound links after launch.

If using a Cloudflare Tunnel, there is generally **no router port-forwarding** required. Cloudflare TLS terminates public HTTPS. Keep `COOKIE_SECURE=true`. Do not open or publicly expose port `8092` in your router. Check that your new domain's DNS zone is active in Cloudflare and that SSL works before deleting the temporary hostname.

Official reference: https://developers.cloudflare.com/tunnel/get-started/ and https://developers.cloudflare.com/tunnel/concepts/routing/.

## Data persistence, backups and upgrades

All customer content, gallery uploads, reviews, and admin account data are kept in the named Docker volume `gem_data`. Back up the database and uploads, not just your Git repository. For safe SQLite backup use Docker's Python interpreter + sqlite3 backup API (do not merely copy an actively-written database file):

```bash
mkdir -p backups
# NOTE: container runs as a non-root user with /data readable

docker compose exec -T gem-autoworks python - <<'PYBACKUP' > backups/gem.sqlite3
import sqlite3,sys,tempfile
with tempfile.NamedTemporaryFile(suffix='.sqlite3') as f:
    source=sqlite3.connect('/data/gem.sqlite3')
    target=sqlite3.connect(f.name)
    source.backup(target)
    target.close();source.close()
    sys.stdout.buffer.write(open(f.name,'rb').read())
PYBACKUP
```

To save uploaded gallery photos, use `docker cp gem-autoworks:/data/uploads ./backups/uploads`. Run backups periodically to a different disk or location, encrypt them, and **test restoring them** on a non-production environment. For upgrades, take a backup then run `docker compose up -d --build`. The schema is idempotently created on boot; for future schema-changing upgrades, add explicit migrations.

To inspect logs: `docker compose logs --tail=200 gem-autoworks`.

## Security and operating limits

This is a functional self-hosted starting release, not an independently audited enterprise platform. Auth uses Argon2 password hashing, HTTPS-only session cookies when `COOKIE_SECURE=true`, CSRF tokens, content-security headers, basic throttling, sanitized data storage/rendering, upload size and format validation, and server-side appointment conflict checking. Implement Cloudflare bot controls/Turnstile and WAF rate limiting if you encounter spam. Rate limiting in this application is per process and resets after restart. SMTP retries are processed by a single app worker; run **one uvicorn process** with the provided Dockerfile.

The location is deliberately not invented. The configured default timezone `America/New_York` is a **placeholder that must be verified by the business**. No payments, SMS, Google Calendar integration, multi-staff booking, client login, or consent-management platform is claimed in this version. No social reviews or testimonials are fabricated. Appointment date/time is explicitly shown in the business timezone and currently available inventory is first-come, first-served.

## Local development & automated tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt httpx pytest
# configure .env with `python3 setup.py` then load it into environment for uvicorn
set -a; source .env; set +a
COOKIE_SECURE=false uvicorn app:app --reload --port 8092
pytest -q
```

The tests use a temporary isolated SQLite database, not your production data.
