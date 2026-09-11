"""Bounded baseline/view/record comparison using the installed wheel.

Run on the acquisition host. Optional real Windows clients can concurrently
read --port; baseline never starts HTTP. Records include exact CRC bytes.
"""
import argparse
import json
from pathlib import Path
import platform
import threading
import time
from urllib.request import urlopen

import tactile500
from tactile500 import TactileSystem, read_recording
from tactile500.monitor import Monitor, make_server
from tactile500.simulation import demo_system


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("baseline", "view", "record"), required=True)
    p.add_argument("--simulate", action="store_true")
    p.add_argument("--seconds", type=float, default=30)
    p.add_argument("--clients", type=int, default=1)
    p.add_argument("--bind", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8875)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    system = demo_system() if a.simulate else TactileSystem()
    monitor = Monitor(system, a.output / "captures", simulation=a.simulate)
    server = make_server(monitor, a.bind, a.port) if a.mode != "baseline" else None
    stop = threading.Event()
    clients = []
    counts = [0] * a.clients
    errors = [0] * a.clients
    payload_bytes = [0] * a.clients

    def client(index):
        while not stop.is_set():
            try:
                with urlopen(f"http://127.0.0.1:{server.server_port}/api/snapshot", timeout=2) as response:
                    data = response.read()
                    json.loads(data)
                counts[index] += 1
                payload_bytes[index] += len(data)
            except Exception:
                errors[index] += 1
            stop.wait(0.1)

    if a.mode == "record":
        monitor.start_recording()
    started = time.monotonic()
    cpu = time.process_time()
    system.open()
    if server:
        monitor.start()
        threading.Thread(target=server.serve_forever, daemon=True).start()
        for i in range(a.clients):
            worker = threading.Thread(target=client, args=(i,), daemon=True)
            worker.start()
            clients.append(worker)
    print(json.dumps({"started": True, "mode": a.mode, "simulation": a.simulate,
                      "port": server.server_port if server else None}), flush=True)
    try:
        while time.monotonic() - started < a.seconds:
            time.sleep(0.1)
        live = system.status()
        elapsed = time.monotonic() - started
        cpu_percent = (time.process_time() - cpu) / elapsed * 100
    finally:
        stop.set()
        for worker in clients:
            worker.join(3)
        if server:
            server.shutdown()
            server.server_close()
        system.close()
        recording = monitor.close()
    verified = 0
    last = recording.get("last")
    if last:
        for name in last["files"]:
            verified += sum(1 for _ in read_recording(Path(last["directory"]) / name))
        if verified != last["records"]:
            raise AssertionError("record count does not match independently read files")
    result = {"version": tactile500.__version__, "package": tactile500.__file__,
              "machine": platform.machine(), "simulation": a.simulate, "mode": a.mode,
              "elapsed_seconds": elapsed, "cpu_percent_one_core": cpu_percent,
              "http_requests": counts, "http_errors": errors, "http_bytes": payload_bytes,
              "live_before_stop": live, "recording": recording, "verified_records": verified}
    (a.output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
    bad = any(b.get("missing_slots") or b.get("duplicates") or
              b.get("stream_rejected_candidates") or b.get("input_dropped_chunks")
              for b in live["boards"])
    return int(bad or any(errors) or bool(last and (last["error"] or last["dropped"])))


if __name__ == "__main__":
    raise SystemExit(main())
