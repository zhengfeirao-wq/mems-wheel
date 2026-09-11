"""Summarize saved release evidence; does not access USB or change recordings."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from tactile500 import read_recording


def main():
    here = Path(__file__).resolve().parent.parent
    root = here / "reports/release_0_3_0"
    source = here.parent / "嵌入式代码/Applications/Tactile500/tools/protocol_v2.py"
    spec = importlib.util.spec_from_file_location("firmware_decoder", source)
    reference = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = reference
    spec.loader.exec_module(reference)
    checks = []
    for path in sorted((root / "g1/hardware_record_windows").rglob("*.t5raw")):
        stats = reference.CaptureStats()
        count = 0
        first = None
        pmin = pmax = None
        for item in read_recording(path):
            f = reference.decode_frame(item.frame.raw)
            assert (f.sequence, f.pressure, f.temperature) == (
                item.frame.sequence, item.frame.pressure, item.frame.temperature)
            stats.add(f)
            first = first or item
            if pmin is None:
                pmin = list(f.pressure)
                pmax = list(f.pressure)
            else:
                pmin = [min(a, b) for a, b in zip(pmin, f.pressure)]
                pmax = [max(a, b) for a, b in zip(pmax, f.pressure)]
            count += 1
        checks.append({"file": str(path.relative_to(root)),
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "frames": count, "stats": stats.summary(),
                       "pressure_min": pmin, "pressure_max": pmax})
    wheel = here / "wheelhouse/tactile500-0.3.0-py3-none-any.whl"
    tests = [json.loads(p.read_text(encoding="utf-8")) | {"test": p.parent.name}
             for p in sorted((root / "g1").glob("*/result.json"))]
    summary = {"wheel": wheel.name, "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
               "tests": tests, "independent_hardware_recording_checks": checks}
    (root / "evidence_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"independently_verified": sum(c["frames"] for c in checks),
                       "wheel_sha256": summary["wheel_sha256"],
                       "left12_ch12": [(c["pressure_min"][11], c["pressure_max"][11])
                                      for c in checks if c["stats"]["channels"] == 12]}))


if __name__ == "__main__":
    main()
