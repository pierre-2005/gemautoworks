"""Blender-side proof renders before final sequence production."""
import bpy
from pathlib import Path
ROOT=Path(__file__).resolve().parent
s=bpy.context.scene
assert s.camera is not None
s.cycles.samples=32
s.render.resolution_percentage=100
for composition,size in [('desktop',(640,400)),('mobile',(400,500))]:
    s.camera=bpy.data.objects['CAM-'+composition]
    s.render.resolution_x,s.render.resolution_y=size
    folder=ROOT/'validation'/composition;folder.mkdir(parents=True,exist_ok=True)
    for frame in [1,25,49,72,90,115,140,160,177,192]:
        s.frame_set(frame);s.render.filepath=str(folder/f'{frame:03d}.png')
        bpy.ops.render.render(write_still=True)
        print(composition,frame,flush=True)
s.camera=bpy.data.objects['CAM-desktop'];s.render.resolution_x=1280;s.render.resolution_y=800
