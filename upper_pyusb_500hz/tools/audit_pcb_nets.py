"""Read Altium Components6/Nets6/Pads6 without changing source PCB files.

Pad field layout follows KiCad's APAD6 parser (source recorded in report).
This extracts assigned nets, not a geometric copper continuity/DRC check.
"""
from pathlib import Path
import json
import struct
import hashlib
import olefile


def records(blob):
    offset = 0
    while offset < len(blob):
        size = struct.unpack_from('<I', blob, offset)[0]
        offset += 4
        assert offset + size <= len(blob)
        yield blob[offset:offset+size]
        offset += size
    assert offset == len(blob)


def props(blob):
    return [dict(part.split('=', 1) for part in r.decode('cp1252').rstrip('\0').split('|') if '=' in part) for r in records(blob)]


def inspect(path):
    ole = olefile.OleFileIO(path)
    components = props(ole.openstream('Components6/Data').read())
    nets = props(ole.openstream('Nets6/Data').read())
    blob = ole.openstream('Pads6/Data').read()
    offset = 0
    pads = []
    while offset < len(blob):
        assert blob[offset] == 2, (offset, blob[offset])
        offset += 1
        sub = []
        for _ in range(6):
            size = struct.unpack_from('<I', blob, offset)[0]
            offset += 4
            assert offset + size <= len(blob)
            sub.append(blob[offset:offset+size])
            offset += size
        name = sub[0][1:1+sub[0][0]].decode('cp1252')
        assert len(sub[0]) == 1+sub[0][0]
        raw = sub[4]
        assert len(raw) >= 110
        net = struct.unpack_from('<H', raw, 3)[0]
        component = struct.unpack_from('<H', raw, 7)[0]
        assert net == 65535 or net < len(nets)
        assert component == 65535 or component < len(components)
        x, y = struct.unpack_from('<ii', raw, 13)
        pads.append({'pad': name, 'component_index': component, 'designator': components[component].get('SOURCEDESIGNATOR', f'index_{component}') if component != 65535 else None, 'net_index': net, 'net': nets[net]['NAME'] if net != 65535 else None, 'x_mil': x/10000, 'y_mil': y/10000})
    expected = struct.unpack('<I', ole.openstream('Pads6/Header').read())[0]
    assert len(pads) == expected, (len(pads), expected)
    return {'source': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'pad_count_verified': expected, 'components': components, 'nets': [n['NAME'] for n in nets], 'pads': pads}


if __name__ == '__main__':
    # 注意：本脚本针对原始工作区运行——需相邻存在“硬件原理图和芯片原理图/”目录，
    # 产物写入“gpt6-tactile500_pyusb上位机/reports/”。这两者均未纳入本仓库
    # （体积原因，见根目录 README「包含与不包含」），因此在仓库内直接运行会找不到路径。
    root = Path(__file__).resolve().parents[2]
    dest = root/'gpt6-tactile500_pyusb上位机/reports/firmware_hardware_audit_20260910'
    for path in (root/'硬件原理图和芯片原理图').glob('*.PcbDoc'):
        result = inspect(path)
        (dest/(path.stem+'_connectivity.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(path.name, 'components', len(result['components']), 'pads', result['pad_count_verified'])
        for i, comp in enumerate(result['components']):
            if comp.get('SOURCEDESIGNATOR', '').startswith(('S', 'J', 'P', 'U')) or '50P' in comp['PATTERN']:
                print(i, comp.get('SOURCEDESIGNATOR'), comp['PATTERN'], [(p['pad'], p['net']) for p in result['pads'] if p['component_index'] == i])
