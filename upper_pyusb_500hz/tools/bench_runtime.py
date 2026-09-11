"""Exercise the installed wheel, native recording and the common host timeline."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import platform
import sys
import time

import tactile500
from tactile500 import Recorder, TactileSystem


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seconds", type=float, default=1800)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--simulate", action="store_true")
    p.add_argument("--progress-interval", type=float, default=10)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    hub = None
    if a.simulate:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
        from helpers import FakeHub
        hub = FakeHub()
        system = TactileSystem(enumerate_fn=hub.enumerate, transport_factory=hub.factory,
                               scan_interval=0.05)
    else:
        system = TactileSystem()
    recorder = Recorder(system, a.output / "capture")
    states = Counter()
    ages = Counter()
    skews = Counter()
    skipped = snapshots = 0
    started = time.monotonic()
    cpu_start = os.times()
    next_progress = started
    injected = set()
    system.open()

    def quantiles(histogram):
        total = sum(histogram.values())
        result = {}
        for fraction in (0.5, 0.99, 0.999, 1.0):
            cumulative = 0
            for value, count in sorted(histogram.items()):
                cumulative += count
                if cumulative >= fraction * total:
                    result[str(fraction)] = value / 1000
                    break
        return result

    def report():
        status = system.status()
        cpu = os.times()
        elapsed = time.monotonic() - started
        return {"pid": os.getpid(), "elapsed_seconds": elapsed,
                "package": tactile500.__file__, "version": tactile500.__version__,
                "python": platform.python_version(), "machine": platform.machine(),
                "kernel": platform.release(), "simulation": a.simulate,
                "cpu_percent_one_core": (cpu.user + cpu.system - cpu_start.user - cpu_start.system) / elapsed * 100,
                "snapshots": snapshots, "skipped_ticks": skipped,
                "snapshot_state_counts": dict(states), "age_ms_quantiles": quantiles(ages),
                "receive_skew_ms_quantiles": quantiles(skews), "system": status}

    try:
        for snapshot in system.snapshots():
            now = time.monotonic()
            elapsed = now - started
            snapshots += 1
            skipped += snapshot.skipped_ticks
            for role, slot in snapshot.slots.items():
                states[role + ":" + slot.state] += 1
                if slot.age_ns is not None and slot.state in ("updated", "reused"):
                    ages[round(slot.age_ns / 100000) * 100] += 1  # bounded 0.1ms bins
            if snapshot.receive_skew_ns is not None:
                skews[round(snapshot.receive_skew_ns / 100000) * 100] += 1
            if hub:
                with hub.lock:
                    if elapsed >= 5 and "unplug" not in injected:
                        hub.present.remove("port2")
                        injected.add("unplug")
                    if elapsed >= 7 and "replug" not in injected:
                        hub.present.add("port2")
                        injected.add("replug")
                    if elapsed >= 10 and "swap" not in injected:
                        hub.roles["port1"], hub.roles["port3"] = hub.roles["port3"], hub.roles["port1"]
                        injected.add("swap")
            if now >= next_progress:
                full = report()
                pending = a.output / "progress.tmp"
                pending.write_text(json.dumps(full, indent=2), encoding="utf-8")
                pending.replace(a.output / "progress.json")
                print(json.dumps({"elapsed": round(elapsed, 1), "snapshots": snapshots,
                    "skipped": skipped, "boards": [{"role": b["role"], "frames": b.get("frames", 0),
                    "missing": b.get("missing_slots", 0), "crc_stream": b["stream_rejected_candidates"],
                    "connected": b["connected"], "epoch": b["epoch"], "error": b["error"]}
                    for b in full["system"]["boards"]]}), flush=True)
                next_progress = now + a.progress_interval
            if elapsed >= a.seconds:
                break
    except KeyboardInterrupt:
        pass
    finally:
        final = report()
        system.close()
        final["recording"] = recorder.close()
        final["simulation_injected"] = sorted(injected)
        (a.output / "final.json").write_text(json.dumps(final, indent=2), encoding="utf-8")
        print(json.dumps({"complete": True, "output": str(a.output),
                          "elapsed": final["elapsed_seconds"],
                          "recorded": final["recording"]["records"],
                          "recording_drops": final["recording"]["dropped"],
                          "error": final["recording"]["error"]}), flush=True)


if __name__ == "__main__":
    main()
