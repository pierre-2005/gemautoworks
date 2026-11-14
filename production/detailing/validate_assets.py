"""Validate every rendered frame and produce compact, inspectable final contact sheets."""
from pathlib import Path
from PIL import Image,ImageChops,ImageStat,ImageDraw
import hashlib,json,statistics

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'validation'
OUT.mkdir(exist_ok=True)
revision=hashlib.sha256((ROOT/'gem_detailing.blend').read_bytes()).hexdigest()
report={'source_revision':revision,'compositions':{},'artistic_approval':False,
    'remaining_limits':['Stylized procedural character and garment anatomy require specialist refinement.',
                        'Controlled cloth and foam approximations; no fluid or cloth simulation.']}

def contact(folder,indices,name,cols=5):
    cell=(240,190 if folder.name=='desktop' else 310)
    sheet=Image.new('RGB',(cols*cell[0],((len(indices)+cols-1)//cols)*cell[1]),'#0b1116')
    for i,index in enumerate(indices):
        with Image.open(folder/f'{index:03d}.png') as image:
            im=image.convert('RGB');im.thumbnail((cell[0],cell[1]-22),Image.Resampling.LANCZOS)
            x=(i%cols)*cell[0];y=(i//cols)*cell[1]
            sheet.paste(im,(x+(cell[0]-im.width)//2,y+22))
            ImageDraw.Draw(sheet).text((x+8,y+5),f'{index:03d} / source {1+191*index/159:.1f}',fill='#dce5ec')
    sheet.save(OUT/name,quality=90)

for variant,size in [('desktop',(960,600)),('mobile',(576,720))]:
    folder=ROOT/'masters'/variant
    frames=[folder/f'{i:03d}.png' for i in range(160)]
    if not all(p.is_file() for p in frames):raise RuntimeError(f'{variant}: incomplete render')
    hashes=set();differences=[];stable=[];previous=None;previous_corner=None
    for index,p in enumerate(frames):
        if p.with_suffix('.revision').read_text()!=revision:raise RuntimeError(f'{p.name}: stale source revision')
        hashes.add(hashlib.sha256(p.read_bytes()).hexdigest())
        with Image.open(p) as original:
            if original.size!=size:raise RuntimeError(f'{p}: unexpected dimensions {original.size}')
            image=original.convert('RGB')
        corner=image.crop((int(size[0]*.85),int(size[1]*.85),size[0],size[1]))
        if previous is not None:
            differences.append({'index':index,'mean_rgb_difference':round(statistics.mean(ImageStat.Stat(ImageChops.difference(previous,image)).mean),4)})
            stable.append(statistics.mean(ImageStat.Stat(ImageChops.difference(previous_corner,corner)).mean))
        previous=image;previous_corner=corner
    largest=sorted(differences,key=lambda r:r['mean_rgb_difference'],reverse=True)[:8]
    if len(hashes)<140:raise RuntimeError(f'{variant}: insufficient unique temporal samples')
    report['compositions'][variant]={'frames':160,'dimensions':list(size),'unique_pngs':len(hashes),
        'largest_frame_differences':largest,'median_difference':round(statistics.median(d['mean_rgb_difference'] for d in differences),4),
        'static_corner_max_difference':round(max(stable),4),
        'master_bytes':sum(p.stat().st_size for p in frames)}
    (OUT/f'final-{variant}-frame-differences.json').write_text(json.dumps(differences,indent=2)+'\n')
    contact(folder,[0,21,40,59,75,95,116,132,146,159],f'final-{variant}-contact.jpg')
    contact(folder,[19,21,23,57,59,61,73,75,77,132,134,136,150,153,156],f'final-{variant}-transitions.jpg')

(OUT/'quality-gates.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
