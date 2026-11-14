---
name: GEM Autoworks
built-with: Taste kit (tasteskill 2.5.1) for public pages, Impeccable operate rules for booking, account and admin
---

# GEM Autoworks design system

## World
A detailer's site where GEM's real before/after photos and real open times do the selling. Light, cool silver-white pages
(daylight driveways, phones outdoors) with the logo's own dark graphite used where the chrome logo needs its native ground:
the nav tile, the admin rail, the booking "work order" ticket, and the plate on each car in the garage.

## Colour (`templates/base.html` :root; generated with `start.mjs brand` from the logo)
| Token | Value | Use |
|---|---|---|
| `--p-bg` | `#eef1f4` | page ground (theme-color) |
| `--p-surface` | `#e2e7ec` | alternate band (statement + plans), form panels, KPIs |
| `--p-ink` | `#0b0f14` | text, hairlines (via `--line`), dark grounds |
| `--p-muted` | `#4b5563` | secondary text (6.7:1 on bg) |
| `--p-accent` / `--p-action` | `#0b5cad` | the one accent: primary buttons, links, focus, selected choices (5.1:1 on bg, white text 6.4:1) |
| `--p-inv-bg` | `#0b0f14` | ticket, admin rail, car plate, logo tile |
| `--gem-ice` | `#8fd0f5` | the diamond's light blue, only on dark grounds (offer line on the ticket) |
| state pills | ok `#e3f1e8/#14532d`, wait `#fdf0d5/#713f12`, bad `#fbe4e4/#7f1d1d`, info `#e1ecf8/#0b3d75` | booking and plan status only |

## Type
Red Hat Display (headlines, weight 400, tracking −2.5%) and Red Hat Text (everything else, 400/500), self-hosted variable
WOFF2 in `static/fonts/`. Scale from the kit: h1 72/40, h2 48/30, lead 20, body 16/26, small 14, label 13; never under 13px.
Tabular numerals for prices, times and dates.

## Layout
- Public pages: the kit's one-section-per-screen system (`static/kit/system.css`, `layout.css`): 12 columns, 1280 wrap,
  gutters 80/24, split pair 5 + 6 (text left, picture right, start-7), sections exactly 1 or 2 screens.
- App pages (`static/css/app.css`): normal flow, `.app-grid` (form + 360px sticky summary), `.panel-box`, `.choices`, `.days`.
- Admin (`static/css/admin.css`): 232px dark rail, light work area; the rail becomes a top scroller under 900px.

## Components
- Buttons: the kit's `block` look, 44px; one filled primary per view ("Book a detail"); `btn--small` 36px in admin lists.
- Before/after `.compare`: two stacked photos, the before clipped with `clip-path`, a native range input for keyboard and
  screen readers, visible Before/After labels.
- `.ticket`: dark work-order card with perforated divider; live estimate on `/book`, static on `/booking/{token}`.
- `.bay`: a garage car card with a dark size plate.
- `.job` timeline (admin today): a dot and time per job on a 1px rule.
- Pills for status, `.notice` for page messages, `.toast` for saved states, `.empty` for empty states.

## Motion
The kit's motion layer (hover lift, button press, the hero's one entrance) plus one dealt moment: `word-highlight` on the
home statement. Page CSS uses `--ease-out: cubic-bezier(.23,1,.32,1)`, transitions ≤ 300ms on transform/opacity/colour,
toasts with `@starting-style`. Everything rests under `prefers-reduced-motion`.

## Imagery
Only GEM's own photographs (Instagram originals at 1440/960/480 WebP, `scripts/build_images.py`); uploads are resized to
WebP at 480/960/1600 with EXIF stripped. No stock, no captions under pictures, alt text on every content photo.
Provenance: `assets-src/` files come from GEM Autoworks' Instagram posts (Sep–Nov 2026) and the v1 site's owner photo.
