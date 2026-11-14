"""Original GEM cinematic assets. Geometry and shaders authored for this project."""
import bpy
import math
from mathutils import Vector
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def material(name, color, roughness=.4, metal=0, coat=0):
    m = bpy.data.materials.new('MAT-' + name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    for key, value in {'Base Color': (*color, 1), 'Roughness': roughness,
                       'Metallic': metal, 'Coat Weight': coat, 'Coat Roughness': .075}.items():
        b.inputs[key].default_value = value
    return m

def mesh(name, verts, faces, mat=None):
    data = bpy.data.meshes.new('MESH-' + name)
    data.from_pydata(verts, [], faces)
    data.update()
    obj = bpy.data.objects.new('GEO-' + name, data)
    bpy.context.collection.objects.link(obj)
    if mat: data.materials.append(mat)
    for p in data.polygons: p.use_smooth = True
    return obj

def grid(name, nu, nv, fn, mat):
    return mesh(name, [fn(i/nu,j/nv) for i in range(nu+1) for j in range(nv+1)],
        [(i*(nv+1)+j,(i+1)*(nv+1)+j,(i+1)*(nv+1)+j+1,i*(nv+1)+j+1)
         for i in range(nu) for j in range(nv)], mat)

def bevel(obj, width=.015, segments=3):
    mod=obj.modifiers.new('Manufactured edge radius','BEVEL')
    mod.width=width; mod.segments=segments
    return obj

def cube(name, loc, scale, mat, radius=.015):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o=bpy.context.object; o.name='GEO-'+name; o.scale=scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(mat)
    bevel(o,radius)
    return o

def ellipsoid(name, loc, scale, mat, segments=32, rings=20):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=loc)
    o=bpy.context.object; o.name='GEO-'+name; o.scale=scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(mat)
    for p in o.data.polygons:p.use_smooth=True
    return o

def curve(name, points, radius, mat, cyclic=False):
    d=bpy.data.curves.new('CURVE-'+name,'CURVE');d.dimensions='3D';d.resolution_u=16
    s=d.splines.new('POLY');s.points.add(len(points)-1)
    for p,co in zip(s.points,points):p.co=(*co,1)
    s.use_cyclic_u=cyclic;d.bevel_depth=radius;d.bevel_resolution=3
    o=bpy.data.objects.new('GEO-'+name,d);bpy.context.collection.objects.link(o);d.materials.append(mat)
    return o

def aim(o, target):
    o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()

def tube(name, centers, radii, mat, sides=24):
    verts=[]
    for i,c in enumerate(centers):
        c=Vector(c)
        tangent=Vector(centers[min(i+1,len(centers)-1)])-Vector(centers[max(0,i-1)])
        tangent.normalize()
        a=tangent.cross(Vector((0,1,0)))
        if a.length<.01:a=tangent.cross(Vector((1,0,0)))
        a.normalize();b=tangent.cross(a).normalized()
        r=radii[i];rx,ry=(r,r) if isinstance(r,(int,float)) else r
        for j in range(sides):
            angle=j*2*math.pi/sides
            verts.append(tuple(c+a*(rx*math.cos(angle))+b*(ry*math.sin(angle))))
    faces=[(i*sides+j,i*sides+(j+1)%sides,(i+1)*sides+(j+1)%sides,(i+1)*sides+j)
           for i in range(len(centers)-1) for j in range(sides)]
    faces += [tuple(reversed(range(sides))), tuple((len(centers)-1)*sides+j for j in range(sides))]
    return mesh(name,verts,faces,mat)

def smoothstep(t):
    t=max(0,min(1,t));return t*t*(3-2*t)

def hood(x,y):
    base=.875 + .058*(y+2.25)/1.9 - .075*x*x + .012*math.cos((y+1.2)*2) - .16*math.exp(-((y+2.36)/.36)**2)
    fender=.09*math.exp(-((abs(x)-.86)/.18)**2)*(math.exp(-((y+1.35)/.6)**2)+math.exp(-((y-1.35)/.6)**2))
    return base+fender

def width(y):
    return .97 + .055*math.exp(-((y+1.35)/.46)**2)+.065*math.exp(-((y-1.38)/.6)**2)-.17*math.exp(-((y+2.45)/.35)**2)

def microtexture(mat, scale, strength=.12, distance=.001):
    n=mat.node_tree.nodes;l=mat.node_tree.links
    b=next(n for n in n if n.type=='BSDF_PRINCIPLED')
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=scale
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=strength;bump.inputs['Distance'].default_value=distance
    l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],b.inputs['Normal'])

def initialize():
    # Rebuild only the default startup file or this dedicated, consistently named scene.
    existing=list(bpy.context.scene.objects)
    default={'Cube','Light','Camera'}
    if existing and not ({o.name for o in existing}<=default or all(o.name.startswith(('GEO-','LGT-','CAM-','ARM-')) for o in existing)):
        raise RuntimeError('Open a dedicated GEM scene or a new default file before rebuilding')
    for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
    bpy.data.orphans_purge(do_recursive=True)
    s=bpy.context.scene;s.unit_settings.system='METRIC';s.unit_settings.scale_length=1
    s.frame_start=1;s.frame_end=192;s.render.fps=24
    w=bpy.data.worlds.new('WORLD-neutral_studio');s.world=w;w.use_nodes=True
    n=w.node_tree.nodes;n.clear();bg=n.new('ShaderNodeBackground');out=n.new('ShaderNodeOutputWorld')
    bg.inputs['Color'].default_value=(.045,.05,.06,1);bg.inputs['Strength'].default_value=.18
    w.node_tree.links.new(bg.outputs[0],out.inputs['Surface'])
    s.render.engine='CYCLES';s.cycles.samples=48;s.cycles.use_denoising=True
    s.cycles.denoiser='OPENIMAGEDENOISE';s.cycles.seed=0;s.cycles.use_animated_seed=False
    s.cycles.use_adaptive_sampling=True;s.cycles.adaptive_threshold=.025
    prefs=bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type='OPTIX';prefs.refresh_devices()
    for device in prefs.devices:device.use=device.type=='OPTIX'
    s.cycles.device='GPU';s.cycles.max_bounces=6;s.cycles.transmission_bounces=8
    s.view_settings.view_transform='AgX'
    s.render.resolution_x=1280;s.render.resolution_y=800;s.render.resolution_percentage=100
    s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB'
    return s
