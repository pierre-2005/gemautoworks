# Original GEM detailing animation

All geometry, procedural surface materials, pose trajectories, cloth deformation and foam masks in `gem_detailing.blend` were authored for this project. No downloaded car, character, rig, texture, HDRI, animation clip or generated storyboard is used in this scene. Blender 5.3.0 and the installed Blender MCP drive construction, inspection and rendering. Blender and Python are tools, not asset sources.

This is an original, stylized procedural scene. It does not depict GEM's employees, workshop or customer vehicles. It is an unbranded fictional coupe. No manufacturer affiliation is suggested. The legacy licensed concept car remains elsewhere in the repository, with its original licence; the homepage does not use it.

## Production contract

Fixed cameras; stationary car; 192 source frames at 24 fps (eight seconds). Prepare 1–25; wash 26–71; reposition 72–90; wipe/reveal 91–161; lift/finish 162–192. The character's feet and torso remain planted. Each arm uses a fixed-length two-segment reach solver. Sleeves, glove curvature and towel deformation are baked as shape keys; hand and cloth positions are keyed. The .blend needs no Python handler to play or render. Armature landmarks are inspection guides, not a fully skinned character rig.

The hood, glove contact and towel share one analytic surface, including the fender crown. The foam is part of the actual paint material, with animated world-coordinate deposition and removal boundaries. There are no image crossfades or texture swaps. An inexpensive spatial mask replaces a fluid simulation. Droplets and a physically simulated fabric are not included.

## Rebuild and resume

The build entry point replaces the current Blender scene. Use it only in the dedicated GEM scene:

```python
import runpy
runpy.run_path('/absolute/path/to/production/detailing/build.py', run_name='__main__')
```

`common.py`, `car.py`, `character.py`, `action.py` and `studio.py` are the editable source. Save the result as `gem_detailing.blend`. All surfaces are procedural; there are no linked texture dependencies. Intermediate versions remain locally as `gem_detailing_v*.blend`, outside Git.

```text
blender -b gem_detailing.blend -P render.py -- preview
blender -b gem_detailing.blend -P render.py -- final
python package_assets.py
```

`render.py` skips completed PNGs of the expected size and records progress, so interrupted jobs resume. Final rendering emits 160 sampled frames per composition, equivalent to 20 fps over eight seconds. Delivery masters are 960×600 desktop and 576×720 mobile, rendered at 32 adaptive samples with denoising. The website receives WebP frames; lossless PNG masters remain local under `masters/`. The editable scene can render larger masters. Render with Cycles/OptiX on the available RTX 4060. Preview uses reduced size and samples.

## Quality record

Early previews exposed blunt nose geometry, canopy gaps, washed-out paint, a floating cloth and paper-like foam. Subsequent passes closed glazing, narrowed softboxes, unified the hood/contact surface and put foam into the paint shader. A fused jacket skinning experiment produced poor deformation and was rejected; it is absent from the delivered source. The retained sleeves are deterministically baked. Contact sheets and frame differences are in `validation/`.

Remaining visual limits are significant: the procedural character, gloves and workwear remain stylized; cloth folds and surface foam are controlled approximations. This does not yet meet the requested photorealistic, production-quality character standard. A character artist and animator should refine original garment anatomy, pose performance and fine contact before production approval. Do not mistake a successful render or browser test for artistic acceptance.
