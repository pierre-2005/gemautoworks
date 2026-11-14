"""Original unbranded coupe, built from continuous lofted panels."""
from common import *

def build_car():
    paint=material('midnight_blue_lacquer',(.003,.012,.027),.29,0,1)
    microtexture(paint,760,.08,.00012)
    black=material('satin_carbon_trim',(.009,.012,.015),.31)
    rubber=material('tire_rubber',(.018,.02,.023),.63)
    microtexture(rubber,210,.15,.0005)
    alloy=material('satin_forged_aluminium',(.42,.46,.49),.24,1)
    rotor=material('brushed_brake_disc',(.28,.3,.32),.42,1)
    caliper=material('brake_caliper',(.09,.11,.14),.31,1)
    glass=material('smoked_automotive_glass',(.014,.023,.031),.085,0,1)
    lamp=material('headlamp_optics',(.55,.64,.69),.13,1)
    led=material('neutral_daylight_LED',(.8,.9,1),.18)
    b=next(n for n in led.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    b.inputs['Emission Color'].default_value=(.76,.86,1,1);b.inputs['Emission Strength'].default_value=2

    # Closed superelliptic shell: long, low nose; wide hips; continuous crown.
    verts=[];faces=[];ny=112;nr=64
    for i in range(ny+1):
        y=-2.3+4.6*i/ny;w=width(y)
        for j in range(nr):
            a=2*math.pi*j/nr;sn=math.sin(a);cs=math.cos(a)
            x=w*math.copysign(abs(sn)**.63,sn)
            top=hood(x,y)
            z=top-(top-.47)*(1-cs)**8 if cs>=0 else .47-.28*abs(cs)**.6
            # Sweep the corners rearward; a shallow prow avoids a flat cut-off nose.
            yy=y+.16*(abs(x)/w)**2*math.exp(-((y+2.3)/.19)**2)
            verts.append((x,yy,z))
    for i in range(ny):
        for j in range(nr):faces.append((i*nr+j,i*nr+(j+1)%nr,(i+1)*nr+(j+1)%nr,(i+1)*nr+j))
    faces.extend([tuple(reversed(range(nr))),tuple(ny*nr+j for j in range(nr))])
    shell=mesh('coupe_body_shell',verts,faces,paint)
    # True wheel openings, not black decals hiding solid bodywork.
    for y in (-1.38,1.38):
        bpy.ops.mesh.primitive_cylinder_add(vertices=96,radius=.402,depth=2.6,location=(0,y,.365),rotation=(0,math.pi/2,0))
        cutter=bpy.context.object
        mod=shell.modifiers.new('Wheel opening','BOOLEAN');mod.operation='DIFFERENCE';mod.object=cutter
        bpy.context.view_layer.objects.active=shell;bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(cutter,do_unlink=True)
    bevel(shell,.009,3)

    # A single swept glass canopy with a roof panel, pillars and rubber seals.
    def canopy(u,v):
        y=-.52+2.02*v
        z=.94+.43*math.sin(math.pi*v)**.72
        w=.75-.12*math.sin(math.pi*v)
        x=(u*2-1)*w
        return (x,y,z-.115*(abs(u*2-1)**2))
    canopy_obj=grid('continuous_glazed_canopy',48,64,canopy,glass)
    solid=canopy_obj.modifiers.new('Laminated glass','SOLIDIFY');solid.thickness=.008
    # Roof cap occupies the crown, leaving a broad windshield for reflections.
    roof=grid('sculpted_roof',36,32,lambda u,v:tuple(Vector(canopy(.04+.92*u,.39+.30*v))+Vector((0,0,.012))),paint)
    roof.modifiers.new('Roof skin','SOLIDIFY').thickness=.016
    for side in (0,1):
        curve('canopy_edge_seal', [canopy(side,i/80) for i in range(81)], .014,black)
        # Close the side glazing down to the beltline, preserving the roof arc.
        def sideglass(u,v):
            x,y,z=canopy(side,v)
            sign=-1 if side==0 else 1
            return (x+sign*.09*u,y,z*(1-u)+(.892+.008*math.sin(v*math.pi))*u)
        grid('side_window',20,64,sideglass,glass)
        for v in (.02,.39,.7,.98):
            curve('canopy_structural_pillar',[tuple(Vector(canopy(i/40,v))+Vector((0,0,.006))) for i in range(41)],.018,paint)
    # Hood shut line and tapered character creases follow the actual panel.
    outline=[]
    for i in range(41):
        y=-2.05+1.48*i/40;x=.67+.04*math.sin(i/40*math.pi)
        outline.append((x,y,hood(x,y)+.002))
    outline += [(-x,y,z) for x,y,z in reversed(outline)]
    curve('hood_panel_gap',outline,.003,black,True)
    for sign in (-1,1):
        curve('hood_character_line',[(sign*(.50+.13*t/50),-2.04+1.43*t/50,hood(.50+.13*t/50,-2.04+1.43*t/50)+.006) for t in range(51)],.0035,paint)
        # Slim integrated headlamp housings, sculpted into the nose corners.
        def lamp_surface(u,v):
            x=sign*(.51+.36*u);y=-2.17+.27*v+.09*u
            return(x,y,hood(x,y)+.001)
        grid('headlamp_recess',20,12,lamp_surface,black)
        for line in range(2):
            pts=[]
            for t in range(31):
                x=sign*(.54+.30*t/30);y=-2.12+.09*t/30+.09*line
                pts.append((x,y,hood(x,y)+.005))
            curve('headlamp_light_blade',pts,.0035,led)
        # Front air intakes and a restrained carbon splitter.
        vent=cube('front_brake_duct',(sign*.68,-2.30,.39),(.34,.11,.18),black,.045)
        for bar in range(3):cube('duct_vane',(sign*.68,-2.36,.34+.045*bar),(.25,.012,.009),alloy,.003)
        curve('rocker_sill',[(sign*(width(y)+.006),y,.235) for y in [-.94+i*.047 for i in range(41)]],.038,black)
        # Door seams define the body architecture without ornamental graphics.
        pts=[(sign*(width(y)+.002),y,.51+.28*math.sin(t/45*math.pi)) for t,y in enumerate([-.63+i*.034 for i in range(46)])]
        curve('door_panel_gap',pts,.003,black)
        mirror=ellipsoid('mirror_shell',(sign*1.045,-.24,1.015),(.16,.18,.055),paint)
        curve('mirror_stalk',[(sign*.82,-.12,.95),(sign*.98,-.20,.98)],.021,black)
    cube('central_front_grille',(0,-2.304,.415),(.65,.055,.20),black,.055)
    for i in range(17):cube('grille_vertical_fin',(-.29+i*.036,-2.339,.415),(.007,.014,.12),alloy,.002)
    curve('front_splitter',[(-.91,-2.24,.224),(-.76,-2.39,.207),(0,-2.405,.197),(.76,-2.39,.207),(.91,-2.24,.224)],.028,black)

    # Four independently modelled, grounded wheels, brake rotors and forged spokes.
    for sign in (-1,1):
        for y in (-1.38,1.38):
            x=sign*.958
            bpy.ops.mesh.primitive_torus_add(major_radius=.282,minor_radius=.079,major_segments=96,minor_segments=24,location=(x,y,.361),rotation=(0,math.pi/2,0))
            tire=bpy.context.object;tire.name='GEO-performance_tire';tire.data.materials.append(rubber)
            for p in tire.data.polygons:p.use_smooth=True
            for rad,depth,mat,offset,name in [(.267,.17,alloy,.01,'wheel_barrel'),(.225,.022,rotor,.072,'brake_rotor'),(.062,.035,alloy,.113,'wheel_hub')]:
                bpy.ops.mesh.primitive_cylinder_add(vertices=80,radius=rad,depth=depth,location=(x+sign*offset,y,.361),rotation=(0,math.pi/2,0))
                o=bpy.context.object;o.name='GEO-'+name;o.data.materials.append(mat);bevel(o,.004)
            # Dark outer barrel face, with genuinely separate narrow spokes.
            bpy.ops.mesh.primitive_cylinder_add(vertices=80,radius=.246,depth=.012,location=(x+sign*.1,y,.361),rotation=(0,math.pi/2,0))
            o=bpy.context.object;o.name='GEO-wheel_inner_shadow';o.data.materials.append(black)
            for j in range(10):
                a=2*math.pi*j/10
                pts=[(x+sign*.116,y+.057*math.sin(a),.361+.057*math.cos(a)),(x+sign*.115,y+.16*math.sin(a+.10),.361+.16*math.cos(a+.10)),(x+sign*.101,y+.25*math.sin(a+.15),.361+.25*math.cos(a+.15))]
                curve('forged_wheel_spoke',pts,.013,alloy)
            # Tire sidewall mould line and subtle tread grooves.
            for rr in (.30,.336):
                curve('tire_sidewall_ring',[(x+sign*.065,y+rr*math.sin(t*math.pi/48),.361+rr*math.cos(t*math.pi/48)) for t in range(96)],.0015,black,True)
    print('Original coupe built:',len(bpy.data.objects),'objects')
    return paint
