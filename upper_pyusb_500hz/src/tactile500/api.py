"""Fault-isolated native acquisition and causal host timeline snapshots."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import queue
import threading
import time
from typing import Callable, Iterator

from .protocol import CaptureStats, Frame, StreamDecoder
from .transport.pyusb_ch340 import CH340PyUsbTransport, enumerate_devices

ROLES = ("left_fingers", "right_fingers", "left_palm", "right_palm")
FLAG_GAP = 1
FLAG_DUPLICATE = 2
FLAG_RESET = 4
FLAG_BATCHED = 8


@dataclass(frozen=True, slots=True)
class ReceivedFrame:
    frame: Frame
    path: str
    epoch: int
    host_read_start_ns: int
    host_read_end_ns: int
    flags: int = 0


@dataclass(frozen=True, slots=True)
class SnapshotSlot:
    state: str
    value: ReceivedFrame | None
    age_ns: int | None


@dataclass(frozen=True, slots=True)
class Snapshot:
    target_ns: int
    slots: dict[str, SnapshotSlot]
    receive_skew_ns: int | None
    skipped_ticks: int


class Subscription:
    """Bounded, non-blocking publisher; a slow consumer drops its oldest item."""

    def __init__(self, owner: "TactileSystem", capacity: int):
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._owner = owner
        self._queue: queue.Queue[ReceivedFrame] = queue.Queue(capacity)
        self.dropped = 0
        self.closed = False

    def _put(self, item: ReceivedFrame) -> None:
        if self.closed:
            return
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self.dropped += 1
            except queue.Empty:
                pass
            self._queue.put_nowait(item)

    def get(self, timeout: float | None = None) -> ReceivedFrame:
        return self._queue.get(timeout=timeout)

    def close(self) -> None:
        with self._owner._lock:
            self.closed = True
            if self in self._owner._subscriptions:
                self._owner._subscriptions.remove(self)

    def __enter__(self) -> "Subscription":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


@dataclass
class _Board:
    path: str
    connected: bool = False
    epoch: int = 0
    reconnects: int = 0
    error: str | None = None
    latest: ReceivedFrame | None = None
    history: deque[ReceivedFrame] = field(default_factory=lambda: deque(maxlen=256))
    stats: CaptureStats = field(default_factory=CaptureStats)
    rejected: int = 0
    startup_rejected: int = 0
    discarded: int = 0
    bytes_read: int = 0
    first_ns: int = 0
    last_ns: int = 0
    reads: int = 0
    max_frames_per_read: int = 0
    metadata: dict = field(default_factory=dict)
    input_dropped_chunks: int = 0


class _ReadPump:
    """Keep the next USB request moving while a separate thread decodes frames."""

    def __init__(self, transport):
        self.transport = transport
        self.queue: queue.Queue = queue.Queue(2048)
        self.stop = threading.Event()
        self.error: Exception | None = None
        self.dropped = 0
        self.thread = threading.Thread(target=self._run, name="tactile-usb-pump", daemon=True)
        self.thread.start()

    def _run(self):
        try:
            while not self.stop.is_set():
                started = time.monotonic_ns()
                data = self.transport.read(0.050)
                ended = time.monotonic_ns()
                if not data:
                    continue
                try:
                    self.queue.put_nowait((started, ended, data, self.dropped))
                except queue.Full:
                    try:
                        self.queue.get_nowait()
                        self.dropped += 1
                    except queue.Empty:
                        pass
                    self.queue.put_nowait((started, ended, data, self.dropped))
        except Exception as exc:
            self.error = exc

    def get(self):
        try:
            return self.queue.get(timeout=0.050)
        except queue.Empty:
            if self.error:
                raise self.error
            now = time.monotonic_ns()
            return now, now, b"", self.dropped

    def close(self):
        self.stop.set()
        self.thread.join(0.2)
        if self.thread.is_alive():
            raise TimeoutError("USB read exceeded its configured deadline")


class TactileSystem:
    """Discover CH340 boards; their wire identities determine their roles.

    Only this class's supervisor discovers devices. Each path gets an independent
    retrying reader. User code and disk writes never run in those reader threads.
    The injected factory/enumerator also support hardware-free integration tests.
    """

    def __init__(self, *, expected_roles: tuple[str, ...] = ROLES,
                 scan_interval: float = 0.5, stale_seconds: float = 0.020,
                 no_data_seconds: float = 2.0,
                 usb_io: str = "async",
                 enumerate_fn: Callable = enumerate_devices,
                 transport_factory: Callable = CH340PyUsbTransport):
        if (scan_interval <= 0 or stale_seconds <= 0 or no_data_seconds <= 0
                or len(set(expected_roles)) != len(expected_roles)
                or any(role not in ROLES for role in expected_roles)
                or usb_io not in ("async", "sync")):
            raise ValueError("invalid timing or expected_roles")
        self.expected_roles = tuple(expected_roles)
        self.scan_interval = scan_interval
        self.stale_ns = int(stale_seconds * 1e9)
        self.no_data_seconds = no_data_seconds
        self.usb_io = usb_io
        self._enumerate = enumerate_fn
        self._factory = transport_factory
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._boards: dict[str, _Board] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._subscriptions: list[Subscription] = []
        self._quarantined: list = []
        self._supervisor: threading.Thread | None = None
        self.discovery_error: str | None = None

    def open(self) -> "TactileSystem":
        if self._supervisor is not None:
            raise RuntimeError("system is already open; create a new instance to restart")
        self._supervisor = threading.Thread(target=self._supervise,
                                            name="tactile-discovery", daemon=True)
        self._supervisor.start()
        return self

    def subscribe(self, capacity: int = 8192) -> Subscription:
        result = Subscription(self, capacity)
        with self._lock:
            self._subscriptions.append(result)
        return result

    def _supervise(self) -> None:
        while not self._stop.is_set():
            try:
                devices = self._enumerate()
                with self._lock:
                    self.discovery_error = None
                    for descriptor in devices:
                        if not descriptor.stable_identity:
                            self.discovery_error = "device has no USB topology; cannot select reliably"
                            continue
                        path = descriptor.path
                        if path in self._threads:
                            continue
                        if len(self._threads) >= 64:
                            self.discovery_error = "64 topology limit reached; restart acquisition"
                            break
                        self._boards[path] = _Board(path)
                        worker = threading.Thread(target=self._reader, args=(path,),
                                                  name=f"tactile-{path}", daemon=True)
                        self._threads[path] = worker
                        worker.start()
            except Exception as exc:
                with self._lock:
                    self.discovery_error = f"{type(exc).__name__}: {exc}"
            self._stop.wait(self.scan_interval)

    def _reader(self, path: str) -> None:
        board = self._boards[path]
        backoff = 0.1
        while not self._stop.is_set():
            transport = None
            pump = None
            try:
                transport = self._factory(path)
                transport.open()
                decoder = StreamDecoder()
                previous: Frame | None = None
                with self._lock:
                    board.connected = True
                    board.epoch += 1
                    board.reconnects += int(board.epoch > 1)
                    board.history.clear()
                    board.latest = None
                    board.metadata = dict(getattr(transport, "descriptor", {}))
                last_valid = time.monotonic()
                if self.usb_io == "async" and isinstance(transport, CH340PyUsbTransport):
                    from .transport.async_libusb import AsyncReadPump
                    pump = AsyncReadPump(transport)
                else:
                    pump = _ReadPump(transport)
                board.metadata["usb_io"] = self.usb_io if isinstance(transport, CH340PyUsbTransport) else "simulation"
                previous_dropped = 0
                while True:
                    if self._stop.is_set():
                        pump.stop.set()
                        if pump.queue.empty() and not pump.thread.is_alive():
                            break
                    started, ended, data, dropped = pump.get()
                    if dropped != previous_dropped:
                        with self._lock:
                            board.input_dropped_chunks += dropped - previous_dropped
                        decoder.buffer.clear()
                        previous_dropped = dropped
                    old_rejected, old_discarded = decoder.rejected_candidates, decoder.discarded_bytes
                    frames = decoder.feed(data)
                    with self._lock:
                        board.bytes_read += len(data)
                        board.reads += 1
                        board.rejected += decoder.rejected_candidates - old_rejected
                        if previous is None:
                            board.startup_rejected += decoder.rejected_candidates - old_rejected
                        board.discarded += decoder.discarded_bytes - old_discarded
                        board.max_frames_per_read = max(board.max_frames_per_read, len(frames))
                        for frame in frames:
                            flags = FLAG_BATCHED if len(frames) > 1 else 0
                            if previous is not None:
                                step = (frame.sequence - previous.sequence) & 0xFFFFFFFF
                                dt = (frame.sample_time_us - previous.sample_time_us) & 0xFFFFFFFF
                                if frame.identity != previous.identity:
                                    board.stats = CaptureStats()
                                    board.first_ns = 0
                                    flags |= FLAG_RESET
                                elif step == 0:
                                    flags |= FLAG_DUPLICATE
                                elif step >= 0x80000000 or dt == 0 or dt >= 0x80000000:
                                    flags |= FLAG_RESET
                                elif step > 1:
                                    flags |= FLAG_GAP
                            if flags & FLAG_RESET:
                                board.epoch += 1
                                board.history.clear()
                            item = ReceivedFrame(frame, path, board.epoch, started, ended, flags)
                            board.latest = item
                            board.history.append(item)
                            # Reconnect may reveal another board on this path.
                            if board.stats.previous and board.stats.previous.identity != frame.identity:
                                board.stats = CaptureStats()
                                board.first_ns = 0
                            board.stats.add(frame)
                            board.first_ns = board.first_ns or ended
                            board.last_ns = ended
                            board.error = None
                            for subscription in self._subscriptions:
                                subscription._put(item)
                            previous = frame
                    if frames:
                        last_valid = time.monotonic()
                        backoff = 0.1
                        # A request smaller than one UART frame avoids routinely
                        # collecting two full frames behind one host timestamp.
                        packet = int(board.metadata.get("wMaxPacketSize", 32) or 32)
                        if hasattr(transport, "read_size"):
                            transport.read_size = max(packet, (len(frames[-1].raw) - 1) // packet * packet)
                    elif time.monotonic() - last_valid >= self.no_data_seconds:
                        raise RuntimeError("no valid V2 frame (old BT firmware, silence or bad link)")
            except Exception as exc:
                with self._lock:
                    board.error = f"{type(exc).__name__}: {exc}"
            finally:
                safe_to_close = True
                if pump is not None:
                    try:
                        pump.close()
                    except Exception as exc:
                        with self._lock:
                            board.error = str(exc)
                            self._quarantined.append((transport, pump))
                        safe_to_close = False
                with self._lock:
                    board.connected = False
                if not safe_to_close:
                    # Do not free a handle underneath an outstanding C transfer.
                    return
                if transport is not None:
                    try:
                        transport.close()
                    except Exception:
                        pass
            self._stop.wait(backoff)
            backoff = min(2.0, backoff * 2)

    def status(self) -> dict:
        now = time.monotonic_ns()
        with self._lock:
            boards = []
            for board in self._boards.values():
                span = board.last_ns - board.first_ns
                boards.append({
                    "path": board.path, "connected": board.connected,
                    "epoch": board.epoch, "reconnects": board.reconnects,
                    "role": board.latest.frame.role if board.latest else None,
                    "age_ms": (now - board.latest.host_read_end_ns) / 1e6 if board.latest else None,
                    "error": board.error, "rejected_candidates": board.rejected,
                    "startup_rejected_candidates": board.startup_rejected,
                    "stream_rejected_candidates": board.rejected - board.startup_rejected,
                    "discarded_bytes": board.discarded, "bytes_read": board.bytes_read,
                    "read_calls": board.reads, "max_frames_per_read": board.max_frames_per_read,
                    "input_dropped_chunks": board.input_dropped_chunks,
                    "host_received_rate_hz": (board.stats.frames - 1) * 1e9 / span if span > 0 else None,
                    "metadata": dict(board.metadata), **board.stats.summary(),
                })
            roles = self.snapshot(now).slots
            return {"boards": boards, "roles": {k: v.state for k, v in roles.items()},
                    "discovery_error": self.discovery_error,
                    "subscriber_drops": [sub.dropped for sub in self._subscriptions]}

    def snapshot(self, target_ns: int | None = None, *, previous: Snapshot | None = None,
                 skipped_ticks: int = 0) -> Snapshot:
        """Latest received frame at/before target; no interpolation or future lookahead."""
        target = time.monotonic_ns() if target_ns is None else target_ns
        slots: dict[str, SnapshotSlot] = {}
        arrivals = []
        with self._lock:
            for role in self.expected_roles:
                candidates = [b for b in self._boards.values()
                              if b.latest and b.latest.frame.role == role and b.connected]
                if len(candidates) != 1:
                    known = any(b.latest and b.latest.frame.role == role for b in self._boards.values())
                    state = "ambiguous" if candidates else ("offline" if known else "missing")
                    slots[role] = SnapshotSlot(state, None, None)
                    continue
                value = next((x for x in reversed(candidates[0].history)
                              if x.host_read_end_ns <= target), None)
                if value is None:
                    slots[role] = SnapshotSlot("missing", None, None)
                    continue
                age = target - value.host_read_end_ns
                old = previous.slots.get(role) if previous else None
                reused = old is not None and old.value is value
                state = "stale" if age > self.stale_ns else ("reused" if reused else "updated")
                slots[role] = SnapshotSlot(state, value, age)
                if state != "stale":
                    arrivals.append(value.host_read_end_ns)
        skew = max(arrivals) - min(arrivals) if len(arrivals) > 1 else None
        return Snapshot(target, slots, skew, skipped_ticks)

    def snapshots(self, *, hz: float = 500.0, delay_seconds: float = 0.004) -> Iterator[Snapshot]:
        if hz <= 0 or delay_seconds < 0:
            raise ValueError("hz must be positive and delay nonnegative")
        period = max(1, int(1e9 / hz))
        delay = int(delay_seconds * 1e9)
        due = time.monotonic_ns() + period
        previous = None
        while not self._stop.is_set():
            self._stop.wait(max(0, due - time.monotonic_ns()) / 1e9)
            if self._stop.is_set():
                break
            skipped = max(0, (time.monotonic_ns() - due) // period)
            due += skipped * period
            result = self.snapshot(due - delay, previous=previous, skipped_ticks=skipped)
            previous = result
            due += period
            yield result

    def close(self, timeout: float = 8.0) -> None:
        self._stop.set()
        deadline = time.monotonic() + timeout
        if self._supervisor:
            self._supervisor.join(max(0, deadline - time.monotonic()))
        with self._lock:
            workers = list(self._threads.values())
        for worker in workers:
            worker.join(max(0, deadline - time.monotonic()))
        if any(worker.is_alive() for worker in workers):
            raise TimeoutError("USB worker did not finish within shutdown timeout")
        if any(pump.thread.is_alive() for _, pump in self._quarantined):
            raise TimeoutError("a USB cancellation is still outstanding")

    def __enter__(self) -> "TactileSystem":
        return self.open()

    def __exit__(self, *args: object) -> None:
        self.close()


# Familiar entry point for embedding; V2 returns ReceivedFrame / Snapshot objects.
TactileHand = TactileSystem
