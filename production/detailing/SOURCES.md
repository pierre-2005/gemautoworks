# Asset sources and dependencies

| Asset | Source | External asset licence |
| --- | --- | --- |
| Fictional midnight-blue coupe, wheels, glazing and trim | Original geometry in `car.py` | No third-party model used |
| Fictional detailer, clothes, shoes, cap and five-finger gloves | Original geometry in `character.py` | No third-party character or rig used |
| Microfiber towel and its deformations | Original surface and baked shape keys in `action.py` | No downloaded fabric mesh or simulation cache |
| Foam progression and paint reveal | Original procedural material mask in `action.py` | No texture pack or image sequence used as input |
| Paint, glass, rubber, workwear, fabric and studio floor | Original Blender procedural materials | No external texture files |
| Studio, cameras and softboxes | Original setup in `studio.py` | No HDRI or studio scene imported |
| Rendered frames, final posters and preview | Rendered from `gem_detailing.blend` | No stock footage or generated storyboard used |

Blender 5.3, Python, Pillow and FFmpeg are production tools. The installed Blender MCP controls the scene. Website playback uses native browser APIs and introduces no animation-library dependency.

The GEM logo, pre-existing website photographs and font remain separate website assets. If the complete animation directory fails to load, the player uses the site's existing automotive photograph as an emergency fallback. That photograph is not part of the original 3D scene.

The repository's old concept-car model, Three.js bundle, paint controls and eight-picture storyboard remain unreferenced legacy files. Their existing attribution and licence notices remain intact. They were not used to build this scene. Automatic approval review rejected deleting those tracked legacy assets during this task.

The scene is a fictional illustration. It does not depict GEM employees, premises or customer work, and carries no vehicle-manufacturer branding or affiliation.
