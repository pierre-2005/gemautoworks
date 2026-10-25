# GEM Autoworks — Website V2

Self-hosted luxury automotive website, booking calendar, optional customer accounts, and business administration. Runs on FastAPI, Jinja2, SQLite and Docker (Raspberry Pi ARM64 or AMD64) behind Cloudflare Tunnel.

## Public website
The site retains the original GEM logo, contact details and supplied automotive photos with a unified black-and-electric-blue design. There is just one maintained stylesheet at static/css/site.css. The hero photograph fades smoothly into the left-side background. The responsive site includes Home, Services, Gallery, Reviews, Contact, Booking, Privacy, Terms and a private Admin workspace. The four-stage booking flow walks customers through service, availability, details and final review. Booking slot checks are authoritative on the server; reservations use serialized transactions to prevent double booking.

## Optional customer portal
The portal is **disabled by default**. After configuring working SMTP, open Admin → Website → Customer account access, enable it and save. Disabling it hides the public login button and makes customer account routes inaccessible, without deleting existing data.

Customers can register, provide vehicle details at signup (and add additional vehicles later), verify their email through a two-hour one-time link, sign in, reset passwords, maintain a multi-vehicle garage, update profile details, and book using a saved vehicle. Their dashboard shows linked appointments and lets them reschedule or cancel at least 24 hours before their appointment, subject to available hours and current availability. Anonymous customers can still book without an account.

Admin creates and edits service-linked recurring plans, with intervals from 1 to 60 months. Customers can enroll or cancel reminders. Admin can assign plans to customers' saved vehicles, set due dates, deactivate plans, and mark service complete. Reminder messages are queued around 30 days, seven days, and the due date. A plan is a reminder program: **no payment, subscription charge or appointment reservation is created automatically**.

Account passwords use Argon2, verification and password reset links are hashed and expire after two hours, sessions are signed, forms are CSRF-protected, and access to account records is filtered by the authenticated customer's ID. Keep your Cloudflare WAF and security updates active; basic built-in rate limiting is not a replacement for external bot protection.

## Business administration
Open /admin/login with existing administrator credentials. You can filter bookings by customer, reference, email, vehicle, or status; approve, reschedule, cancel, complete, or create appointments; update availability, holidays, blocked hours, services and prices; upload gallery photos; moderate reviews; edit page text, hero image, contact details, SEO description and site settings; toggle customer registration; manage customers and care-plan assignments; change the admin password; inspect email status, retry failed messages and send an SMTP test.

Routine customer, service, calendar, content and plan administration should not require editing code.

## SMTP: send customer and owner emails

For the existing Gmail business address, you do not need to run a mail server on the Raspberry Pi. Turn on Google 2-Step Verification, then create an app password at https://myaccount.google.com/apppasswords. Do not use your normal Gmail password.

Open Portainer → Stacks → GEM Autoworks → Environment variables and enter:

| Variable | Value |
|---|---|
| SMTP_HOST | smtp.gmail.com |
| SMTP_PORT | 465 |
| SMTP_SECURITY | ssl |
| SMTP_USER | Your complete Gmail address |
| SMTP_PASSWORD | Your 16-character Google app password |
| SMTP_FROM | The same Gmail address |
| PUBLIC_BASE_URL | https://gemautoworks.overvault.ca |
| BUSINESS_TIMEZONE | Your confirmed local business timezone |

Also ensure SECRET_KEY (32+ random characters), ADMIN_EMAIL and ADMIN_PASSWORD (initial first-run setup) are present. Keep COOKIE_SECURE=true for Cloudflare HTTPS. Do not commit secrets to GitHub or use an unverified custom sending domain.

Recreate the container from Portainer so the environment changes apply. Then go to Admin → Emails → Send test email. Verify that the message reaches the configured public business email and examine the delivery log. A queued message is not proof of delivery.

New bookings enqueue an owner email and a customer email. Status changes, customer cancellations/reschedules, verification links, password resets and recurring plan notices also use the queue. SMTP messages include a plain-text and styled HTML version. Delivery failures are retried with backoff, and failed items can be manually retried from Admin → Emails. For production business growth, consider a dedicated transactional email provider with proper SPF, DKIM and DMARC.

## Protect production data before any V2 deployment

The GHCR image is ghcr.io/pierre-2005/gemautoworks:latest, built and pushed by GitHub Actions only after checks on main. A pull-request branch is not published as the production image. Portainer Git polling does not always pull a changed image when the image tag stays latest; manually re-pull and redeploy as appropriate.

**Back up SQLite and uploads first.** On the Raspberry Pi:

~~~bash
docker exec gem-autoworks python -c "import sqlite3; a=sqlite3.connect('/data/gem.sqlite3'); b=sqlite3.connect('/data/gem-before-v2.sqlite3'); a.backup(b); b.close(); a.close()"
docker cp gem-autoworks:/data/gem-before-v2.sqlite3 ./gem-before-v2.sqlite3
docker cp gem-autoworks:/data/uploads ./gem-uploads-before-v2
~~~

Store these backups somewhere else too. Never remove or rename the existing gem_data Docker volume. The V2 app uses additive SQLite schema changes, retaining existing appointments and uploads.

After the V2 pull request is reviewed and checks pass: merge to main, confirm GitHub Actions successfully published both ARM64 and AMD64 images, pull the new GHCR image in Portainer, then redeploy the same stack with the same Docker volume and environment. Verify /health, public pages, old appointments, existing uploads, account toggle, test emails and a real test booking.

Keep the existing Cloudflare route for gemautoworks.overvault.ca unchanged. If cloudflared runs on the Pi host the target is usually http://localhost:8092; if it shares GEM's Docker network the target is http://gem-autoworks:8000.

## Testing
Python functional and account flow regression tests plus real Chromium responsive checks run in GitHub Actions. Responsive tests cover 320, 360, 390, 768, 1024, 1440 and 1920 pixel widths, public routes, customer onboarding/login, the booking wizard, admin navigation and horizontal overflow. GitHub Actions uploads a temporary ZIP of preview screenshots for review.

Run locally after installing project requirements, pytest, httpx and Playwright Chromium:

~~~bash
python -m pytest -q
python tests/visual_smoke.py
~~~

The tests are not a guarantee of every device and browser combination. Also test a physical smartphone, tablet and desktop, and confirm delivery from real SMTP before opening registration.

## File layout
- app.py: public routes, admin, booking logic and delivery worker.
- customer_portal.py: customer accounts, garages, recurring plans and reminders.
- templates/: marketing, booking, admin and customer pages.
- static/css/site.css: single responsive stylesheet.
- static/js/site.js: mobile menu, booking stages, admin and account controls.
- static/img/: original GEM logo and photos.
- tests/: unit, integration and headless browser checks.
- docker-compose.yml, Dockerfile: ARM64/AMD64 GHCR and persistent data.
- .github/workflows/publish.yml: checks, screenshots and production image publishing.

## Important limitations
Changing ADMIN_PASSWORD in Portainer after first boot does not reset an existing admin password; use Admin → Security. Keep SECRET_KEY stable or existing sessions will be logged out. Verify actual service offerings, business hours, price notes, privacy policy, location and business timezone before going live. This project does not offer payment collection, recurring charges or automatic calendar booking for a recurring care plan, nor does it provide legal or business compliance certification.
