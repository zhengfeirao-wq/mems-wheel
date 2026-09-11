"""Generate named, separate CAD solids and the offline discussion preview.

Install cadquery==2.8.0; place original STEP files one directory above this file.
Edit parameters.json and run python build_models.py. All CAD exports retain the
original STEP coordinate system. PCB/chips/cables are explicitly illustrative.
"""
from pathlib import Path
import json
import math
import shutil
import cadquery as cq
import numpy as np
from scipy.interpolate import PchipInterpolator
from build_preview import mesh_record, write_html
from sensor_layout import load_layout, validate_centers

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent
PARAMS = json.loads((HERE / 'parameters.json').read_text(encoding='utf-8'))
OUTPUT = HERE / 'cad'
OUTPUT.mkdir(exist_ok=True)
# The source contact plane is Z=-2, beginning near Y=21.174 mm.
# Keep the existing curved-to-flat transition at Y=21.3 mm and extend the
# silicone's outer plane through the tip, independent of source edge ribs.
FLAT_START_Y = 21.3
FLAT_BASE_Z = -2.0


def combine(shapes):
    return cq.Compound.makeCompound(shapes)


def profile(body):
    """Sample exact transverse sections; inset the envelope inside the outline."""
    bb = body.BoundingBox()
    ys = np.linspace(PARAMS['silicone_start_y_mm'], bb.ymax-PARAMS['silicone_end_inset_mm'], PARAMS['profile_sections'])
    rows = []
    for y in ys:
        section = body.intersect(cq.Face.makePlane(basePnt=(0, float(y), 0), dir=(0,1,0)))
        b = section.BoundingBox()
        rows.append((float(y), b.xmin+PARAMS['silicone_edge_inset_mm'], b.xmax-PARAMS['silicone_edge_inset_mm'], b.zmax))
    return rows


def make_skin(body, rows):
    """Curved upper envelope joins an exactly planar lower contact face."""
    if not rows[0][0] < FLAT_START_Y < rows[-1][0]:
        raise ValueError('Silicone extent must include the curved-to-flat transition.')
    # Insert the transition only for silicone; keep the original sampling used
    # by PCB/chip placement unchanged.
    if not any(r[0] == FLAT_START_Y for r in rows):
        section = body.intersect(cq.Face.makePlane(basePnt=(0,FLAT_START_Y,0),dir=(0,1,0)))
        bb = section.BoundingBox()
        inset = PARAMS['silicone_edge_inset_mm']
        rows = sorted([*rows,(FLAT_START_Y,bb.xmin+inset,bb.xmax-inset,bb.zmax)])
    wires = []
    thickness = PARAMS['silicone_thickness_mm']
    # These source-derived longitudinal stations remove local fastener/rib
    # protrusions from the visible silicone face while retaining its broad curve.
    knots_y = [rows[0][0],4.2,10,16,FLAT_START_Y,rows[-1][0]]
    knots_z = [-8.3,-8.3,-7.5,-5.1,FLAT_BASE_Z,FLAT_BASE_Z]
    smooth = PchipInterpolator(knots_y,knots_z)
    for y, left, right, z in rows:
        if y > FLAT_START_Y:
            break
        top = float(smooth(y))+thickness
        bottom = float(smooth(y))-.25
        wires.append(cq.Wire.makePolygon([(left,y,bottom),(right,y,bottom),(right,y,top),(left,y,top)],close=True))
    curved = cq.Solid.makeLoft(wires, ruled=False)
    # A planar outline extrusion guarantees a CAD PLANE, avoiding both the old
    # 2 mm tip upturn and any global-loft interpolation ripple on the flat face.
    tail_rows = [r for r in rows if r[0] >= FLAT_START_Y]
    bottom = FLAT_BASE_Z - .25
    left = [cq.Vector(r[1],r[0],bottom) for r in tail_rows]
    right = [cq.Vector(r[2],r[0],bottom) for r in tail_rows]
    outline = cq.Wire.assembleEdges([
        cq.Edge.makeLine(right[0],left[0]),
        cq.Edge.makeSpline(left),
        cq.Edge.makeLine(left[-1],right[-1]),
        cq.Edge.makeSpline(list(reversed(right))),
    ])
    flat = cq.Solid.extrudeLinear(outline,[],cq.Vector(0,0,thickness+.25))
    cap = curved.fuse(flat).cut(body).clean()
    # The source's slanted tip can cut off a small fragment underneath the body.
    # Keep the connected outer encapsulation, never a detached underside sliver.
    solids = cap.Solids()
    if len(solids) > 1:
        exterior = [s for s in solids if s.BoundingBox().ymin < FLAT_START_Y
                    and s.BoundingBox().ymax > FLAT_START_Y
                    and s.BoundingBox().zmax >= FLAT_BASE_Z+thickness-1e-5]
        if len(exterior) == 1 and all(s is exterior[0] or
                s.BoundingBox().zmax < FLAT_BASE_Z+thickness-1e-5 for s in solids):
            cap = exterior[0]
    if len(cap.Solids()) != 1 or not cap.isValid():
        raise ValueError(f'Silicone must be one valid solid: solids={len(cap.Solids())}, valid={cap.isValid()}')
    return cap


def z_at(rows, y):
    return float(np.interp(y, [r[0] for r in rows], [r[3] for r in rows]))


def local_box(x, y, z, width, length, height, slope=0):
    shape = cq.Workplane('XY').box(width,length,height,centered=(True,True,False)).val()
    if slope:
        shape = shape.rotate((0,0,0),(1,0,0),slope)
    return shape.translate((x,y,z))


def electronics(channel, rows):
    """Place exact CSV XY centers; infer only Z and illustrative PCB supports."""
    layout = load_layout(channel)
    boards, chips, contacts = [], [], []
    chip_size = PARAMS['sensor_size_mm']
    chip_h = PARAMS['sensor_height_mm']
    pcb_t = PARAMS['pcb_thickness_mm']
    strips = []
    for group in layout['groups']:
        y = sum(p['cad_xy'][1] for p in group)/len(group)
        left = min(p['cad_xy'][0] for p in group)-1.8
        right = max(p['cad_xy'][0] for p in group)+1.8
        slope = math.degrees(math.atan2(z_at(rows,y+.3)-z_at(rows,y-.3),.6))
        boards.append(local_box((left+right)/2,y,z_at(rows,y)+.12,right-left,3.1,pcb_t,slope))
        strips.append((y,left,right))
    for point in layout['points']:
        x,y = point['cad_xy']
        angle = math.atan2(z_at(rows,y+.3)-z_at(rows,y-.3),.6)
        slope = math.degrees(angle)
        # Center the solid before tilting: no Y drift from a rotated bottom pivot.
        z_center = z_at(rows,y)+.12+(pcb_t+.07+chip_h/2)/math.cos(angle)
        chip = cq.Workplane('XY').box(chip_size,chip_size,chip_h).val()
        chips.append(chip.rotate((0,0,0),(1,0,0),slope).translate((x,y,z_center)))
        for side in (-1,1):
            for offset in (-.48,.48):
                pad_y = y+offset
                pad_z = z_at(rows,y)+.12+math.tan(angle)*offset+pcb_t/math.cos(angle)
                contacts.append(local_box(x+side*(chip_size/2+.18),pad_y,pad_z,.33,.42,.13,slope))
    # Bridges follow the measured rows; their geometry remains illustrative.
    for a,b in zip(strips[:-1],strips[1:]):
        low_y,high_y = sorted((a[0],b[0]))
        y = (low_y+high_y)/2
        x = min(a[2],b[2])-.6
        slope = math.degrees(math.atan2(z_at(rows,high_y)-z_at(rows,low_y),high_y-low_y))
        length = math.hypot(high_y-low_y,z_at(rows,high_y)-z_at(rows,low_y))
        boards.append(local_box(x,y,z_at(rows,y)+.12,1.0,length+1,pcb_t,slope))
    return combine(boards), chips, combine(contacts)


def check_electronics_orientation(channel, chips, skin):
    """Compare actual solid centers with CSV positions, independent of ID order."""
    layout = load_layout(channel)
    centers = [chip.Center().toTuple() for chip in chips]
    check = validate_centers(layout,centers,1e-6)
    bb = skin.BoundingBox()
    assert all(bb.ymin < center[1] < bb.ymax for center in centers)
    check.update({'roof_direction_cad':'+Y (CSV +Y, displayed upward)',
                  'row_counts_from_roof':[len(g) for g in layout['groups']],
                  'sensor_row_centers_cad_y_mm':[sum(p['cad_xy'][1] for p in g)/len(g) for g in layout['groups']],
                  'electronics_orientation_verified':True,
                  'coordinate_source':{k:v for k,v in layout.items() if k not in ('groups','points')}})
    return check


def wire_segment(a,b,radius):
    start,end=cq.Vector(*a),cq.Vector(*b)
    d=end-start
    return cq.Solid.makeCylinder(radius,d.Length,start,d.normalized())


def wiring():
    connector=local_box(0,-5.5,-22.1,6.4,4.2,2.7)
    # Display-level cable routing, 4 electrical conductors; DF52 housing is a
    # simplified envelope without a claimed vendor-accurate pin pitch.
    pins=[local_box(-1.2+i*.8,-7.1,-22.7,.28,1.5,.65) for i in range(4)]
    cables=[]
    for i in range(4):
        x=-1.2+i*.8
        start=(x,-7.8,-21.4)
        end=(x,-7.8-PARAMS['wire_length_mm'],-21.4)
        # Flexible conductors shown straight in their relaxed display pose.
        cables.append(wire_segment(start,end,PARAMS['wire_radius_mm']))
    return connector, combine(pins), cables


def check_skin_outline(body,skin,rows):
    """Verify cap does not extend outside the source X silhouette at section cuts."""
    worst=0.0
    for y in np.linspace(rows[0][0]+.01,rows[-1][0]-.01,101):
        plane=cq.Face.makePlane(basePnt=(0,float(y),0),dir=(0,1,0))
        bb=body.intersect(plane).BoundingBox()
        sb=skin.intersect(plane).BoundingBox()
        worst=max(worst,bb.xmin-sb.xmin,sb.xmax-bb.xmax)
    overlap=body.intersect(skin).Volume()
    if worst>.015 or overlap>1e-5:
        raise ValueError(f'Skin outline/interference check failed: {worst}, {overlap}')
    return {'section_samples':101,'max_outline_overrun_mm':worst,'body_skin_overlap_mm3':overlap}


def check_skin_flatness(skin,rows):
    """Check the actual solid's outer plane all the way to the tip."""
    target_z = FLAT_BASE_Z + PARAMS['silicone_thickness_mm']
    planar_faces = [f for f in skin.Faces() if f.geomType() == 'PLANE'
                    and abs(f.Center().z-target_z) < 1e-6
                    and abs(abs(f.normalAt().z)-1) < 1e-6
                    and f.BoundingBox().ymin <= FLAT_START_Y+1e-5
                    and f.BoundingBox().ymax >= rows[-1][0]-1e-5]
    max_error = 0.0
    for y in np.linspace(FLAT_START_Y+.001,rows[-1][0]-.001,31):
        section = skin.intersect(cq.Face.makePlane(basePnt=(0,float(y),0),dir=(0,1,0)))
        max_error = max(max_error,abs(section.BoundingBox().zmax-target_z))
    if not planar_faces or max_error > 1e-5:
        raise ValueError(f'Silicone lower face is not flat: planes={len(planar_faces)}, error={max_error}')
    return {'flat_start_y_mm':FLAT_START_Y,'flat_end_y_mm':rows[-1][0],
            'flat_outer_z_mm':target_z,'flat_surface_type':'PLANE',
            'flatness_section_samples':31,'max_flatness_error_mm':max_error}


def build(channel):
    print(f'{channel}: reading source',flush=True)
    source = cq.importers.importStep(str(SOURCE / f'onebody-{channel}-jiegoujian.STEP')).val()
    initial_bb=source.BoundingBox()
    dimensions=[initial_bb.xlen,initial_bb.ylen,initial_bb.zlen]
    solids=sorted(source.Solids(),key=lambda s:-s.Volume())
    body, cover=solids
    rows=profile(body)
    print(f'{channel}: making silicone',flush=True)
    skin=make_skin(body,rows)
    check=check_skin_outline(body,skin,rows)
    check.update(check_skin_flatness(skin,rows))
    pcb,chips,pads=electronics(channel,rows)
    check.update(check_electronics_orientation(channel,chips,skin))
    connector,pins,wires=wiring()
    entries=[
        ('Structural_body','结构主体','body',body,'#a8aaa0',[0,0,0],'原始 STEP 中的主体实体，未重画。'),
        ('Source_cover','原始第二结构实体','cover',cover,'#bfc0b6',[0,0,-17],'原始 STEP 中的第二实体；具体实物名称待确认。'),
        ('Silicone_cap','黄色硅胶封装','silicone',skin,'#dcae32',[-28,0,52],f'新增独立包覆实体；上部随形，下部至末端的外表面为平面。名义厚度 {PARAMS["silicone_thickness_mm"]} mm 为假设，轮廓按原结构截面向内收边。'),
        ('PCB_illustrative','PCB 板示意','pcb',pcb,'#18765c',[-5,0,17],'条带根据 CSV 实际点位布置；桥接、板宽和绝对安装位置仍为示意。'),
        ('Solder_pads_illustrative','焊盘示意','pcb',pads,'#c2a355',[-5,0,17],'焊盘细节示意，未按实际封装校核。'),
        ('Connector_illustrative','连接器示意','connector',connector,'#ddd6be',[12,0,-24],'插座外包络示意；未建供应商精确型号。'),
        ('Connector_pins_illustrative','端子示意','connector',pins,'#b8a266',[12,0,-24],'端子示意，非制造定义。'),
    ]
    layout = load_layout(channel)
    for chip,point in zip(chips,layout['points']):
        source_id = point['source_id']
        entries.append((f'Sensor_{source_id:02d}_illustrative',f'传感器件 {source_id:02d} 示意','sensors',chip,'#39424b',[-14,0,32],f"XY 相对位置来自 CSV {point['source_xy']}；编号只标识来源。Z 与封装尺寸仍为示意。"))
    for i,wire in enumerate(wires):
        entries.append((f'Wire_{i+1}_illustrative',f'导线 {i+1} 示意','wires',wire,'#2d3437',[12,0,-24],'柔性导线，以伸直状态展示；长度为示意参数。'))
    assembly=cq.Assembly(name=f'Gripper_{channel}_discussion')
    exploded=cq.Assembly(name=f'Gripper_{channel}_exploded_discussion')
    mesh=[]
    folder=OUTPUT / str(channel)
    folder.mkdir(exist_ok=True)
    for key,name,category,shape,color,offset,note in entries:
        if not shape.isValid() or shape.Volume()<=0:
            raise ValueError(f'Invalid shape: {key}')
        rgb=tuple(int(color[k:k+2],16)/255 for k in (1,3,5))
        assembly.add(shape,name=key,color=cq.Color(*rgb))
        # Display transform reverses X/Y; reverse those offsets for CAD.
        exploded.add(shape,name=key,color=cq.Color(*rgb),loc=cq.Location(cq.Vector(-offset[0],-offset[1],offset[2])))
        mesh.append(mesh_record(shape,name,category,color,offset,note))
        if category in ('body','cover','silicone','pcb','connector') and 'pins' not in key and 'pads' not in key:
            cq.exporters.export(shape,str(folder/f'{key}.step'))
    assembly.export(str(folder/f'gripper-{channel}-assembled.step'))
    exploded.export(str(folder/f'gripper-{channel}-exploded.step'))
    check.update({'channel':channel,'source_solids':len(solids),'sensor_count':len(chips),'wire_count':len(wires),'silicone_valid':skin.isValid(),'silicone_solids':len(skin.Solids()),'silicone_volume_mm3':skin.Volume(),'assembly_components':len(entries),'profile':rows})
    print(f'{channel}: exported {len(entries)} components',flush=True)
    return {'dimensions':dimensions,'parts':mesh,'sensor_layout':{k:v for k,v in layout.items() if k!='groups'}},check


def main():
    models,checks={},[]
    for channel in (12,32):
        models[str(channel)],check=build(channel)
        checks.append(check)
    write_html(models)
    (HERE/'geometry-validation.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print('All models and HTML generated.',flush=True)


if __name__=='__main__':
    main()
