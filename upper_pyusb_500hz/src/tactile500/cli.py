from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

from .api import TactileSystem
from .protocol import CaptureStats
from .recording import Recorder, read_recording
from .transport.pyusb_ch340 import enumerate_devices


def main() -> int:
    parser = argparse.ArgumentParser(description="Tactile V2 / CH340 / PyUSB only")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan", help="read-only USB topology enumeration")
    probe = sub.add_parser("probe", help="receive native frames and report real rates")
    probe.add_argument("--seconds", type=float, default=30)
    capture = sub.add_parser("capture", help="record exact native V2 frames")
    capture.add_argument("--seconds", type=float, default=30)
    capture.add_argument("--output", type=Path, required=True)
    inspect = sub.add_parser("inspect", help="validate recorded frames offline")
    inspect.add_argument("path", type=Path)
    view = sub.add_parser("view", help="optional local/LAN four-board browser monitor")
    view.add_argument("--bind", default="127.0.0.1")
    view.add_argument("--port", type=int, default=8875)
    view.add_argument("--output-root", type=Path, default=Path("captures"))
    view.add_argument("--record", action="store_true", help="record immediately")
    view.add_argument("--simulate", action="store_true", help="four fake boards; no USB access")
    view.add_argument("--seconds", type=float, default=0, help="0 means until Ctrl+C")
    args = parser.parse_args()
    if args.command == "view":
        if args.seconds < 0 or not 0 <= args.port <= 65535:
            parser.error("invalid --seconds or --port")
        from .monitor import run_monitor
        return run_monitor(args)
    if args.command == "scan":
        print(json.dumps([{"path": d.path, "bus": d.bus, "address": d.address,
                           "vid": f"{d.vid:04x}", "pid": f"{d.pid:04x}"}
                          for d in enumerate_devices()], indent=2))
        return 0
    if args.command == "inspect":
        paths = sorted(args.path.glob("*.t5raw")) if args.path.is_dir() else [args.path]
        result = []
        for path in paths:
            stats = CaptureStats()
            for item in read_recording(path):
                stats.add(item.frame)
            result.append({"file": str(path), **stats.summary()})
        print(json.dumps(result, indent=2))
        return 0
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    system = TactileSystem()
    recorder = Recorder(system, args.output) if args.command == "capture" else None
    started = time.monotonic()
    cpu_started = os.times()
    system.open()
    try:
        deadline = started + args.seconds
        while time.monotonic() < deadline:
            time.sleep(min(0.25, max(0, deadline - time.monotonic())))
    except KeyboardInterrupt:
        pass
    finally:
        live_before_stop = system.status()
        system.close()
    result = recorder.close() if recorder else system.status()
    result["live_before_stop"] = live_before_stop
    cpu = os.times()
    result["elapsed_seconds"] = time.monotonic() - started
    result["process_cpu_seconds"] = cpu.user + cpu.system - cpu_started.user - cpu_started.system
    result["process_cpu_percent_one_core"] = result["process_cpu_seconds"] / result["elapsed_seconds"] * 100
    if recorder:
        (args.output / "report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 1 if recorder and (recorder.error or recorder.subscription.dropped) else 0
