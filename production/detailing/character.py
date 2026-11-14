"""Original clothed detailer. Continuous sleeve meshes and five-finger work gloves."""
from common import *

def build_character():
    fabric=material('charcoal_workwear',(.003,.004,.006),.84)
    microtexture(fabric,330,.3,.0012)
    b=next(n for n in fabric.node_tree.nodes if n.type=='BSDF_PRINCIPLED');b.inputs['Sheen Weight'].default_value=.05
    b.inputs['Sheen Tint'].default_value=(.03,.035,.04,1);b.inputs['Specular IOR Level'].default_value=.15
    glove=material('black_nitrile_gloves',(.002,.003,.005),.52)
    microtexture(glove,440,.16,.0004)
    next(n for n in glove.node_tree.nodes if n.type=='BSDF_PRINCIPLED').inputs['Specular IOR Level'].default_value=.28
    seam=material('workwear_stitch',(.052,.06,.066),.8)
    sole=material('shoe_rubber',(.012,.014,.017),.72)
    skin=material('skin',(.27,.145,.09),.48)
    b=next(n for n in skin.node_tree.nodes if n.type=='BSDF_PRINCIPLED');b.inputs['Subsurface Weight'].default_value=.12
    # Anatomical shoulder width .43m; tapered waist; stable, individually shaped legs.
    centers=[(-1.30,-.98,.83),(-1.20,-.99,.99),(-.98,-1.0,1.10),(-.72,-1.0,1.21),(-.50,-1.0,1.30)]
    torso=tube('tailored_work_jacket',centers,[(.16,.21),(.155,.20),(.17,.235),(.18,.24),(.13,.20)],fabric,40)
    sub=torso.modifiers.new('Tailoring smooth','SUBSURF');sub.levels=2
    for side in (-1,1):
        y=-.98+side*.155
        leg=tube('work_trouser', [(-1.31,y,.89),(-1.36,y+side*.06,.67),(-1.42,y+side*.09,.44),(-1.43,y+side*.12,.20),(-1.44,y+side*.13,.09)],
                 [(.14,.13),(.13,.12),(.105,.11),(.082,.09),(.078,.085)],fabric,28)
        leg.modifiers.new('Trouser drape','SUBSURF').levels=2
        ellipsoid('work_shoe',(-1.38,y+side*.13,.066),(.19,.108,.065),sole)
        curve('trouser_outer_seam',[(-1.50,y+side*.13,.14),(-1.50,y+side*.09,.43),(-1.46,y+side*.06,.66),(-1.43,y,.83)],.002,seam)
    # Head is bowed toward the work; an original cap shades the face.
    neck=ellipsoid('neck',(-.45,-1.0,1.36),(.075,.08,.115),skin)
    head=ellipsoid('bowed_head',(-.35,-1.0,1.46),(.12,.105,.15),skin)
    head.rotation_euler.y=.5
    ellipsoid('ear',(-.39,-1.108,1.46),(.035,.018,.047),skin)
    ellipsoid('nose',(-.235,-1.01,1.413),(.039,.032,.027),skin)
    cap=ellipsoid('work_cap',(-.38,-1.0,1.545),(.127,.115,.075),fabric)
    cap.rotation_euler.y=.46
    brim=ellipsoid('cap_visor',(-.244,-1.0,1.499),(.17,.12,.014),fabric)
    brim.rotation_euler.y=.45
    curve('jacket_zipper',[(-1.10,-1.226,1.00),(-.98,-1.24,1.15),(-.79,-1.23,1.33)],.003,seam)
    # A pocket and stitch lines break up the workwear without invented company branding.
    pocket=cube('jacket_chest_pocket',(-.93,-1.231,1.235),(.15,.009,.13),fabric,.012)
    pocket.rotation_euler.y=-.5

    # Glove local X points toward the fingertips. Palm + each digit are modelled,
    # then fused into one watertight glove, avoiding detached tube fingers.
    for side in ('working','support'):
        parts=[]
        parts.append(ellipsoid('glove_palm',(0.04,0,.018),(.065,.043,.024),glove,32,20))
        parts.append(ellipsoid('glove_wrist',(-.025,0,.021),(.035,.032,.024),glove,24,16))
        for i,length in enumerate((.073,.086,.080,.061)):
            yy=-.029+i*.019
            centers=[(.074,yy,.019),(.096,yy,.018),(.074+length*.66,yy-.002,.008),(.074+length,yy-.002,-.002)]
            digit=tube('glove_finger',centers,[.010,.0105,.009,.0065],glove,12);parts.append(digit)
            parts.append(ellipsoid('glove_fingertip',centers[-1],(.009,.007,.009),glove,16,10))
        parts.append(tube('glove_thumb',[(.014,-.03,.012),(.043,-.057,.010),(.073,-.06,.006),(.089,-.048,.006)], [.016,.014,.011,.009],glove,16))
        bpy.ops.object.select_all(action='DESELECT')
        for o in parts:o.select_set(True)
        bpy.context.view_layer.objects.active=parts[0];bpy.ops.object.join()
        hand=bpy.context.object;hand.name='GEO-'+side+'_glove'
        remesh=hand.modifiers.new('Continuous glove anatomy','REMESH');remesh.mode='VOXEL';remesh.voxel_size=.003
        bpy.ops.object.modifier_apply(modifier=remesh.name)
        smooth=hand.modifiers.new('Soft nitrile surface','SMOOTH');smooth.factor=.8;smooth.iterations=3
        # All primitive origins are baked into world coordinates before parenting.
        bpy.context.scene.cursor.location=(0,0,0);bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
        hand['original_asset']=True
    print('Original detailer and gloves built')
    return fabric,glove
