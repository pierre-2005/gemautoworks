"""Fixed cameras and broad photographic softboxes; no downloaded environments."""
from common import *

def build_studio():
    floor=material('studio_graphite',(.007,.009,.012),.42)
    microtexture(floor,90,.06,.0006)
    cube('studio_floor',(0,0,-.048),(200,200,.09),floor,.01)
    for name,loc,target,power,size,sy,color in [
        ('key_softbox',(-3,1,4.5),(0,-.8,.7),650,3,.45,(.94,.97,1)),
        ('long_reflection',(3,2,4),(0,0,.8),750,.35,4,(1,.97,.93)),
        ('front_fill',(1,-4,2.4),(0,-.8,.7),120,3,2,(.92,.96,1)),
        ('far_rim',(-3,2,3),(0,0,.8),400,.6,3,(.93,.96,1))]:
        d=bpy.data.lights.new('LGT-'+name,'AREA');d.energy=power;d.shape='RECTANGLE';d.size=size;d.size_y=sy;d.color=color
        if name=='front_fill':d.specular_factor=0
        o=bpy.data.objects.new('LGT-'+name,d);bpy.context.collection.objects.link(o);o.location=loc;aim(o,target)
    for name,loc,target,lens,shift in [
        ('desktop',(1.9,-3.9,2.85),(-.28,-1.25,.80),78,0),
        ('mobile',(1.4,-3.3,3.2),(-.37,-1.18,.78),47,.08)]:
        d=bpy.data.cameras.new('CAM-'+name);d.lens=lens;d.sensor_width=36;d.shift_x=shift
        if name=='mobile':d.sensor_fit='VERTICAL';d.sensor_height=24;d.shift_y=-.16
        o=bpy.data.objects.new('CAM-'+name,d);bpy.context.collection.objects.link(o);o.location=loc;aim(o,target)
        d.dof.use_dof=False
    bpy.context.scene.camera=bpy.data.objects['CAM-desktop']

def save_scene(name='gem_detailing_v01.blend'):
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/name))
    print('Saved editable scene',ROOT/name)
