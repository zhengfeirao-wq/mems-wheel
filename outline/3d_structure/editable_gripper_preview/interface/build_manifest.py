"""Publish the stable, relative-path interface for the existing accepted geometry."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
BASE_IDS = {
    '结构主体':'Structural_body', '原始第二结构实体':'Source_cover',
    '黄色硅胶封装':'Silicone_cap', 'PCB 板示意':'PCB_illustrative',
    '焊盘示意':'Solder_pads_illustrative', '连接器示意':'Connector_illustrative',
    '端子示意':'Connector_pins_illustrative',
}


def part_id(part):
    if part['name'] in BASE_IDS:
        return BASE_IDS[part['name']]
    if part['category'] == 'sensors':
        return f"Sensor_{int(part['name'].split()[1]):02d}_illustrative"
    if part['category'] == 'wires':
        return f"Wire_{int(part['name'].split()[1])}_illustrative"
    raise ValueError(f"Unknown part: {part['name']}")


def write_manifest(models=None):
    if models is None:
        models = json.loads((ROOT/'mesh-data.json').read_text(encoding='utf-8'))
    manifest = {
        'schema_version':1, 'revision':'2026-09-08-csv-relative-layout',
        'asset_root':'.. (relative to this manifest)',
        'units':'mm', 'coordinate_system':'original STEP XYZ, right-handed',
        'mesh_file':'mesh-data.json',
        'mesh_sha256':hashlib.sha256((ROOT/'mesh-data.json').read_bytes()).hexdigest(),
        'preview_html':'gripper-preview.html',
        'preview_default':{'channel':32,'explode':0.8,'roof_up':True},
        'preview_to_cad':{
            'matrix_row_major':[-1,0,0,0, 0,-1,0,14, 0,0,1,-12, 0,0,0,1],
            'description':'CAD = (-preview.x, 14-preview.y, preview.z-12)',
        },
        'source_manual':'../自适应通用夹爪传感器说明书.pdf',
        'reference_pcb':'reference-pcb.png',
        'limitations':[
            'Electronic placement and nominal silicone thickness are illustrative assumptions.',
            'STEP contains named bodies/components, not original SolidWorks feature history.',
            'Blender and GLB are tessellated geometry; use STEP for CAD surfaces.',
        ],
        'models':{},
    }
    for channel,model in models.items():
        source = ROOT.parent/f'onebody-{channel}-jiegoujian.STEP'
        parts = []
        for index,p in enumerate(model['parts']):
            key = part_id(p)
            step = f'cad/{channel}/{key}.step'
            parts.append({'id':key,'name':p['name'],'category':p['category'],
                          'mesh_index':index,'color_srgb':p['color'],
                          'step_component_name':key,
                          'step_file':step if (ROOT/step).is_file() else None,
                          'explode_translation_cad_mm':[-p['explode'][0],-p['explode'][1],p['explode'][2]],
                          'note':p['note']})
        assert len({p['id'] for p in parts}) == len(parts)
        manifest['models'][channel] = {
            'coordinate_source':{k:v for k,v in model['sensor_layout'].items() if k!='points'},
            'channel':int(channel),'component_count':len(parts),
            'source_step':f'../{source.name}',
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'step':{state:f'cad/{channel}/gripper-{channel}-{state}.step' for state in ('assembled','exploded')},
            'blender':f'blender/gripper-{channel}.blend',
            'glb':f'blender/gripper-{channel}.glb',
            'glb_coordinates':'glTF Y-up, meters; standard Blender exporter conversion from CAD XYZ',
            'parts':parts,
        }
    (ROOT/'interface/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest


if __name__ == '__main__':
    write_manifest()
