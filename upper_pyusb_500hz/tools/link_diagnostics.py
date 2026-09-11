"""Compare USB read sizes and preserve pre-parser UART bytes for loss diagnosis."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time

from tactile500.protocol import StreamDecoder, CaptureStats, decode_frame
from tactile500.transport.pyusb_ch340 import CH340PyUsbTransport, enumerate_devices


def run(path, size, seconds, directory):
    transport = CH340PyUsbTransport(path, read_size=size)
    raw = bytearray()
    gaps = []
    last = None
    transport.open()
    try:
        start = time.monotonic()
        while time.monotonic() - start < seconds:
            chunk = transport.read(0.050)
            now = time.monotonic_ns()
            if chunk:
                if last is not None:
                    gaps.append(now - last)
                last = now
                raw.extend(chunk)
    finally:
        transport.close()
    out = directory / f"{path}_read{size}.bin"
    out.write_bytes(raw)
    decoder = StreamDecoder()
    frames = decoder.feed(raw)
    stats = CaptureStats()
    for frame in frames:
        stats.add(frame)
    headers = []
    i = 0
    while True:
        i = raw.find(b"\xa5\x5a", i)
        if i < 0:
            break
        if i + 5 < len(raw) and raw[i + 2] in (80, 180) and raw[i + 3] == 0x21:
            headers.append(i)
        i += 1
    bad = []
    for k, offset in enumerate(headers[:-1]):
        length = raw[offset + 2]
        packet = bytes(raw[offset:offset + length])
        try:
            decode_frame(packet)
        except ValueError:
            if len(bad) < 12:
                bad.append({"offset": offset, "next_header_distance": headers[k + 1] - offset,
                            "hex": packet.hex()})
    gaps.sort()
    return {"path": path, "read_size": size, "bytes": len(raw), "report": stats.summary(),
            "rejected": decoder.rejected_candidates, "discarded": decoder.discarded_bytes,
            "header_distances": dict(Counter(b - a for a, b in zip(headers, headers[1:]))),
            "read_gap_ms": {str(p): gaps[min(len(gaps) - 1, int(len(gaps) * p))] / 1e6
                            for p in (0.5, 0.99, 0.999, 1.0)} if gaps else {},
            "bad_examples": bad, "raw_file": str(out)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=15)
    parser.add_argument("--sizes", default="160,512,1024")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    paths = [d.path for d in enumerate_devices()]
    reports = []
    for size in map(int, args.sizes.split(",")):
        with ThreadPoolExecutor(max_workers=max(1, len(paths))) as pool:
            rows = list(pool.map(lambda p: run(p, size, args.seconds, args.output), paths))
        reports.extend(rows)
        print(json.dumps({"size": size, "devices": [{"path": r["path"], "rejected": r["rejected"],
              "missing": r["report"].get("missing_slots"), "distances": r["header_distances"],
              "read_gap_ms": r["read_gap_ms"]} for r in rows]}), flush=True)
    (args.output / "diagnostics.json").write_text(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
