# Validation — 13 November 2026

## Status and provenance

Functional integration and render delivery pass the checks below. Artistic approval is **false**. The procedural character and garments remain stylized; vehicle surfacing, hand anatomy and fabric need specialist refinement before this can meet the requested production-quality realism. Cloth and foam use controlled deformations and material masks, not physical simulation. No droplets are simulated. This is a reviewable original draft, not a finished photoreal commercial.

Every 3D asset and animation input was built from scratch in this project. No downloaded model, rig, texture, HDRI, clip or generated storyboard is used. See `SOURCES.md`. The emergency website photograph is a separate pre-existing website asset.

## Render and delivery

The editable `.blend` contains eight seconds of keyed motion, with no Python playback handlers or external textures. Both fixed-camera compositions contain 160 unique frames at 20 delivery fps. All 320 master dimensions and source-revision stamps were verified. Lossless masters remain local and ignored; rebuilding instructions and editable source are supplied.

| Delivery | Dimensions | Complete frame payload |
| --- | --- | --- |
| Desktop WebP | 960×600 | 2,843,282 bytes |
| Mobile WebP | 576×720 | 1,828,838 bytes |
| Review MP4 | 960×600, 8 seconds | 756,253 bytes |

Posters are additional small files. Native playback requests nearby frames and a few key poses, rather than downloading every frame first. Phones request only the mobile composition. A 14-bitmap cache retains about 32.3 MB desktop or 23.2 MB mobile raw RGBA pixels, excluding canvas, browser overhead and one transient decode. Browser instrumentation measured 14 retained and at most 15 live bitmaps. Measured JS heap was about 3 MB; this is not total GPU/browser memory.

The final video was evaluated in Chrome: 160 presented frames, three dropped during concurrent browser work, no reverse-time anomalies; six direct seeks measured 3.6–27.8 ms. Video is smaller and was competitive. Canvas was retained for deterministic reverse access to cached frames and progressive per-composition fetching. This does not establish that video is inherently slower.

## Visual inspection

Desktop/mobile contact sheets and transition sheets were rendered and inspected. Ten sampled mobile poses keep the glove and cloth inside the camera frame. Seven contact probes found a minimum 2.43 mm cloth/hood clearance. This checks sampled analytic geometry; it does not certify every intersection or physical fabric behavior. Stable-corner adjacent-frame differences stayed below 0.18/255 mean RGB. See `validation/quality-gates.json`, `contact-validation.json`, `final-framing.json` and the contact sheets.

## Browser and application checks

Automated real-browser checks passed in Chrome 157.0.8103.78 and Edge 157.0.4341.46 against an isolated local FastAPI server and database. Tests cover forward/reverse scroll, jumps, resizing, phone portrait/landscape, overflow, keyboard access, live reduced-motion changes, Save-Data, disabled JavaScript, delayed frames, failed frames/manifest, and failure of the entire animation directory. Booking availability, invalid submission, local confirmation and admin navigation passed. No captured JavaScript or CSP violations occurred.

Cached scroll-to-frame changes measured 4.6–6.1 ms in Chrome and 1.3–4.9 ms in Edge in this run. These are local cached measurements, not field performance guarantees. The phone scenario fetched 228,042 transferred bytes (288,800 encoded resource bytes including cached responses); desktop Chrome fetched 984,031 transferred bytes. These scenarios traverse selected positions, not all frames. See `validation/final-browser-report.json` for exact samples.

Python: four tests pass, including booking conflicts, availability, CSRF, review moderation and admin settings. JavaScript syntax and `git diff --check` pass. Safari/WebKit, Firefox and physical phones were unavailable and were not tested. The live public domain returned a Cloudflare Tunnel error during inspection; production was not modified.

## Design gate and remaining work

The Taste design checker returned **FAIL: 24 findings, round 1**. Findings include its prohibition on sticky sections, screen-height/empty-area heuristics, repeated CTA expectations, compact-footer geometry, inherited text-only introduction, mobile heading scale, and its stricter 7:1 body-contrast target (measured 5.48:1, above WCAG AA normal-text contrast). Some conflict with this brief's bounded sticky animation and single booking CTA; others remain design polish work. No blanket design-gate approval is claimed.

The previous model, spin/paint code and storyboard are unused. Automatic approval review blocked deleting 24 tracked legacy files; `LEGACY_CLEANUP.md` records the pending cleanup. Their licence notices remain. The PR stays a draft. No merge or production deployment was performed.
