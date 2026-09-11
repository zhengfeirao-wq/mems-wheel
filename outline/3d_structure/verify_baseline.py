"""Verify the frozen starting material; never regenerate or update its hashes."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent


def verify():
    baseline = json.loads((ROOT/'baseline-manifest.json').read_text(encoding='utf-8'))
    errors = []
    for relative, expected in baseline['files'].items():
        path = ROOT/relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append(relative)
    if errors:
        raise RuntimeError('基准材料缺失或被修改：' + ', '.join(errors))
    return baseline


if __name__ == '__main__':
    baseline = verify()
    print(f"基准校验通过：{baseline['revision']}，{len(baseline['files'])} 个文件")
