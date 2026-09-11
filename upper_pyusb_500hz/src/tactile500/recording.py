"""Versioned loss-accounted recordings containing exact CRC-protected UART frames."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import re
import struct
import threading
from typing import Iterator

from .api import ReceivedFrame, TactileSystem
from .protocol import decode_frame

MAGIC = b"T5V2RAW\0"
RECORD = struct.Struct("<QQIHH")  # completing read end/start, epoch, raw length, flags


def _write_header(stream, metadata: dict) -> None:
    payload = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
    stream.write(MAGIC + struct.pack("<I", len(payload)) + payload)


def read_recording(path: str | Path) -> Iterator[ReceivedFrame]:
    """Validate header, complete record lengths and every V2 frame CRC."""
    with Path(path).open("rb") as stream:
        header = stream.read(12)
        if len(header) != 12 or header[:8] != MAGIC:
            raise ValueError("not a T5V2RAW recording")
        length = struct.unpack_from("<I", header, 8)[0]
        if not 1 <= length <= 65536:
            raise ValueError("invalid metadata length")
        payload = stream.read(length)
        if len(payload) != length:
            raise ValueError("truncated metadata")
        metadata = json.loads(payload)
        if metadata.get("format_version") != 2 or not isinstance(metadata.get("path"), str):
            raise ValueError("unsupported recording format")
        while prefix := stream.read(RECORD.size):
            if len(prefix) != RECORD.size:
                raise ValueError("truncated record header")
            end, start, epoch, size, flags = RECORD.unpack(prefix)
            if size not in (80, 180) or start > end:
                raise ValueError("invalid record metadata")
            raw = stream.read(size)
            if len(raw) != size:
                raise ValueError("truncated UART frame")
            yield ReceivedFrame(decode_frame(raw), metadata["path"], epoch, start, end, flags)


class Recorder:
    """One bounded subscriber and writer thread; disk stalls do not stop USB readers."""

    def __init__(self, system: TactileSystem, directory: str | Path, *, capacity: int = 32768):
        self.system = system
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.subscription = system.subscribe(capacity)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="tactile-recording", daemon=True)
        self.error: str | None = None
        self.records = 0
        self.files: list[str] = []
        self.started_utc = datetime.now(timezone.utc).isoformat()
        self._thread.start()

    def _run(self) -> None:
        handles: dict[str, tuple[tuple[int, int], object]] = {}
        try:
            while True:
                try:
                    item = self.subscription.get(timeout=0.1)
                except queue.Empty:
                    if self._stop.is_set():
                        break
                    continue
                key = (item.epoch, item.frame.identity)
                current = handles.get(item.path)
                if current is None or current[0] != key:
                    if current:
                        current[1].close()
                    safe_path = re.sub(r"[^a-zA-Z0-9_.-]", "_", item.path)
                    name = f"{safe_path}_e{item.epoch:04d}_{item.frame.identity:02x}.t5raw"
                    stream = (self.directory / name).open("xb", buffering=1024 * 1024)
                    handles[item.path] = (key, stream)
                    self.files.append(name)
                    _write_header(stream, {
                        "format_version": 2, "path": item.path, "role": item.frame.role,
                        "identity": item.frame.identity, "wire_version": item.frame.version,
                        "started_utc": self.started_utc,
                        "clock": "time.monotonic_ns on acquisition host",
                        "read_timestamp": "start/end of USB read completing this frame",
                        "record_struct": "<QQIHH followed by exact V2 UART bytes",
                    })
                stream = handles[item.path][1]
                raw = item.frame.raw
                stream.write(RECORD.pack(item.host_read_end_ns, item.host_read_start_ns,
                                         item.epoch, len(raw), item.flags) + raw)
                self.records += 1
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            for _, stream in handles.values():
                try:
                    stream.close()
                except Exception as exc:
                    self.error = self.error or f"close failed: {exc}"

    def close(self) -> dict:
        """Stop producers (system.close) first to drain every remaining queued frame."""
        self.subscription.close()
        self._stop.set()
        self._thread.join(10.0)
        if self._thread.is_alive():
            raise TimeoutError("recording writer is still blocked")
        report = {"format_version": 2, "started_utc": self.started_utc,
                  "records": self.records, "dropped": self.subscription.dropped,
                  "error": self.error, "files": self.files, "system": self.system.status()}
        (self.directory / "session.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
