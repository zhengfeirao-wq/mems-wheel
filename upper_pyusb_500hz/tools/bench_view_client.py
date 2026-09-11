"""Measure the actual Windows-to-G1 snapshot path without controlling boards."""
import argparse
import json
from pathlib import Path
import time
from urllib.request import urlopen


def main():
    p = argparse.ArgumentParser()
    p.add_argument("url")
    p.add_argument("--seconds", type=float, default=60)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    started = time.monotonic()
    latencies = []
    errors = []
    total = 0
    ticks = set()
    last = None
    while time.monotonic() - started < a.seconds:
        request_start = time.monotonic()
        try:
            with urlopen(a.url.rstrip("/") + "/api/snapshot", timeout=2) as response:
                data = response.read()
            last = json.loads(data)
            if "boards" not in last or last.get("view_error"):
                raise RuntimeError("monitor not ready")
            ticks.add(last["tick"])
            total += len(data)
            latencies.append((time.monotonic() - request_start) * 1000)
        except Exception as exc:
            errors.append(str(exc))
        time.sleep(max(0, 0.1 - (time.monotonic() - request_start)))
    elapsed = time.monotonic() - started
    ordered = sorted(latencies)
    report = {"elapsed_seconds": elapsed, "requests": len(latencies), "unique_view_ticks": len(ticks),
              "errors": errors, "bytes": total, "bytes_per_second": total / elapsed,
              "latency_ms_p50": ordered[len(ordered) // 2] if ordered else None,
              "latency_ms_p99": ordered[min(len(ordered) - 1, int(len(ordered) * .99))] if ordered else None,
              "last_snapshot": last}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "last_snapshot"}), flush=True)
    return int(bool(errors) or not latencies)


if __name__ == "__main__":
    raise SystemExit(main())
