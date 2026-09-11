"""Independent Tactile500 V2 decoder and raw UART capture inspector.

Only Python's standard library is required. Input must contain UART payload
bytes, after any USB bridge packet headers have been removed by the transport.
"""
from __future__ import annotations

import argparse
import binascii
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import struct

SYNC = b"\xa5\x5a"
STATUS_NAMES = (
    "not_all_fresh", "spi_error", "sensor_error", "init_error",
    "sweep_late_latched", "tx_busy_latched", "tx_error_latched", "tick_late_latched",
)


@dataclass(frozen=True)
class Frame:
    version: int
    identity: int
    status: int
    sequence: int
    sample_time_us: int
    fresh_mask: int
    temperature: tuple[int, ...]
    pressure: tuple[int, ...]

    @property
    def channels(self) -> int:
        return len(self.temperature)

    @property
    def hand(self) -> str:
        return "right" if self.identity & 1 else "left"

    @property
    def cable(self) -> str:
        if self.channels == 12:
            return "none"
        return "short" if self.identity & 4 else "long"

    @property
    def mapping_revision(self) -> int:
        return self.identity >> 3


def decode_frame(packet: bytes) -> Frame:
    if len(packet) < 20 or packet[:2] != SYNC or packet[2] != len(packet):
        raise ValueError("Invalid sync or length")
    if packet[3] >> 4 != 2:
        raise ValueError("Unsupported protocol major version")
    channels = 32 if packet[4] & 2 else 12
    if len(packet) != 20 + channels * 5 or (channels == 12 and packet[4] & 4):
        raise ValueError("Length/identity mismatch")
    expected = int.from_bytes(packet[-2:], "little")
    if binascii.crc_hqx(packet[:-2], 0xFFFF) != expected:
        raise ValueError("CRC mismatch")
    sequence, sample_time, fresh = struct.unpack_from("<III", packet, 6)
    if fresh >> channels:
        raise ValueError("Fresh mask contains nonexistent channels")
    temperature = struct.unpack_from("<" + "h" * channels, packet, 18)
    start = 18 + 2 * channels
    pressure = tuple(int.from_bytes(packet[i:i + 3], "little", signed=True)
                     for i in range(start, start + 3 * channels, 3))
    return Frame(packet[3], packet[4], packet[5], sequence, sample_time,
                 fresh, temperature, pressure)


class StreamDecoder:
    """Handles arbitrary USB chunk boundaries, noise, and damaged frames."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.rejected_candidates = 0
        self.discarded_bytes = 0

    def feed(self, data: bytes) -> list[Frame]:
        self.buffer.extend(data)
        result = []
        while True:
            index = self.buffer.find(SYNC)
            if index < 0:
                keep = 1 if self.buffer.endswith(SYNC[:1]) else 0
                drop = len(self.buffer) - keep
                self.discarded_bytes += drop
                del self.buffer[:drop]
                break
            self.discarded_bytes += index
            del self.buffer[:index]
            if len(self.buffer) < 5:
                break
            length = self.buffer[2]
            if (length not in (80, 180) or self.buffer[3] >> 4 != 2
                    or length != 20 + (32 if self.buffer[4] & 2 else 12) * 5):
                self.rejected_candidates += 1
                self.discarded_bytes += 1
                del self.buffer[0]
                continue
            if len(self.buffer) < length:
                break
            try:
                frame = decode_frame(bytes(self.buffer[:length]))
            except ValueError:
                self.rejected_candidates += 1
                self.discarded_bytes += 1
                del self.buffer[0]
                continue
            result.append(frame)
            del self.buffer[:length]
        return result


class CaptureStats:
    """Single identity statistics, with explicit wrap/reset handling.

    Rate is derived from MCU sample-start timestamps, not USB arrival time.
    A backward sequence/time jump is a reset or out-of-order observation;
    it never becomes billions of fabricated missing packets.
    """

    def __init__(self) -> None:
        self.frames = 0
        self.previous: Frame | None = None
        self.missing_slots = 0
        self.duplicates = 0
        self.resets_or_reorders = 0
        self.sequence_steps = 0
        self.observed_intervals = 0
        self.elapsed_us = 0
        self.full_fresh_frames = 0
        self.fresh_counts: list[int] = []
        self.status_counts: Counter[str] = Counter()

    def add(self, frame: Frame) -> None:
        if self.previous and frame.identity != self.previous.identity:
            raise ValueError("Use separate CaptureStats for each identity")
        if not self.fresh_counts:
            self.fresh_counts = [0] * frame.channels
        self.frames += 1
        self.full_fresh_frames += int(frame.fresh_mask == (1 << frame.channels) - 1)
        for channel in range(frame.channels):
            self.fresh_counts[channel] += (frame.fresh_mask >> channel) & 1
        for bit, name in enumerate(STATUS_NAMES):
            if frame.status & (1 << bit):
                self.status_counts[name] += 1
        if self.previous:
            steps = (frame.sequence - self.previous.sequence) & 0xFFFFFFFF
            elapsed = (frame.sample_time_us - self.previous.sample_time_us) & 0xFFFFFFFF
            if steps == 0:
                self.duplicates += 1
            elif steps >= 0x80000000 or elapsed == 0 or elapsed >= 0x80000000:
                self.resets_or_reorders += 1
            else:
                self.missing_slots += steps - 1
                self.sequence_steps += steps
                self.observed_intervals += 1
                self.elapsed_us += elapsed
        self.previous = frame

    def summary(self) -> dict:
        frame = self.previous
        if frame is None:
            return {"frames": 0}
        return {
            "identity_hex": f"0x{frame.identity:02X}",
            "hand": frame.hand, "channels": frame.channels, "cable": frame.cable,
            "mapping_revision": frame.mapping_revision,
            "wire_version_hex": f"0x{frame.version:02X}",
            "frames": self.frames, "missing_slots": self.missing_slots,
            "duplicates": self.duplicates, "resets_or_reorders": self.resets_or_reorders,
            "mcu_scheduled_rate_hz": (self.sequence_steps * 1e6 / self.elapsed_us
                                      if self.elapsed_us else None),
            "mcu_received_rate_hz": (self.observed_intervals * 1e6 / self.elapsed_us
                                     if self.elapsed_us else None),
            "full_fresh_frame_fraction": self.full_fresh_frames / self.frames,
            "per_channel_fresh_fraction": [n / self.frames for n in self.fresh_counts],
            "status_frame_counts": dict(self.status_counts),
        }


def inspect_capture(path: Path) -> dict:
    decoder = StreamDecoder()
    boards: dict[int, CaptureStats] = {}
    total_bytes = 0
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            total_bytes += len(chunk)
            for frame in decoder.feed(chunk):
                boards.setdefault(frame.identity, CaptureStats()).add(frame)
    return {
        "input": str(path.resolve()), "bytes": total_bytes,
        "valid_frames": sum(stats.frames for stats in boards.values()),
        "rejected_candidates": decoder.rejected_candidates,
        "discarded_bytes": decoder.discarded_bytes,
        "trailing_incomplete_bytes": len(decoder.buffer),
        "boards": [stats.summary() for _, stats in sorted(boards.items())],
        "rate_basis": "MCU sample-start timestamps; verify wall-clock UART timing separately",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path, help="Optional JSON report")
    args = parser.parse_args()
    report = inspect_capture(args.capture)
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(encoded, end="")
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    return 0 if report["valid_frames"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

