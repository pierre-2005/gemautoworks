"""Resumable Blender rendering. Usage: blender -b scene.blend -P render.py -- preview|final."""
import bpy,sys,json,time,struct,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
mode=sys.argv[-1] if '--' in sys.argv else 'preview'
s=bpy.context.scene
s.render.resolution_percentage=100;s.render.use_persistent_data=True
s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB'
s.cycles.use_denoising=True;s.cycles.device='GPU';s.cycles.adaptive_min_samples=8
prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.refresh_devices()
for device in prefs.devices:device.use=device.type=='OPTIX'
preview=mode.startswith('preview')
jobs=[('desktop',480,300,80,12)] if preview else [('desktop',960,600,160,32),('mobile',576,720,160,32)]
started=time.time()
revision=hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest()
for composition,w,h,count,samples in jobs:
    s.camera=bpy.data.objects['CAM-'+composition];s.render.resolution_x=w;s.render.resolution_y=h;s.cycles.samples=samples
    folder=ROOT/(mode+'-frames' if preview else 'masters')/composition;folder.mkdir(parents=True,exist_ok=True)
    for index in range(count):
        path=folder/f'{index:03d}.png'
        stamp=path.with_suffix('.revision')
        if path.exists() and path.stat().st_size>1000 and stamp.exists() and stamp.read_text()==revision:
            with path.open('rb') as existing:header=existing.read(24)
            if len(header)==24 and struct.unpack('>II',header[16:24])==(w,h):continue
        sourceframe=1+191*index/(count-1)
        whole=int(sourceframe);s.frame_set(whole,subframe=sourceframe-whole)
        s.render.filepath=str(path);bpy.ops.render.render(write_still=True)
        stamp.write_text(revision)
        (ROOT/'render-progress.json').write_text(json.dumps({'mode':mode,'composition':composition,'index':index,'count':count,'elapsed_seconds':round(time.time()-started,1)}))
        print(f'GEM_RENDER {composition} {index+1}/{count}',flush=True)
(ROOT/f'{mode}-complete.json').write_text(json.dumps({'completed':True,'elapsed_seconds':round(time.time()-started,1),'jobs':jobs}))
