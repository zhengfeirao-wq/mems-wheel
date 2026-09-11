"""Measure wire integrity and equal adjacent pressure codes, separately.

Usage: python tools/analyze_repeated_values.py SESSION_DIR OUTPUT_DIR
Equal codes are observations, not proof of reused ADC conversions.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from tactile500 import read_recording
from tactile500.protocol import CaptureStats

def channel_metrics(values, elapsed_s):
    valid = values != -8388608
    adjacent = valid[1:] & valid[:-1]
    changed = adjacent & (values[1:] != values[:-1])
    equal = adjacent & ~changed
    changes = np.flatnonzero(changed) + 1
    count = int(adjacent.sum())
    intervals = np.diff(changes)
    return {
        "valid_adjacent_pairs": count,
        "equal_adjacent_pairs": int(equal.sum()),
        "equal_fraction": float(equal.sum() / count) if count else None,
        "observed_code_changes": int(changed.sum()),
        "observed_changes_per_second": float(changed.sum() / elapsed_s),
        "change_interval_frames": dict(sorted(Counter(map(int, intervals)).items())),
        "four_or_five_frame_interval_fraction": (
            float(np.isin(intervals, [4, 5]).mean()) if len(intervals) else None),
    }

def main():
    source = Path(sys.argv[1])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "definition": "adjacent pressure code equality; not an ADC freshness count",
        "boards": [],
    }
    for path in sorted((source / "capture").rglob("*.t5raw")):
        records = list(read_recording(path))
        if len(records) < 2:
            continue
        frames = [x.frame for x in records]
        first = frames[0]
        stats = CaptureStats()
        for frame in frames:
            stats.add(frame)
        host_duration = (records[-1].host_read_end_ns - records[0].host_read_end_ns) / 1e9
        mcu = np.array([x.sample_time_us for x in frames], dtype=np.int64)
        dt_us = np.diff(mcu) & 0xffffffff
        if np.any(dt_us > 1000000):
            raise ValueError("segment contains a reset or a gap over one second")
        mcu_elapsed = np.r_[0, np.cumsum(dt_us)] / 1e6
        pressure = np.array([x.pressure for x in frames], dtype=np.int64)
        channels = [
            dict(wire_channel=c+1, **channel_metrics(pressure[:, c], mcu_elapsed[-1]))
            for c in range(first.channels)
        ]
        repeats = np.array([x["equal_fraction"] for x in channels])
        changes = np.array([x["observed_changes_per_second"] for x in channels])
        vector_valid = np.all(pressure != -8388608, axis=1)
        vector_pair = vector_valid[1:] & vector_valid[:-1]
        board = {
            "identity": f"0x{first.identity:02X}",
            "hand": first.hand, "channels": first.channels, "cable": first.cable,
            "source": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "frames": len(frames), "host_seconds": host_duration,
            "host_received_hz": (len(frames)-1)/host_duration,
            "mcu_time_delta_us_counts": dict(sorted(Counter(map(int, dt_us)).items())),
            "capture_stats": stats.summary(),
            "per_channel_equal_fraction_median": float(np.median(repeats)),
            "per_channel_equal_fraction_min": float(repeats.min()),
            "per_channel_equal_fraction_max": float(repeats.max()),
            "observed_changes_per_second_median": float(np.median(changes)),
            "observed_changes_per_second_min": float(changes.min()),
            "observed_changes_per_second_max": float(changes.max()),
            "whole_pressure_vector_equal_fraction": float(
                (np.all(pressure[1:] == pressure[:-1], axis=1) & vector_pair).sum()
                / vector_pair.sum()),
            "per_channel": channels,
        }
        if first.channels == 12 and first.hand == "right":
            mask = (mcu_elapsed >= 38) & (mcu_elapsed < 46)
            board["active_example"] = {
                "wire_channel": 12, "window_mcu_elapsed_s": [38, 46],
                **channel_metrics(pressure[mask, 11],
                                  float(mcu_elapsed[mask][-1] - mcu_elapsed[mask][0])),
            }
        report["boards"].append(board)
    if not report["boards"]:
        raise ValueError("no recordings")
    (out / "repeat_metrics.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                           encoding="utf-8")
    for board in report["boards"]:
        print(json.dumps({k: v for k, v in board.items()
                          if k not in ("per_channel", "source", "sha256", "capture_stats")},
                         ensure_ascii=False))
    lines = ["# 原始压力相邻码值重复统计", "",
             "重复率 = 有效相邻帧压力码值相同的次数 / 有效相邻帧对数。",
             "它不是转换就绪标志，也不是API复用同一个序号的比例。",
             "全段包含静止与加载；新转换也可能产生相同码值。", ""]
    for board in report["boards"]:
        lines += [f"## {board['hand']} {board['channels']}点 {board['cable']}", "",
                  "| MCU通道 | 相邻码值重复率 | 观察到的码值改变次数/秒 |",
                  "|---|---:|---:|"]
        for channel in board["per_channel"]:
            lines.append(f"| CH{channel['wire_channel']:02d} | "
                         f"{channel['equal_fraction']:.3%} | "
                         f"{channel['observed_changes_per_second']:.3f} |")
        lines.append("")
    (out / "逐通道重复率.md").write_text("\n".join(lines), encoding="utf-8")

if __name__ == "__main__":
    main()

