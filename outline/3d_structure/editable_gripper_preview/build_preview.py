"""Build a portable HTML preview from exact STEP tessellations and CAD parts."""
from pathlib import Path
import base64
import json

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent

def coordinate_svg(models):
    """Equal-axis, equal-scale source point view without sensor numbers."""
    scale = 7.0
    elements = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 320" style="display:block;width:100%;height:auto" role="img" aria-label="12 和 32 通道原始坐标，等比例点位图，不显示编号">',
                '<rect width="800" height="320" fill="#fafaf7"/>']
    for channel,cx in [('12',200),('32',600)]:
        points = models[channel]['sensor_layout']['points']
        xs,ys = zip(*(p['source_xy'] for p in points))
        mid_x = (min(xs)+max(xs))/2
        elements.append(f'<text x="{cx}" y="25" text-anchor="middle" font-family="Arial,Microsoft YaHei" font-size="16">{channel} 通道</text>')
        for point in points:
            x,y = point['source_xy']
            elements.append(f'<circle cx="{cx+(x-mid_x)*scale:.5f}" cy="{50+(max(ys)-y)*scale:.5f}" r="4" fill="#18765c"/>')
    elements.append('<text x="400" y="300" text-anchor="middle" font-family="Arial,Microsoft YaHei" font-size="13" fill="#687175">X 向右，Y 向上；横纵同尺度，保留原始间距与微小错位</text></svg>')
    return ''.join(elements)

def mesh_record(shape, name, category, color, explode, note):
    # Presentation transform is a proper 180 degree rotation about Z, followed
    # by a translation; source coordinates are preserved in exported STEP files.
    vertices, triangles = shape.tessellate(0.13, 0.15)
    return {"name": name, "category": category, "color": color,
            "explode": explode, "note": note,
            "vertices": [round(v, 4) for p in vertices for v in (-p.x, 14-p.y, p.z+12)],
            "triangles": [i for t in triangles for i in t]}

def write_html(models):
    html = (HERE / 'preview.template.html').read_text(encoding='utf-8')
    html = html.replace('__THREE_JS__', (HERE / 'vendor/three.min.js').read_text(encoding='utf-8'))
    html = html.replace('__MODEL_DATA__', json.dumps(models, ensure_ascii=False, separators=(',', ':')))
    reference = HERE / 'reference-pcb.png'
    img = 'data:image/png;base64,' + base64.b64encode(reference.read_bytes()).decode() if reference.exists() else ''
    html = html.replace('__PCB_IMAGE__', img)
    svg = coordinate_svg(models)
    html = html.replace('__COORDINATE_LAYOUT__', svg)
    (HERE/'coordinate-layout.svg').write_text(svg,encoding='utf-8')
    (HERE / 'gripper-preview.html').write_text(html, encoding='utf-8')
    (HERE / 'mesh-data.json').write_text(json.dumps(models, ensure_ascii=False), encoding='utf-8')
    from interface.build_manifest import write_manifest
    write_manifest(models)

if __name__ == '__main__':
    # Rebuild the presentation from the accepted model; never replace it with
    # a structural-only placeholder when this script is run on its own.
    models = json.loads((HERE / 'mesh-data.json').read_text(encoding='utf-8'))
    write_html(models)
    print('HTML ready', flush=True)
