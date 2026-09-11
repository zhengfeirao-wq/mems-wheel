"""Optional 10 Hz browser view. USB and full-rate recording never wait for HTTP.

One publisher takes bounded snapshots and caches JSON once per tick. HTTP
clients receive that immutable cache; opening extra tabs creates no subscribers.
"""
from __future__ import annotations

from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit

from . import __version__
from .api import ROLES, TactileSystem
from .mapping import physical_values, SHORT_POSITION_TO_CHANNEL
from .recording import Recorder

ROLE_LABELS = {"left_fingers": "左手 · 12 点", "right_fingers": "右手 · 12 点",
               "left_palm": "左手 · 32 点", "right_palm": "右手 · 32 点"}


class Monitor:
    def __init__(self, system: TactileSystem, output_root: Path, *, simulation=False):
        self.system = system
        self.output_root = Path(output_root)
        self.simulation = simulation
        self.control_token = secrets.token_urlsafe(24)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._recorder: Recorder | None = None
        self._last_recording: dict | None = None
        self._cache = b"{}"
        self._rate_base: dict = {}
        self._rates: dict = {}
        self._rate_time = time.monotonic()
        self._tick = 0
        self._error: str | None = None
        self._thread = threading.Thread(target=self._publish, name="tactile-view-cache", daemon=True)

    def start(self):
        self._thread.start()
        return self

    def cached(self) -> bytes:
        return self._cache

    def recording_status(self):
        with self._lock:
            rec = self._recorder
            if rec is None:
                return {"active": False, "last": self._last_recording}
            return {"active": True, "directory": str(rec.directory),
                    "records": rec.records, "dropped": rec.subscription.dropped,
                    "error": rec.error}

    def start_recording(self):
        with self._lock:
            if self._recorder is not None:
                return self.recording_status()
            name = datetime.now().strftime("%Y%m%d_%H%M%S_") + secrets.token_hex(3)
            self._recorder = Recorder(self.system, self.output_root / name)
            return self.recording_status()

    def stop_recording(self):
        with self._lock:
            rec = self._recorder
            if rec is not None:
                report = rec.close()
                self._last_recording = {"directory": str(rec.directory),
                                        **{k: report[k] for k in ("records", "dropped", "error", "files")}}
                self._recorder = None
            return self.recording_status()

    def snapshot_payload(self):
        status = self.system.status()
        snapshot = self.system.snapshot()
        by_path = {b["path"]: b for b in status["boards"]}
        now = time.monotonic()
        dt = now - self._rate_time
        if dt >= 1:
            for b in status["boards"]:
                count = b.get("frames", 0)
                old = self._rate_base.get(b["path"])
                self._rates[b["path"]] = ((count - old) / dt
                                           if old is not None and count >= old else None)
                self._rate_base[b["path"]] = count
            self._rate_time = now
        boards = []
        for role in ROLES:
            slot = snapshot.slots[role]
            out = {"role": role, "label": ROLE_LABELS[role], "state": slot.state}
            item = slot.value
            if item is not None:
                f = item.frame
                order = list(range(1, f.channels + 1))
                try:
                    temperature, pressure, fresh = physical_values(f)
                    if f.channels == 32:
                        order = list(SHORT_POSITION_TO_CHANNEL)
                    mapping = "短线显示位置" if f.channels == 32 else "MCU 通道顺序"
                except ValueError:
                    temperature, pressure, fresh = f.temperature, f.pressure, f.fresh_mask
                    mapping = "MCU 通道顺序 · 物理位置未确认"
                board = by_path[item.path]
                out.update(path=item.path, epoch=item.epoch, sequence=f.sequence,
                           identity=f"0x{f.identity:02X}", version=f"0x{f.version:02X}",
                           cable=f.cable, mapping=mapping, source_channels=order,
                           temperature=list(temperature), pressure=list(pressure),
                           fresh_mask=fresh, status=f.status, age_ms=slot.age_ns / 1e6,
                           recent_rate_hz=self._rates.get(item.path), diagnostics=board)
            boards.append(out)
        self._tick += 1
        return {"version": __version__, "simulation": self.simulation, "view_hz": 10,
                "tick": self._tick, "host_monotonic_ms": snapshot.target_ns / 1e6,
                "boards": boards, "devices": status["boards"],
                "discovery_error": status["discovery_error"], "view_error": self._error,
                "recording": self.recording_status()}

    def _publish(self):
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                payload = self.snapshot_payload()
                self._cache = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self._error = None
            except Exception as exc:
                self._error = f"{type(exc).__name__}: {exc}"
                self._cache = json.dumps({"view_error": self._error}).encode("utf-8")
            self._stop.wait(max(0, 0.1 - (time.monotonic() - started)))

    def close(self):
        self._stop.set()
        if self._thread.ident is not None:
            self._thread.join(2)
        return self.stop_recording()


def make_server(monitor: Monitor, bind="127.0.0.1", port=8875):
    html = files("tactile500").joinpath("assets/monitor.html").read_text(encoding="utf-8")
    page = html.replace("__CONTROL_TOKEN__", monitor.control_token).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *args):
            pass

        def reply(self, code, body, kind="application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/":
                self.reply(200, page, "text/html; charset=utf-8")
            elif path == "/api/snapshot":
                self.reply(200, monitor.cached())
            else:
                self.reply(404, b'{"error":"not found"}')

        def do_POST(self):
            # A custom token header and same-origin check protect recording actions.
            origin = self.headers.get("Origin")
            if (self.headers.get("X-Tactile-Control") != monitor.control_token
                    or (origin and urlsplit(origin).netloc != self.headers.get("Host"))):
                self.reply(403, b'{"error":"control token or origin rejected"}')
                return
            try:
                if self.path == "/api/record/start":
                    result = monitor.start_recording()
                elif self.path == "/api/record/stop":
                    result = monitor.stop_recording()
                else:
                    self.reply(404, b'{"error":"not found"}')
                    return
                self.reply(200, json.dumps(result, ensure_ascii=False).encode("utf-8"))
            except Exception as exc:
                self.reply(500, json.dumps({"error": str(exc)}).encode("utf-8"))

    server = ThreadingHTTPServer((bind, port), Handler)
    server.daemon_threads = True
    return server


def run_monitor(args):
    if args.simulate:
        from .simulation import demo_system
        system = demo_system()
    else:
        system = TactileSystem()
    monitor = Monitor(system, args.output_root, simulation=args.simulate)
    # Bind first; an occupied HTTP port must not start a second USB acquisition.
    server = make_server(monitor, args.bind, args.port)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    started = time.monotonic()
    try:
        if args.record:
            monitor.start_recording()
        system.open()
        monitor.start()
        server_thread.start()
        print(json.dumps({"view": f"http://{args.bind}:{server.server_port}",
                          "simulation": args.simulate, "version": __version__,
                          "output_root": str(args.output_root.resolve())}), flush=True)
        while not args.seconds or time.monotonic() - started < args.seconds:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        if server_thread.is_alive():
            server.shutdown()
        server.server_close()
        live = system.status()
        try:
            system.close()
        finally:
            result = monitor.close()
        print(json.dumps({"live_before_stop": live, "recording": result}), flush=True)
    last = result.get("last") or {}
    return int(bool(last.get("error") or last.get("dropped")))
