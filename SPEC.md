# GEM Autoworks — Website v2 Spec

## Goal
Turn GEM Autoworks' web presence into the place customers **book, rebook and manage** their detailing — not just a brochure. Every page should push toward one action: *Book a detail*. Returning customers should be able to sign in, keep their cars in a garage, and put a car on a recurring cleaning plan in under a minute.

## The business (verified from Instagram + Canva site, Nov 2026)
- **GEM Autoworks LLC** — mobile auto detailing, Central Massachusetts. Tagline: **"Your Car. Our Craft."** Secondary line: "Passion Drives Detail."
- Owner: **Pavly**, 23. Started GEM to combine his passion for cars with serving his community.
- Contact: (774) 291-1596 · gemautoworksllc@gmail.com · @gemautoworksllc · Facebook "GEM Autoworks"
- Offer: **10% off your first detail** (toggleable in admin).
- Packages (prices by vehicle size: Sedan/Coupe · SUV/Crossover · Large SUV/Truck):
  - **Exterior Detail** — $89 / $99 / $109 — hand wash, non-contact wheel clean + tire shine, door jambs, exterior glass & mirrors, microfiber hand dry, exterior trim.
  - **Interior Detail** — $119 / $139 / $159 — full vacuum incl. trunk, carpets & mats, seats (cloth/leather), dash/console/doors, cup holders/vents/crevices, wipe & sanitize, interior glass, leather clean & condition, light stain treatment, protectant.
  - **GEM Detail** (interior + exterior) — $179 / $199 / $219.
  - "Pricing may vary based on vehicle condition and distance."
- Real work photos: Kia K5, Nissan Altima (before/after), Altima console (before/after), Ford F-150 (before/after), Infiniti G37, Jeep Grand Cherokee. Owner photo with McLaren Senna (used in the About section).

## Audience
1. **New local customers** (phone, from Instagram/Google) — need trust fast: real work, clear prices, easy booking.
2. **Repeat customers** — want to rebook in two taps and set a recurring schedule.
3. **Pavly (admin)** — runs everything from his phone: today's jobs, addresses, confirmations, prices, photos.

## Pages
| Public | Purpose |
|---|---|
| `/` Home | Hero (logo mark, tagline, Book CTA), proof strip (before/after), packages with size toggle, how it works (3 steps), recurring-plan pitch, about Pavly, reviews, Instagram strip, service area, final CTA |
| `/services` | Full package detail, size-based price matrix, add-ons, what's included checklist, FAQ |
| `/work` | Gallery of before/after drag sliders + photo grid (admin-managed) |
| `/about` | Pavly's story + owner photo, values |
| `/book` | Multi-step booking (works signed-in or as guest) |
| `/contact` | Contact form, phone/text/email/IG, service area, hours |
| `/reviews` | Approved reviews + leave-a-review form |
| `/privacy`, `/terms` | Legal |
| **Account** | |
| `/account/signup`, `/login`, `/forgot`, `/reset` | Customer auth |
| `/account` | Dashboard: next appointment, garage, plans, history, profile, saved addresses |
| `/account/garage` | Add/edit/remove vehicles |
| `/account/plans` | Create/pause/cancel recurring plans |
| **Admin** (`/admin`) | Today/week agenda, calendar, appointments, customers, plans, services & pricing, add-ons, availability, service mode, gallery & before/after, reviews, Instagram posts, messages, site content & offer, emails, security |

## Key features
- **Service mode switch (admin):** `Mobile` / `Shop` / `Both`. Drives the booking flow (address field vs. shop address vs. customer choice), copy across the site, and the service-area block. Shop address, service-area towns and a travel note are editable.
- **Pricing matrix:** each service has price + duration per vehicle size; add-ons with optional price/duration. Booking shows a live estimate (with first-detail discount when eligible).
- **Booking flow:** Package → Vehicle (pick from garage or enter year/make/model/size) → Where (per service mode) → Date & time (real availability, duration-aware, no double-booking) → Details/confirm. Guest checkout allowed; offer "create an account to save this car" after booking.
- **Accounts & garage:** email + password (Argon2), sessions, password reset by email. Vehicles: nickname, year, make, model, color, size class, notes. Saved addresses.
- **Recurring plans:** customer picks car, package, frequency (every 2 / 4 / 6 / 8 weeks), preferred weekday + time window, address. Admin approves; the system keeps the next 3 visits booked, skips conflicts and flags them for admin. Customer can pause, skip one visit, or cancel.
- **Customer self-service:** cancel or reschedule up to a cutoff (admin setting, default 24h).
- **Notifications:** email to owner + customer on booking, change, cancel, plan approval, reminder 24h before (via existing SMTP outbox with retries).
- **Contact form:** stored in admin inbox + emailed; honeypot + rate limit.
- **Instagram section:** curated posts managed in admin (image, caption, link) seeded with the real posts. Instagram's official API requires a Business account + Meta app token, so it's an optional upgrade, not a dependency.
- **Payments:** none in v2 (pay in person). Data model leaves room for Stripe later.

## Data (SQLite, new file `gem_v2.sqlite3` in the existing `/data` volume)
`settings` · `admins` · `customers` · `vehicles` · `addresses` · `services` · `service_prices (service, size, price, minutes)` · `addons` · `hours` · `date_overrides` · `blocks` · `appointments (customer?, vehicle snapshot, service, size, addons, location type/address, start, end, status, price estimate, plan?)` · `plans` · `reviews` · `gallery (single or before/after pair)` · `instagram_posts` · `messages` · `email_outbox` · `password_resets`.

**Live data safety:** the old `gem.sqlite3` is left untouched. On first boot v2 imports the old admin login, appointments, reviews and gallery uploads into the new file, so rollback is just redeploying the old image.

## Non-goals (v2)
Online payments, SMS, native app, multi-staff scheduling, Google Calendar sync.

## Quality bar
Responsive 360→1440+, keyboard accessible, WCAG AA contrast, no layout shift, optimized responsive images, working forms with clear errors and empty states, reduced-motion support, tests (pytest + Playwright screenshots at 390 and 1440), independent code review with findings fixed.
