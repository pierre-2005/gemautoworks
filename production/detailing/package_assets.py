"""Keep full-quality PNG masters separate; publish only bounded WebP sequences."""
from pathlib import Path
from PIL import Image
import json,sys,hashlib

ROOT=Path(__file__).resolve().parent
OUT=ROOT.parents[1]/'static'/'detailing'
manifest={'version':1,'duration':8,'count':160,'variants':{}}
desktop_preview='--desktop-preview' in sys.argv
revision=hashlib.sha256((ROOT/'gem_detailing.blend').read_bytes()).hexdigest()
for variant in (('desktop',) if desktop_preview else ('desktop','mobile')):
    source=ROOT/'masters'/variant
    frames=sorted(source.glob('*.png'))
    if len(frames)!=160:raise RuntimeError(f'{variant}: expected 160 masters, found {len(frames)}')
    if not all(p.with_suffix('.revision').read_text()==revision for p in frames):
        raise RuntimeError(f'{variant}: source revision mismatch')
    destination=OUT/variant;destination.mkdir(parents=True,exist_ok=True)
    for frame in frames:
        with Image.open(frame) as im:
            im.save(destination/(frame.stem+'.webp'),quality=78 if variant=='desktop' else 76,method=6)
    for name,index in [('poster',0),('finish',159)]:
        with Image.open(frames[index]) as im:im.save(destination/(name+'.webp'),quality=86,method=6)
    manifest['variants'][variant]={'width':im.width,'height':im.height,'path':f'/static/detailing/{variant}/',
        'frameBytes':sum(p.stat().st_size for p in destination.glob('[0-9]*.webp'))}
if desktop_preview:
    # Local production review only. The complete packaging pass replaces this
    # once the separate phone render finishes; failed phone frames retain its poster.
    manifest['variants']['mobile']={'width':576,'height':720,'path':'/static/detailing/mobile/','frameBytes':None}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,indent=2))
