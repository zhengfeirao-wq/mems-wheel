"""Reproducible unsmoothed experimental traces from exact V2 recordings.

Chart contract: compare channel response over host elapsed time using faceted
line plots. Independent labelled y scales preserve small signals. Blue for
ordinary channels, gold for CH12. PNG/SVG are standalone scientific artifacts.
Baseline subtraction is only a display transform; raw arrays are retained.
"""
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import numpy as np

from tactile500 import read_recording
from tactile500.protocol import CaptureStats
from tactile500.mapping import SHORT_POSITION_TO_CHANNEL

root = Path(sys.argv[1])
font = Path("C:/Windows/Fonts/msyh.ttc")
if font.exists():
    from matplotlib import font_manager
    font_manager.fontManager.addfont(str(font))
    plt.rcParams["font.family"] = FontProperties(fname=str(font)).get_name()
plt.rcParams.update({"axes.unicode_minus": False, "font.size": 11,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.labelcolor": "#30383f", "text.color": "#30383f",
                     "xtick.color": "#58616a", "ytick.color": "#58616a",
                     "path.simplify": False, "svg.fonttype": "none"})
out = root / "plots"
out.mkdir(exist_ok=True)
loaded = []
for path in sorted((root / "capture").rglob("*.t5raw")):
    items = list(read_recording(path))
    if not items:
        continue
    stats = CaptureStats()
    for item in items:
        stats.add(item.frame)
    loaded.append((path, items, stats.summary()))
if not loaded:
    raise RuntimeError("no complete records")
origin = min(items[0].host_read_end_ns for _, items, _ in loaded)
reports = []


def save(fig, name):
    fig.savefig(out / (name + ".png"), dpi=160, facecolor="white")
    fig.savefig(out / (name + ".svg"), facecolor="white")
    plt.close(fig)


def decorate(ax):
    ax.grid(axis="y", color="#e4e8eb", linewidth=.6)
    ax.axhline(0, color="#aeb6bd", linewidth=.6)
    ax.tick_params(labelsize=9)
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)


for path, items, stats in loaded:
    frame = items[0].frame
    t = np.array([(x.host_read_end_ns - origin) / 1e9 for x in items])
    raw = np.array([x.frame.pressure for x in items], dtype=float)
    temp = np.array([x.frame.temperature for x in items], dtype=float) / 10
    raw[raw == -8388608] = np.nan
    temp[temp == -3276.8] = np.nan
    source_order = np.arange(frame.channels)
    if frame.channels == 32 and frame.cable == "short":
        source_order = np.array(SHORT_POSITION_TO_CHANNEL) - 1
    raw = raw[:, source_order]
    temp = temp[:, source_order]
    baseline = np.nanmedian(raw[t <= t[0] + .5], axis=0)
    delta = raw - baseline
    span = np.nanmax(raw, axis=0) - np.nanmin(raw, axis=0)
    hand_label = "左" if frame.hand == "left" else "右"
    cable_label = "短线" if frame.cable == "short" else "长线"
    label = f"{hand_label}{frame.channels}点" + (cable_label if frame.channels == 32 else "") + "板"
    name = frame.hand + str(frame.channels)
    mapping_note = ("32点按已确认显示位置换序。" if frame.channels == 32 and frame.cable == "short"
                    else "长线32点按用户确认的MCU已排列通道顺序显示。" if frame.channels == 32
                    else "12点显示MCU通道顺序。")
    np.savez_compressed(out / (name + "_data.npz"), host_elapsed_s=t,
                        pressure=raw, delta=delta, temperature_c=temp,
                        source_channel=source_order + 1, baseline=baseline)
    # Gaps are broken explicitly; they are never drawn as invented observations.
    seq = np.array([x.frame.sequence for x in items], dtype=np.uint64)
    gaps = np.flatnonzero(((seq[1:] - seq[:-1]) & 0xffffffff) != 1) + 1
    plotted = delta.copy()
    plotted[gaps] = np.nan
    groups = [range(12)] if frame.channels == 12 else [range(16), range(16, 32)]
    for group_number, channels in enumerate(groups):
        cols = 3 if frame.channels == 12 else 4
        fig, axes = plt.subplots(4, cols, figsize=(16, 12), sharex=True)
        for ax, channel in zip(axes.flat, channels):
            color = "#b58221" if frame.channels == 12 and channel == 11 else "#356a99"
            ax.plot(t, plotted[:, channel], linewidth=.7, color=color)
            ax.set_title(f"CH{channel+1:02d} ← ch{source_order[channel]+1:02d}   范围 {span[channel]:.0f}",
                         loc="left", fontsize=11)
            decorate(ax)
            ax.set_xlim(t[0], t[-1])
        for ax in axes[-1]:
            ax.set_xlabel("主机接收相对时间 / s")
        for ax in axes[:, 0]:
            ax.set_ylabel("压力变化量 / 码值")
        fig.suptitle(label + " · 压力曲线" + (f"（{group_number+1}/2）" if len(groups)>1 else ""),
                     fontsize=20, x=.07, ha="left", y=.985)
        fig.text(.07, .946, f"{len(items):,}个原始帧 · {t[-1]-t[0]:.2f}秒 · 未平滑 · 各子图纵轴独立，不能按线条高度比较幅度", fontsize=12)
        fig.text(.07, .016, "显示基线：每通道前0.5秒中位数，仅作相减参考；压力未经力学校准。" + mapping_note, fontsize=10)
        fig.subplots_adjust(left=.075, right=.975, bottom=.075, top=.905, hspace=.4, wspace=.34)
        save(fig, name + "_pressure" + (f"_{group_number+1}" if len(groups)>1 else ""))
    if frame.channels == 12:
        fig, axes = plt.subplots(3, 1, figsize=(13, 10), sharex=True)
        axes[0].plot(t, raw[:, 11], color="#b58221", linewidth=.85)
        axes[0].set_ylabel("CH12压力原值")
        axes[0].set_title(f"CH12原值范围：{raw[:,11].min():.0f}～{raw[:,11].max():.0f}；跨度 {span[11]:.0f}", loc="left", fontsize=12)
        axes[1].plot(t, delta[:, 11], color="#b58221", linewidth=.85)
        axes[1].set_ylabel("CH12压力变化量")
        axes[1].set_title(f"减去参考基线 {baseline[11]:.0f}；纵轴已放大",loc="left", fontsize=12)
        axes[2].plot(t, temp[:, 11], color="#356a99", linewidth=.85)
        axes[2].set_ylabel("CH12温度 / °C")
        axes[2].set_xlabel("主机接收相对时间 / s")
        for ax in axes:
            ax.grid(axis="y", color="#e4e8eb", linewidth=.6)
            ax.ticklabel_format(axis="y", style="plain", useOffset=False)
            ax.set_xlim(t[0], t[-1])
        fig.suptitle(label + " · CH12细节", fontsize=20, x=.12, ha="left", y=.98)
        fig.text(.12,.934,"全部接收帧直接绘制，未平滑；没有按压时间标记，不能把峰值自动标作某次按压。",fontsize=11)
        fig.subplots_adjust(left=.12,right=.97,bottom=.08,top=.88,hspace=.38)
        save(fig,"ch12_detail")
    reports.append({"role":frame.role, "frames":len(items),"seconds":t[-1]-t[0],
                    "source":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                    "stats":stats,"source_channel":(source_order+1).tolist(),
                    "pressure_baseline":baseline.tolist(),"pressure_span":span.tolist(),
                    "pressure_min":np.nanmin(raw,axis=0).tolist(),"pressure_max":np.nanmax(raw,axis=0).tolist()})
(out/"summary.json").write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps([{"role":r["role"],"frames":r["frames"],"seconds":r["seconds"],
                  "missing":r["stats"]["missing_slots"],"pressure_span":r["pressure_span"]} for r in reports]))
