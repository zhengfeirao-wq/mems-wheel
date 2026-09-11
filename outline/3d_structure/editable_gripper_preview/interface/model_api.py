"""Standard-library API. Returned meshes use original STEP axes and mm by default."""
from pathlib import Path
import argparse
import json
import math

ASSET_ROOT = Path(__file__).resolve().parents[1]


def load_manifest(asset_root=None):
    root = Path(asset_root or ASSET_ROOT).resolve()
    data = json.loads((root / 'interface/manifest.json').read_text(encoding='utf-8'))
    if data['schema_version'] != 1:
        raise ValueError('Unsupported gripper interface schema')
    return data


def resolve_path(reference, asset_root=None):
    root = Path(asset_root or ASSET_ROOT).resolve()
    path = (root / reference).resolve()
    if not path.is_relative_to(root.parent):
        raise ValueError('Asset path leaves the model package')
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def model_info(channel=32, asset_root=None):
    models = load_manifest(asset_root)['models']
    if str(channel) not in models:
        raise ValueError('channel must be 12 or 32')
    return models[str(channel)]


def list_parts(channel=32, asset_root=None):
    return model_info(channel, asset_root)['parts']


def get_step_path(channel=32, state='assembled', part_id=None, asset_root=None):
    info = model_info(channel, asset_root)
    if state not in ('assembled', 'exploded'):
        raise ValueError('state must be assembled or exploded')
    if part_id is None:
        reference = info['step'][state]
    else:
        part = next((p for p in info['parts'] if p['id'] == part_id), None)
        if part is None:
            raise KeyError(part_id)
        if state != 'assembled':
            raise ValueError('Individual STEP parts use assembled/source coordinates')
        reference = part['step_file']
        if reference is None:
            raise ValueError(f'{part_id} is a named component in the full assembly STEP; no standalone STEP')
    return resolve_path(reference, asset_root)


def load_mesh(channel=32, explode=0.0, units='mm', asset_root=None):
    """Return separate meshes in STEP coordinates; explode is in [0, 1].

    Vertices include explosion displacement. No browser display rotation remains.
    Triangle winding is preserved: the display transform is a proper rotation.
    """
    explode = float(explode)
    if not math.isfinite(explode) or not 0 <= explode <= 1:
        raise ValueError('explode must be finite and between 0 and 1')
    if units not in ('mm', 'm'):
        raise ValueError('units must be mm or m')
    info = model_info(channel, asset_root)
    manifest = load_manifest(asset_root)
    models = json.loads(resolve_path(manifest['mesh_file'], asset_root).read_text(encoding='utf-8'))
    factor = .001 if units == 'm' else 1.0
    parts = []
    for part in info['parts']:
        source = models[str(channel)]['parts'][part['mesh_index']]
        offset = part['explode_translation_cad_mm']
        vertices = []
        values = source['vertices']
        for i in range(0, len(values), 3):
            xyz = (-values[i], 14-values[i+1], values[i+2]-12)
            vertices.append(tuple((xyz[j]+explode*offset[j])*factor for j in range(3)))
        indices = source['triangles']
        parts.append({**part, 'vertices':vertices,
                      'triangles':[tuple(indices[i:i+3]) for i in range(0,len(indices),3)]})
    return {'channel':int(channel), 'revision':manifest['revision'],
            'coordinate_system':'original STEP XYZ, right-handed', 'units':units,
            'explode':explode, 'parts':parts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel', type=int, choices=(12,32), default=32)
    parser.add_argument('--state', choices=('assembled','exploded'), default='assembled')
    parser.add_argument('--part', dest='part_id')
    parser.add_argument('--list-parts', action='store_true')
    parser.add_argument('--asset-root', type=Path)
    args = parser.parse_args()
    if args.list_parts:
        print(json.dumps(list_parts(args.channel,args.asset_root),ensure_ascii=False,indent=2))
    else:
        print(get_step_path(args.channel,args.state,args.part_id,args.asset_root))


if __name__ == '__main__':
    main()
