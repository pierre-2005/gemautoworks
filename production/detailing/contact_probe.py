"""Measure deformed cloth and glove clearances against evaluated car geometry."""
import bpy,json
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parent
s=bpy.context.scene
report=[]
for frame in [26,49,71,91,115,140,160]:
    s.frame_set(frame);deps=bpy.context.evaluated_depsgraph_get()
    tree=BVHTree.FromObject(bpy.data.objects['GEO-coupe_body_shell'],deps)
    row={'frame':frame}
    for name,label in [('GEO-folded_microfiber_towel','cloth'),('GEO-working_glove','glove')]:
        obj=bpy.data.objects[name];ev=obj.evaluated_get(deps);data=ev.to_mesh();gaps=[]
        for vertex in data.vertices:
            co=ev.matrix_world@vertex.co
            hit=tree.ray_cast(Vector((co.x,co.y,2)),Vector((0,0,-1)))[0]
            if hit is not None:gaps.append(co.z-hit.z)
        ev.to_mesh_clear()
        row[label+'_min_gap_mm']=round(min(gaps)*1000,2)
        row[label+'_max_gap_mm']=round(max(gaps)*1000,2)
    report.append(row)
(ROOT/'validation').mkdir(exist_ok=True)
(ROOT/'validation'/'contact-validation.json').write_text(json.dumps(report,indent=2)+'\n')
minimum=min(row['cloth_min_gap_mm'] for row in report)
print(json.dumps({'frames':len(report),'cloth_min_gap_mm':minimum,'report':str(ROOT/'validation'/'contact-validation.json')}))
if minimum < -1:raise RuntimeError('Cloth penetrates the hood beyond the 1 mm tolerance')
