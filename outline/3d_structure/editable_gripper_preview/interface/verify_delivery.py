"""Validate all portable interface paths, units, transforms, and accepted assets."""
from pathlib import Path
import hashlib
import json
import math
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from model_api import ASSET_ROOT, get_step_path, load_manifest, load_mesh, resolve_path
sys.path.insert(0,str(ASSET_ROOT))
from sensor_layout import load_layout, validate_centers


def main():
    root=ASSET_ROOT
    manifest=load_manifest()
    mesh_hash=hashlib.sha256((root/'mesh-data.json').read_bytes()).hexdigest()
    assert manifest['mesh_sha256']==mesh_hash
    blender=json.loads((root/'interface/blender-validation.json').read_text())
    assert blender['mesh_sha256']==mesh_hash,'Blender assets are stale; rebuild them'
    assert blender['millimeter_scene_checked']
    assert all(r['blend_roundtrip'] and r['glb_roundtrip'] for r in blender['models'])
    geometry=json.loads((root/'geometry-validation.json').read_text())
    assert all(c['silicone_valid'] and c['silicone_solids']==1 and c['flat_surface_type']=='PLANE'
               and c['max_flatness_error_mm']<1e-5 and c['body_skin_overlap_mm3']<1e-5 for c in geometry)
    assert all(c['electronics_orientation_verified'] for c in geometry)
    roundtrip=json.loads((root/'step-roundtrip-validation.json').read_text())
    assert len(roundtrip)==6 and all(c['valid'] for c in roundtrip)
    resolve_path(manifest['source_manual'])
    resolve_path(manifest['reference_pcb'])
    for channel in (12,32):
        info=manifest['models'][str(channel)]
        source=resolve_path(info['source_step'])
        assert hashlib.sha256(source.read_bytes()).hexdigest()==info['source_sha256']
        for state in ('assembled','exploded'):
            assert get_step_path(channel,state).read_bytes().startswith(b'ISO-10303-21;')
        for part in info['parts']:
            if part['step_file']:
                get_step_path(channel,part_id=part['id'])
        assert resolve_path(info['blender']).read_bytes().startswith(b'BLENDER')
        assert resolve_path(info['glb']).read_bytes().startswith(b'glTF')
        assembled=load_mesh(channel)
        parameters=json.loads((root/'parameters.json').read_text(encoding='utf-8'))
        wires=[p for p in assembled['parts'] if p['category']=='wires']
        assert len(wires)==4
        for wire in wires:
            spans=[max(v[i] for v in wire['vertices'])-min(v[i] for v in wire['vertices'])
                   for i in range(3)]
            assert abs(spans[1]-parameters['wire_length_mm'])<1e-4
            assert all(abs(spans[i]-2*parameters['wire_radius_mm'])<2e-4 for i in (0,2))
        sensors=[p for p in assembled['parts'] if p['category']=='sensors']
        layout=load_layout(channel)
        assert layout['sha256']==info['coordinate_source']['sha256']
        assert layout['translation_cad_xy_mm']==info['coordinate_source']['translation_cad_xy_mm']
        by_id={int(p['id'].split('_')[1]):p for p in sensors}
        centers=[]
        for point in layout['points']:
            part=by_id[point['source_id']]
            centers.append(tuple((min(v[i] for v in part['vertices'])+max(v[i] for v in part['vertices']))/2 for i in range(3)))
        validate_centers(layout,centers,1e-4)
        meters=load_mesh(channel,units='m')
        exploded=load_mesh(channel,explode=1)
        assert len(assembled['parts'])==(23 if channel==12 else 43)
        for base,metric,moved in zip(assembled['parts'],meters['parts'],exploded['parts']):
            assert all(0<=i<len(base['vertices']) for triangle in base['triangles'] for i in triangle)
            for p,q,r in zip(base['vertices'],metric['vertices'],moved['vertices']):
                for i in range(3):
                    assert math.isfinite(p[i]) and abs(p[i]*.001-q[i])<1e-12
                    assert abs(r[i]-p[i]-base['explode_translation_cad_mm'][i])<1e-10
    for invalid in (-1,1.1,float('nan')):
        try:
            load_mesh(12,explode=invalid)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid explosion accepted')
    report={'revision':manifest['revision'],'mesh_sha256':mesh_hash,
            'source_hashes_verified':True,'portable_paths_verified':True,
            'coordinate_and_unit_conversions_verified':True,
            'csv_pairwise_xy_distances_verified':True,
            'straight_wire_geometry_verified':True,
            'blender_roundtrips_verified':True,'html_api_verified_by':'verify_preview.cjs',
            'solidworks_live_tested':False}
    (root/'interface/delivery-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':
    main()
