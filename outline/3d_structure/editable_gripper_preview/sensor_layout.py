"""Read measured XY point layouts without using IDs to determine placement."""
from pathlib import Path
import csv
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parent


def load_layout(channel):
    parameters = json.loads((ROOT/'parameters.json').read_text(encoding='utf-8'))
    filename = 'coord_Small_raw.csv' if channel == 12 else 'coord_Big_raw.csv'
    path = ROOT/'coordinates'/filename
    with path.open(encoding='utf-8-sig', newline='') as stream:
        raw = list(csv.DictReader(stream))
    points = [{'source_id': int(p['sensor_Number']),
               'source_xy': [float(p['X_coord']), float(p['Y_coord'])]} for p in raw]
    if len(points) != channel or len({p['source_id'] for p in points}) != channel:
        raise ValueError('Unexpected coordinate count or duplicate source IDs')
    if not all(math.isfinite(v) for p in points for v in p['source_xy']):
        raise ValueError('Non-finite coordinate')
    if len({tuple(p['source_xy']) for p in points}) != channel:
        raise ValueError('Duplicate coordinate points')
    xs, ys = zip(*(p['source_xy'] for p in points))
    scale = parameters['coordinate_scale_mm_per_unit']
    if scale <= 0:
        raise ValueError('Coordinate scale must be positive')
    translation = [-scale*(min(xs)+max(xs))/2,
                   parameters['coordinate_top_cad_y_mm']-scale*max(ys)]
    for p in points:
        p['cad_xy'] = [v*scale+t for v,t in zip(p['source_xy'],translation)]
    # Group only to construct supporting PCB strips; never snap point positions.
    groups = []
    for p in sorted(points, key=lambda p: (-p['cad_xy'][1], p['cad_xy'][0])):
        if not groups or abs(p['cad_xy'][1]-groups[-1][0]['cad_xy'][1]) > .002*scale:
            groups.append([])
        groups[-1].append(p)
    return {'file': str(path.relative_to(ROOT)).replace('\\','/'),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'scale_mm_per_source_unit': scale, 'translation_cad_xy_mm': translation,
            'xy_mapping': 'CAD.xy = source.xy * uniform_scale + translation; no mirroring or snapping',
            'registration_note': 'CSV units and absolute CAD registration unconfirmed; display assumes 1 source unit = 1 mm.',
            'points': points, 'groups': groups}


def validate_centers(layout, centers, tolerance):
    if len(centers) != len(layout['points']):
        raise ValueError('Sensor count differs from CSV')
    max_position_error = max(math.dist(center[:2], p['cad_xy'])
                             for center,p in zip(centers,layout['points']))
    max_pair_error = 0.0
    for i,a in enumerate(centers):
        for j,b in enumerate(centers[:i]):
            expected = math.dist(layout['points'][i]['source_xy'],
                                 layout['points'][j]['source_xy'])*layout['scale_mm_per_source_unit']
            max_pair_error = max(max_pair_error, abs(math.dist(a[:2], b[:2])-expected))
    if max_position_error > tolerance or max_pair_error > tolerance*2:
        raise ValueError(f'CSV geometry mismatch: position={max_position_error}, pair={max_pair_error}')
    return {'max_xy_position_error_mm': max_position_error,
            'max_pairwise_xy_distance_error_mm': max_pair_error,
            'pairwise_checks': len(centers)*(len(centers)-1)//2,
            'csv_relative_positions_verified': True}
