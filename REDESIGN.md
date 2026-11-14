# Original scroll-controlled detailing draft

The homepage now plays a continuous eight-second Blender animation through native scroll. A stationary fictional coupe and a detailer progress through preparation, washing, wiping, paint reveal and finish. All scene geometry, materials and motion were authored from scratch. There are no imported models, rigs, textures, animation clips or generated storyboard inputs.

This remains an artistic draft, not an approved production-quality result. The procedural character, garment anatomy and vehicle surfacing need further specialist refinement. Cloth contact and foam progression use controlled approximations rather than physical simulations. See `production/detailing/BUILD_NOTES.md`, `SOURCES.md` and `VALIDATION.md` for editable source, provenance, checks and limitations.

Each composition has 160 rendered WebP frames: 960×600 desktop and 576×720 mobile. Playback progressively fetches nearby frames, bounds decoded memory, supports reverse scrolling and returns to normal page flow after one viewport of sticky travel. Reduced motion, reduced data, JavaScript failure and failed sequence requests retain a static fallback. No external animation library is loaded.

Homepage no longer repeats service descriptions, durations, prices, gallery imagery, reviews, contact details, or closing booking pitches. Dedicated pages own those details. Shared main navigation stays for wayfinding. Footer contains legal navigation only. Homepage has a direct booking link rather than a duplicate booking form.

The scene is a fictional illustration, not GEM staff, premises or customer work. The previous licensed car, paint/spin code and eight-image storyboard are unused. Automatic approval review blocked their deletion; they remain with their original licence notices pending direct approval. Nothing was deployed to production.
