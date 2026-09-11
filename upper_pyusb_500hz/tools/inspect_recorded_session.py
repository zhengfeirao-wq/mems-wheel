"""Inspect a completed session with the firmware's separate V2 decoder."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from tactile500 import read_recording


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = (Path(__file__).resolve().parents[2] /
              "嵌入式代码/Applications/Tactile500/tools/protocol_v2.py")
    spec = importlib.util.spec_from_file_location("firmware_inspector", source)
    reference = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = reference
    spec.loader.exec_module(reference)
    results = []
    for path in sorted(args.directory.rglob("*.t5raw")):
        stats = reference.CaptureStats()
        first = last = None
        minimum = maximum = temperature_min = temperature_max = None
        changed = []
        previous = None
        increments = Counter()
        status = Counter()
        for item in read_recording(path):
            frame = reference.decode_frame(item.frame.raw)
            assert (frame.sequence, frame.pressure, frame.temperature) == (
                item.frame.sequence, item.frame.pressure, item.frame.temperature)
            stats.add(frame)
            first = first or item
            last = item
            status[frame.status] += 1
            if minimum is None:
                minimum = list(frame.pressure)
                maximum = list(frame.pressure)
                temperature_min = list(frame.temperature)
                temperature_max = list(frame.temperature)
                changed = [0] * frame.channels
            else:
                minimum = [min(a, b) for a, b in zip(minimum, frame.pressure)]
                maximum = [max(a, b) for a, b in zip(maximum, frame.pressure)]
                temperature_min = [min(a, b) for a, b in zip(temperature_min, frame.temperature)]
                temperature_max = [max(a, b) for a, b in zip(temperature_max, frame.temperature)]
            if previous:
                changed = [n + (a != b) for n, a, b in zip(changed, previous.pressure, frame.pressure)]
                increments[(frame.sample_time_us - previous.sample_time_us) & 0xFFFFFFFF] += 1
            previous = frame
        span = last.host_read_end_ns - first.host_read_end_ns if first else 0
        results.append({"file": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        **stats.summary(),
                        "host_received_rate_hz": (stats.frames - 1) * 1e9 / span if span else None,
                        "first_sequence": first.frame.sequence if first else None,
                        "last_sequence": last.frame.sequence if last else None,
                        "status_counts": {f"0x{k:02X}": v for k, v in status.items()},
                        "timestamp_step_us_counts": dict(increments),
                        "pressure_min": minimum, "pressure_max": maximum,
                        "pressure_change_counts": changed,
                        "temperature_min": temperature_min, "temperature_max": temperature_max})
    report = {"valid_frames": sum(r["frames"] for r in results), "boards": results,
              "interpretation": "Value variation is not evidence of controlled press response or ADC freshness."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"frames": report["valid_frames"], "boards": [
        {k: r[k] for k in ("identity_hex", "frames", "host_received_rate_hz",
                           "missing_slots", "duplicates", "pressure_change_counts")} for r in results]}))


if __name__ == "__main__":
    main()
