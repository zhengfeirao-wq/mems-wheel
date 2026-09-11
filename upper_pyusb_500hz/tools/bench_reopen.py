"""Repeatedly open/close the installed wheel without unplugging devices."""
import argparse
import json
from pathlib import Path
import time

from tactile500 import TactileSystem


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cycles", type=int, default=5)
    a = p.parse_args()
    rows = []
    for cycle in range(a.cycles):
        started = time.monotonic()
        system = TactileSystem()
        system.open()
        while time.monotonic() - started < 8:
            time.sleep(0.1)
            boards = system.status()["boards"]
            if len(boards) == 2 and all(b.get("frames", 0) >= 1000 for b in boards):
                break
        status = system.status()
        system.close()
        row = {"cycle": cycle + 1, "seconds": time.monotonic() - started,
               "boards": [{"role": b["role"], "frames": b.get("frames", 0),
               "error": b["error"], "missing": b.get("missing_slots"),
               "crc_stream": b["stream_rejected_candidates"]} for b in status["boards"]]}
        rows.append(row)
        print(json.dumps(row), flush=True)
        if any(b["frames"] < 1000 for b in row["boards"]):
            break
    a.output.write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
