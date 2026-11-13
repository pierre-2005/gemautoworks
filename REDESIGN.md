Service website. Primary action: Book an appointment.

The user's follow-up explicitly requested an advanced 3D supercar opening with scroll-driven perspective changes. This overrides Taste's default photography-only service page and one-screen rhythm. The final opening uses the CC BY 4.0 Car Concept by Eric Chadwick / DGG, rather than claiming a Koenigsegg model or offering a car for sale.

Brand palette: ivory #f5f5f1, carbon #14191c, original GEM electric blue #1264df. Taste pairing: Schibsted Grotesk. Initial hero deal: photo; overridden by the explicit 3D brief. Moment deal: word-highlight. No background shaders, scenes unrelated to the car, animated statistics, or autoplay loops.

Voice: direct editorial. Verified appointment types and business contact details retained. No fabricated proof or promises. The original logo and showcase remain; CMS headline, introduction, about title and featured photograph remain editable.

Features: native-scroll 3D orbit and opening doors, paint swatches, static fallback and reduced motion, gallery lightbox with keyboard controls, live booking summary, calendar retry state, conflict recovery without losing details, submit feedback, FAQ, accessible mobile navigation, preserved admin workflows.

Model: same-origin external glTF, BIN and WebP textures. This avoids blob URLs and preserves the existing Content Security Policy. Quantized, simplified geometry; render-on-demand; capped pixel ratio; off-screen and hidden-tab work suspended. GZip middleware compresses assets and HTML. Full upstream attribution: static/licenses/3d-model.txt.

Photography: two Unsplash editorial inspiration frames, downloaded and inspected at full size. Original client showcase retained. Stock frames are not placed in the customer gallery. No business facts assumed.

Verification:
- Python: 4 passed. One upstream Starlette/AnyIO deprecation warning.
- JavaScript syntax: passed.
- Browser: seven public/admin-login routes checked at 320, 390, 768, 1024 and 1440px. No horizontal overflow or unnamed buttons.
- Browser interactions: scroll rotation, opening doors, paint change, successful synthetic booking on isolated preview data, gallery dialog, mobile menu and Escape behavior, admin login and dashboard tabs.
- Final 3D textures loaded successfully with no console errors or warnings.
- Desktop and phone screenshots saved locally under visual-artifacts.

GATE: ERROR. The Taste scripts could not launch their Chrome instance. Automated consistency, layout, performance and copy checks did not complete; no pass is claimed for them. The instruction was to report the error without rerunning. Browser QA was completed through the connected browser instead. No checker waivers were used.

The Impeccable context/concept launcher could not run in the initial sandbox; product truth, source and the live site were inspected directly. No workflow preference inferred from silence.

Deployment: existing Docker/Portainer architecture retained. Pull requests run test/browser CI without publishing images. A merge to main builds the production image; Portainer must pull and redeploy it. No production database is part of this checkout.
