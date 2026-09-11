"""Short G1 baseline probe: native V2 frames, before software synchronization."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import platform
import time

from tactile500.protocol import CaptureStats, StreamDecoder
from tactile500.transport.pyusb_ch340 import CH340PyUsbTransport, enumerate_devices


def probe(path, seconds, read_size):
    transport = CH340PyUsbTransport(path, read_size=read_size, read_timeout_ms=50)
    parser = StreamDecoder()
    stats = {}
    first_read_ns = last_read_ns = None
    count_bytes = reads = 0
    first_hex = ""
    examples = {}
    byte_counts = Counter()
    sync_counts = Counter()
    previous_tail = b""
    try:
        transport.open()
        started = time.monotonic()
        while time.monotonic() - started < seconds:
            chunk = transport.read(0.05)
            ended_ns = time.monotonic_ns()
            if not chunk:
                continue
            if first_read_ns is None:
                first_read_ns = ended_ns
                first_hex = chunk[:96].hex(" ")
            last_read_ns = ended_ns
            reads += 1
            count_bytes += len(chunk)
            byte_counts.update(chunk)
            combined = previous_tail + chunk
            sync_counts["v2_A55A"] += combined.count(b"\xa5\x5a")
            sync_counts["legacy_4254"] += combined.count(b"\x42\x54")
            previous_tail = chunk[-1:]
            for frame in parser.feed(chunk):
                stats.setdefault(frame.identity, CaptureStats()).add(frame)
                examples[frame.identity] = {
                    "sequence": frame.sequence, "sample_time_us": frame.sample_time_us,
                    "status_hex": f"0x{frame.status:02X}", "fresh_mask_hex": f"0x{frame.fresh_mask:08X}",
                    "temperature": frame.temperature, "pressure": frame.pressure,
                }
        elapsed = time.monotonic() - started
        total = sum(s.frames for s in stats.values())
        return {
            "path": path, "descriptor": transport.descriptor, "read_size": read_size,
            "elapsed_s": elapsed, "bytes": count_bytes, "reads": reads, "valid_frames": total,
            "host_frames_per_second": total / elapsed,
            "first_bytes_hex": first_hex,
            "sync_counts": dict(sync_counts),
            "most_common_bytes": byte_counts.most_common(12),
            "rejected_candidates": parser.rejected_candidates,
            "discarded_bytes": parser.discarded_bytes,
            "trailing_bytes": len(parser.buffer),
            "boards": [s.summary() for s in stats.values()], "last_frame_by_identity": examples,
        }
    except Exception as error:
        return {"path": path, "error": type(error).__name__ + ": " + str(error)}
    finally:
        transport.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--read-size", type=int, default=160)
    args = parser.parse_args()
    paths = [d.path for d in enumerate_devices()]
    print(json.dumps({"event": "enumerated", "paths": paths, "kernel": platform.release(),
                      "machine": platform.machine()}, ensure_ascii=False), flush=True)
    with ThreadPoolExecutor(max_workers=max(1, len(paths))) as pool:
        reports = list(pool.map(lambda path: probe(path, args.seconds, args.read_size), paths))
    print(json.dumps({"event": "baseline_results", "devices": reports}, ensure_ascii=False, indent=2),
          flush=True)


if __name__ == "__main__":
    main()
