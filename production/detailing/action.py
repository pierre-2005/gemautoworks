"""Deterministic, reversible eight-second performance, baked into the .blend."""
from common import *
import random

def motion(frame):
    if frame<26:
        t=smoothstep((frame-1)/25)
        return (-.58+.02*t,-1.17,.07*(1-t))
    if frame<72:
        t=(frame-26)/46
        return (-.56+.56*smoothstep(t),-1.17+.045*math.sin(t*math.pi*2),0)
    if frame<91:
        t=smoothstep((frame-72)/19)
        return (-.63*t,-1.17,.035*math.sin(t*math.pi))
    if frame<162:
        t=smoothstep((frame-91)/71)
        return (-.63+.67*t,-1.17,0)
    t=smoothstep((frame-162)/22)
    return (.04-.08*t,-1.17+.39*t,.15*t)

def elbow(shoulder,wrist,pole):
    a=Vector(shoulder);b=Vector(wrist);d=(b-a).length
    upper=.31;lower=.30
    if d>upper+lower:raise ValueError(f'Unreachable wrist: {d:.3f}m')
    direction=(b-a).normalized();along=(upper*upper-lower*lower+d*d)/(2*d)
    bend=Vector(pole)-a;bend-=direction*bend.dot(direction);bend.normalize()
    return a+direction*along+bend*math.sqrt(max(0,upper*upper-along*along))

def sleeve_points(shoulder,wrist,pole):
    a=Vector(shoulder);c=Vector(wrist);b=elbow(a,c,pole)
    centers=[];radii=[]
    for i in range(25):
        t=i/24
        # Two segments blended gently around the elbow: sleeves, not joint balls.
        if t<=.5:p=a.lerp(b,t*2)
        else:p=b.lerp(c,(t-.5)*2)
        centers.append(tuple(p))
        radius=.093*(1-t)+.034*t+.008*math.sin(t*math.pi*5)**2
        radii.append(radius)
    return centers,radii

def shape_sample(obj, coords, frame, step):
    key=obj.shape_key_add(name=f'Baked_{frame:03d}')
    key.data.foreach_set('co',[v for co in coords for v in co])
    for f,value in [(max(1,frame-step),0),(frame,1),(min(192,frame+step),0)]:
        # End samples hold; interior samples form a partition of unity.
        key.value=value;key.keyframe_insert('value',frame=f)
    if frame==1:
        key.value=1;key.keyframe_insert('value',frame=1)
    if frame==192:
        key.value=1;key.keyframe_insert('value',frame=192)

def linearize():
    for action in bpy.data.actions:
        curves=[]
        if hasattr(action,'fcurves'):curves=list(action.fcurves)
        else:
            for layer in action.layers:
                for strip in layer.strips:
                    for bag in getattr(strip,'channelbags',[]):curves.extend(bag.fcurves)
        for fc in curves:
            for k in fc.keyframe_points:k.interpolation='LINEAR'

def build_action(fabric,glove):
    towelmat=material('slate_microfiber',(.045,.11,.15),.86)
    b=next(n for n in towelmat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');b.inputs['Sheen Weight'].default_value=.6
    microtexture(towelmat,1050,.4,.0018)
    def towel_coords(frame):
        cx,cy,lift=motion(frame)
        coords=[]
        for i in range(33):
            for j in range(41):
                x=(i/32-.5)*.36;y=(j/40-.5)*.64
                edge=(abs(x)/.18)**6+(abs(y)/.32)**8
                ripple=.003*math.sin(x*58+y*38+frame*.025)+.004*edge*math.sin(y*25+x*31)
                # Cloth's curvature is computed from the same analytic hood as the car.
                fold=.014*math.exp(-((x+.03)/.035)**2)*(1-math.exp(-(y/.085)**2))
                textile=max(.010,.011+ripple+fold)
                z=hood(cx+x,cy+y)-hood(cx,cy)+textile-.07*min(edge,1.2)*(lift/.18)
                coords.append((x,y,z))
        return coords
    faces=[(i*41+j,(i+1)*41+j,(i+1)*41+j+1,i*41+j+1) for i in range(32) for j in range(40)]
    towel=mesh('folded_microfiber_towel',towel_coords(1),faces,towelmat)
    towel.shape_key_add(name='Basis')
    solid=towel.modifiers.new('Folded textile thickness','SOLIDIFY');solid.thickness=.006
    bevel(towel,.002,2)
    working=bpy.data.objects['GEO-working_glove'];support=bpy.data.objects['GEO-support_glove']
    hand_rest=[tuple(v.co) for v in working.data.vertices]
    working.shape_key_add(name='Basis')
    # Sleeve animation is baked as geometry, so rendering never depends on Python handlers.
    shoulders=[(-.52,-1.15,1.235),(-.55,-.85,1.25)]
    poles=[(-1.12,-1.56,1.15),(-1.28,-.40,1.18)]
    sleeves=[]
    def wrist_at(frame,index):
        cx,cy,lift=motion(frame)
        return (cx-.07,cy,hood(cx-.07,cy)+.016+lift) if index==0 else (-.82,-.69,hood(-.82,-.69)+.020)
    for index in range(2):
        centers,radii=sleeve_points(shoulders[index],wrist_at(1,index),poles[index])
        obj=tube(('working' if index==0 else 'support')+'_sleeve',centers,radii,fabric,24)
        obj.shape_key_add(name='Basis');sleeves.append(obj)
    # Bake actual armature landmarks as well, for inspection and later character refinement.
    armdata=bpy.data.armatures.new('ARM-detailer_contact');arm=bpy.data.objects.new('ARM-detailer_contact',armdata)
    bpy.context.collection.objects.link(arm);bpy.context.view_layer.objects.active=arm;arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for i,name in enumerate(('working','support')):
        s=Vector(shoulders[i]);w=Vector(wrist_at(1,i));e=elbow(s,w,poles[i])
        for suffix,start,end in [('upper',s,e),('forearm',e,w)]:
            bone=armdata.edit_bones.new(name+'_'+suffix);bone.head=start;bone.tail=end
    bpy.ops.object.mode_set(mode='OBJECT');arm.hide_render=True
    samples=list(range(1,193,2))
    if samples[-1]!=192:samples.append(192)
    # Dense samples keep contact exact on the original surface, including rapid reversal.
    for frame in samples:
        shape_sample(towel,towel_coords(frame),frame,2 if frame<192 else 1)
        for index,obj in enumerate(sleeves):
            centers,radii=sleeve_points(shoulders[index],wrist_at(frame,index),poles[index])
            temp=tube('temporary_sample',centers,radii,fabric,24)
            shape_sample(obj,[tuple(v.co) for v in temp.data.vertices],frame,2 if frame<192 else 1)
            data=temp.data;bpy.data.objects.remove(temp,do_unlink=True);bpy.data.meshes.remove(data)
    for frame in range(1,193):
        cx,cy,lift=motion(frame)
        towel.location=(cx,cy,hood(cx,cy)+lift);towel.keyframe_insert('location',frame=frame)
        working.location=wrist_at(frame,0);working.keyframe_insert('location',frame=frame)
        support.location=wrist_at(frame,1);support.rotation_euler.z=.85
    for frame in list(range(1,192,4))+[192]:
        wx,wy,wz=wrist_at(frame,0)
        coords=[(x,y,z+hood(wx+x,wy+y)-hood(wx,wy)) for x,y,z in hand_rest]
        shape_sample(working,coords,frame,4 if frame<192 else 3)
    wx,wy,_=wrist_at(1,1)
    for vertex in support.data.vertices:
        x,y=vertex.co.x,vertex.co.y
        worldx=x*math.cos(.85)-y*math.sin(.85);worldy=x*math.sin(.85)+y*math.cos(.85)
        vertex.co.z+=hood(wx+worldx,wy+worldy)-hood(wx,wy)
    # Foam is a shader on the car itself, with stable world-coordinate masking.
    # No overlay mesh, texture replacement, or render-time Python handler exists.
    paint=bpy.data.materials['MAT-midnight_blue_lacquer']
    nodes=paint.node_tree.nodes;links=paint.node_tree.links
    original=next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
    out=next(n for n in nodes if n.type=='OUTPUT_MATERIAL')
    foam=nodes.new('ShaderNodeBsdfPrincipled');foam.name='Wet surface foam'
    foam.inputs['Base Color'].default_value=(.64,.69,.71,1);foam.inputs['Roughness'].default_value=.52
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=210;noise.inputs['Detail'].default_value=3
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.48;bump.inputs['Distance'].default_value=.0025
    links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],foam.inputs['Normal'])
    pos=nodes.new('ShaderNodeNewGeometry');xyz=nodes.new('ShaderNodeSeparateXYZ');links.new(pos.outputs['Position'],xyz.inputs[0])
    x,y,z=[xyz.outputs[k] for k in ('X','Y','Z')]
    def calc(op,a,b=None):
        n=nodes.new('ShaderNodeMath');n.operation=op
        for i,val in enumerate((a,b)):
            if val is None:continue
            if isinstance(val,(int,float)):n.inputs[i].default_value=val
            else:links.new(val,n.inputs[i])
        return n.outputs[0]
    def soften(value,width):
        n=nodes.new('ShaderNodeMapRange');n.clamp=True;n.interpolation_type='SMOOTHSTEP'
        n.inputs['From Min'].default_value=0;n.inputs['From Max'].default_value=width
        links.new(value,n.inputs['Value']);return n.outputs[0]
    edge_noise=nodes.new('ShaderNodeTexNoise');edge_noise.inputs['Scale'].default_value=45
    links.new(pos.outputs['Position'],edge_noise.inputs['Vector'])
    grain=calc('MULTIPLY',calc('SUBTRACT',edge_noise.outputs['Fac'],.5),.05)
    dx=calc('POWER',calc('DIVIDE',calc('ADD',x,.35),.37),4)
    dy=calc('POWER',calc('DIVIDE',calc('ADD',y,1.17),.285),4)
    outline=soften(calc('SUBTRACT',1,calc('ADD',calc('ADD',dx,dy),calc('MULTIPLY',grain,5))),.22)
    wash=nodes.new('ShaderNodeValue');wash.name='Wash boundary'
    wipe=nodes.new('ShaderNodeValue');wipe.name='Wipe boundary'
    for frame in range(1,193):
        wash.outputs[0].default_value=-.7+.80*smoothstep((frame-26)/46) if frame>=26 else -.9
        wash.outputs[0].keyframe_insert('default_value',frame=frame)
        wipe.outputs[0].default_value=motion(frame)[0]-.03 if frame>=91 else -.9
        if frame>=162:wipe.outputs[0].default_value=.2
        wipe.outputs[0].keyframe_insert('default_value',frame=frame)
    deposited=soften(calc('SUBTRACT',wash.outputs[0],calc('ADD',x,grain)),.025)
    remaining=soften(calc('SUBTRACT',calc('ADD',x,calc('MULTIPLY',grain,.20)),wipe.outputs[0]),.018)
    hood_only=calc('GREATER_THAN',z,.76)
    mask=calc('MULTIPLY',calc('MULTIPLY',outline,deposited),calc('MULTIPLY',remaining,hood_only))
    mix=nodes.new('ShaderNodeMixShader');links.new(mask,mix.inputs[0]);links.new(original.outputs[0],mix.inputs[1]);links.new(foam.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],out.inputs['Surface'])
    linearize()
    bpy.context.scene.frame_set(115)
    print('Baked 192-frame action: towel, continuous sleeves, spatial foam, planted feet')
