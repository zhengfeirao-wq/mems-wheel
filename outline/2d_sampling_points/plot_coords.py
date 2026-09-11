# -*- coding: utf-8 -*-
"""绘制触觉传感器坐标分布图（Big=32点板 / Small=12点板）。

坐标数据来自常量模块 sensor_coords.py（单一数据源），本脚本不再自己读 CSV。
用 --verify-csv 可以额外校验常量表与原始 CSV 逐字一致。

坐标方向：默认 **Y 轴向上**；--flip 可上下镜像。
所有面板强制 **X/Y 等比例**（1 单位 X = 1 单位 Y），并打印实测 像素/单位 比值校验。

输出：
    coord_plot_all.png      总览：Big | Small | 两板叠加
    coord_plot_big32.png    32 点板单独大图
    coord_plot_small12.png  12 点板单独大图

用法：
    python plot_coords.py                # Y 轴向上
    python plot_coords.py --flip         # Y 轴向下
    python plot_coords.py --verify-csv   # 顺带校验常量 vs CSV
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colormaps
from matplotlib import colors as mcolors
from matplotlib.lines import Line2D

import sensor_coords as SC

HERE = Path(__file__).resolve().parent
CSV_BIG = HERE / "coord_Big_raw.csv"
CSV_SMALL = HERE / "coord_Small_raw.csv"

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["font.monospace"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans Mono"]
plt.rcParams["axes.unicode_minus"] = False

C_BIG = "#1f5fa8"
C_SMALL = "#c0392b"
BOX = dict(boxstyle="round,pad=0.42", fc="#f4f7fa", ec="#98a6b3", lw=0.8, alpha=0.95)

INVERT_Y = False
Y_NOTE = "Y 轴向上"
PAD_FRAC, PAD_ABS = 0.12, 1.0


# --------------------------------------------------------------------------- 数据
def unpack(coords):
    """((ch, x, y), ...) -> (ids, xs, ys)"""
    return ([c[0] for c in coords], [c[1] for c in coords], [c[2] for c in coords])


def verify_csv():
    """校验常量表与原始 CSV 逐字一致。"""
    ok = True
    for label, path, coords in (("Big", CSV_BIG, SC.BIG_32_COORDS),
                                ("Small", CSV_SMALL, SC.SMALL_12_COORDS)):
        if not path.exists():
            print(f"  [SKIP] {path.name} 不存在")
            continue
        with path.open(newline="", encoding="utf-8-sig") as fh:
            raw = [(int(r["sensor_Number"]), float(r["X_coord"]), float(r["Y_coord"]))
                   for r in csv.DictReader(fh)]
        same = len(raw) == len(coords) and all(
            a[0] == b[0] and a[1] == b[1] and a[2] == b[2] for a, b in zip(raw, coords))
        ok &= same
        print(f"  [{'OK ' if same else 'BAD'}] {label}: 常量表 {len(coords)} 点 "
              f"vs CSV {len(raw)} 点 —— {'逐字一致' if same else '不一致！'}")
    return ok


# --------------------------------------------------------------------------- 绘图
def draw_points(ax, ids, xs, ys, rows=(), marker="o", size=190, label_fs=8.5,
                fixed_color=None, row_lines=True):
    cmap = colormaps["turbo"]
    norm = mcolors.Normalize(vmin=1, vmax=len(ids))
    pos = dict(zip(ids, zip(xs, ys)))

    if row_lines and rows:
        for chans in rows:
            pts = sorted(pos[c] for c in chans if c in pos)
            if len(pts) >= 2:
                ax.plot([p[0] for p in pts], [p[1] for p in pts],
                        ls="--", lw=0.8, color="#9aa4b0", alpha=0.55, zorder=1)

    for n, x, y in zip(ids, xs, ys):
        ax.scatter(x, y, s=size, marker=marker,
                   c=[fixed_color or cmap(norm(n))],
                   edgecolors="white", linewidths=1.1, zorder=3)
        ax.annotate(str(n), (x, y), xytext=(4.0, 3.2),
                    textcoords="offset points", fontsize=label_fs,
                    fontweight="bold", color="#12212e", zorder=4,
                    bbox=dict(boxstyle="round,pad=0.10", fc="white",
                              ec="none", alpha=0.62))


def finish_axes(ax, win, title, sub="", tick_fs=8.5, origin_mark=False,
                xlabel="X_coord", ylabel="Y_coord"):
    x0, x1, y0, y1, _ = win
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal", adjustable="box", anchor="C")
    if INVERT_Y:
        ax.invert_yaxis()
    ax.grid(True, ls=":", lw=0.6, color="#b8c2cc", alpha=0.9)
    ax.set_axisbelow(True)
    ax.set_xlabel(xlabel, fontsize=9.5)
    ax.set_ylabel(ylabel, fontsize=9.5)
    ax.set_title(title, fontsize=11.5, fontweight="bold", pad=26 if sub else 8)
    if sub:
        ax.text(0.5, 1.012, sub, transform=ax.transAxes, ha="center",
                va="bottom", fontsize=8.6, color="#41505e")
    if origin_mark:
        # 红框标出原点 (0, 0)：左下角。文字放到轴下方，避免压住原点附近的通道号
        ax.plot([0.0], [0.0], marker="s", ms=13, mfc="none", mec="#d62728",
                mew=1.8, zorder=6, clip_on=False)
        ax.annotate("原点 (0,0)", (0.0, 0.0), xytext=(3, -17),
                    textcoords="offset points", fontsize=9, fontweight="bold",
                    color="#d62728", zorder=7, ha="left", va="top")
    ax.tick_params(labelsize=tick_fs)


def window(datasets, anchored=False):
    """返回坐标窗口 (x0, x1, y0, y1, 宽高比)。

    anchored=True 时用很小的下侧留白，让 (0, 0) 就贴在坐标轴左下角。
    """
    xs = [v for d in datasets for v in d[1]]
    ys = [v for d in datasets for v in d[2]]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if anchored:
        px = (x1 - x0) * 0.05
        py = (y1 - y0) * 0.05
        x0, x1, y0, y1 = -px, x1 + px, -py, y1 + py
    else:
        mx = (x1 - x0) * PAD_FRAC + PAD_ABS
        my = (y1 - y0) * PAD_FRAC + PAD_ABS
        x0, x1, y0, y1 = x0 - mx, x1 + mx, y0 - my, y1 + my
    return x0, x1, y0, y1, (x1 - x0) / (y1 - y0)


# --------------------------------------------------- 说明框（自动挑不遮挡的角落）
def _text_size_pt(text, fontsize):
    lines = text.split("\n")
    half = max(sum(2 if ord(c) > 0x2E80 else 1 for c in ln) for ln in lines)
    return half * 0.60 * fontsize + 16.0, len(lines) * fontsize * 1.35 + 12.0


def _corner_rects(ax, frac_w, frac_h):
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    out = {}
    for name, (right, top) in (("right-bottom", (1, 0)), ("left-bottom", (0, 0)),
                               ("right-top", (1, 1)), ("left-top", (0, 1))):
        bx0 = 1.0 - frac_w if right else 0.0
        by0 = 1.0 - frac_h if top else 0.0
        out[name] = (x0 + bx0 * (x1 - x0), x0 + (bx0 + frac_w) * (x1 - x0),
                     y0 + by0 * (y1 - y0), y0 + (by0 + frac_h) * (y1 - y0))
    return out


def info_box(ax, text, xs, ys, fontsize=8.2, tag=""):
    fig = ax.figure
    fig.canvas.draw()
    bb = ax.get_window_extent()
    w_pt, h_pt = _text_size_pt(text, fontsize)
    frac_w = min(0.98, 1.20 * w_pt / (bb.width * 72.0 / fig.dpi))
    frac_h = min(0.98, 1.20 * h_pt / (bb.height * 72.0 / fig.dpi))

    best, best_n = None, None
    for name, rect in _corner_rects(ax, frac_w, frac_h).items():
        n = sum(1 for x, y in zip(xs, ys)
                if rect[0] <= x <= rect[1] and rect[2] <= y <= rect[3])
        if best_n is None or n < best_n:
            best, best_n = name, n
    right, top = best.startswith("right"), best.endswith("top")
    ax.text(0.985 if right else 0.015, 0.985 if top else 0.015, text,
            transform=ax.transAxes, ha="right" if right else "left",
            va="top" if top else "bottom", fontsize=fontsize,
            family="monospace", bbox=BOX, zorder=10)
    print(f"    说明框[{tag}] 角落={best:13s} 覆盖数据点 {best_n} 个")
    return best_n


def verify_aspect(fig, panels):
    fig.canvas.draw()
    ok = True
    for name, ax in panels:
        bb = ax.get_window_extent()
        (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
        ux, uy = bb.width / (x1 - x0), bb.height / (y1 - y0)
        good = abs(ux / uy - 1.0) < 0.005
        ok &= good
        print(f"  [{'OK ' if good else 'BAD'}] {name:26s} px/unit  "
              f"X={ux:7.3f}  Y={uy:7.3f}  ratio={ux / uy:.4f}")
    return ok


# --------------------------------------------------------------------------- 主流程
def main() -> int:
    global INVERT_Y
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flip", action="store_true",
                        help="Y 轴向下（上下镜像）；默认 Y 轴向上")
    parser.add_argument("--raw", action="store_true",
                        help="用原始绝对坐标；默认把每块板左下角平移到 (0, 0)")
    parser.add_argument("--verify-csv", action="store_true",
                        help="校验 sensor_coords.py 的常量与原始 CSV 是否一致")
    args = parser.parse_args()
    INVERT_Y = bool(args.flip)
    arrow = "↑" if not INVERT_Y else "↓"
    anchored = not args.raw

    if args.verify_csv:
        print("常量表 vs CSV 校验:")
        if not verify_csv():
            return 1

    if anchored:
        big = unpack(SC.BIG_32_COORDS_REL)
        small = unpack(SC.SMALL_12_COORDS_REL)
        rows_big = [chs for _, chs in SC.BIG_32_ROWS_REL]
        rows_small = [chs for _, chs in SC.SMALL_12_ROWS_REL]
        ylabel = "Y_coord（相对左下角）"
        xlabel = "X_coord（相对左下角）"
        origin_note = "左下角 = (0, 0)"
        print(f"数据源: sensor_coords.py　{origin_note}　Y 轴方向: {Y_NOTE}（{arrow}）")
        print(f"  平移量　Big {SC.BIG_32_ORIGIN}　Small {SC.SMALL_12_ORIGIN}")
        print(f"  尺寸　　Big {SC.BIG_32_SIZE[0]:.4f} × {SC.BIG_32_SIZE[1]:.4f}　"
              f"Small {SC.SMALL_12_SIZE[0]:.4f} × {SC.SMALL_12_SIZE[1]:.4f}")
    else:
        big = unpack(SC.BIG_32_COORDS)
        small = unpack(SC.SMALL_12_COORDS)
        rows_big = [chs for _, chs in SC.BIG_32_ROWS]
        rows_small = [chs for _, chs in SC.SMALL_12_ROWS]
        ylabel = xlabel = None
        origin_note = "原始绝对坐标"
        print(f"数据源: sensor_coords.py　{origin_note}　Y 轴方向: {Y_NOTE}（{arrow}）")
    xlabel = xlabel or "X_coord"
    ylabel = ylabel or "Y_coord"

    w_big = window([big], anchored)
    w_small = window([small], anchored)
    w_both = window([big, small], anchored)
    covered = 0

    # ============================== 总览图 ==============================
    fig = plt.figure(figsize=(15.5, 14.5))
    gs = fig.add_gridspec(2, 2, left=0.058, right=0.985, top=0.905, bottom=0.05,
                          height_ratios=[1.0, 1.25], width_ratios=[1.5, 1.0],
                          hspace=0.34, wspace=0.12)

    ax = fig.add_subplot(gs[0, 0])
    draw_points(ax, *big, rows=rows_big)
    finish_axes(ax, w_big, f"（a）Big　32 点板　{Y_NOTE}　{origin_note}",
                f"点数 {len(big[0])}　点的颜色 = 通道号　虚线 = 同一行　Y{arrow}",
                origin_mark=anchored, xlabel=xlabel, ylabel=ylabel)
    covered += info_box(ax, "24 点主阵列：6 列 × 4 行\n"
                            "第 5 行 7 点：通道 7–13\n"
                            "通道 16：独立单点", big[1], big[2], tag="Big")

    ax = fig.add_subplot(gs[0, 1])
    draw_points(ax, *small, rows=rows_small, marker="s", size=150)
    finish_axes(ax, w_small, f"（b）Small　12 点板　{Y_NOTE}　{origin_note}",
                f"点数 {len(small[0])}　色标 = 通道号　虚线 = 同一行\n"
                f"3×2 阵列（通道 1–6）+ 2×3 阵列（通道 7–12）",
                origin_mark=anchored, xlabel=xlabel, ylabel=ylabel)

    ax = fig.add_subplot(gs[1, :])
    draw_points(ax, *big, row_lines=False, size=200, label_fs=9.5, fixed_color=C_BIG)
    draw_points(ax, *small, marker="s", row_lines=False, size=200,
                fixed_color=C_SMALL, label_fs=9.5)
    sub = ("两板各自以左下角为原点 → 可直接比较尺寸与节距"
           if anchored else
           "两者 X 区间互不重叠（Small 在左、Big 在右）→ 可能取自同一模型的两个部位")
    finish_axes(ax, w_both, f"（c）两块板叠加　同一坐标系、等比例　{Y_NOTE}"
                            f"　{origin_note}", sub,
                origin_mark=anchored, xlabel=xlabel, ylabel=ylabel)
    ax.legend(handles=[
        Line2D([], [], marker="o", ls="", mfc=C_BIG, mec="white", ms=10,
               label="Big  32 点"),
        Line2D([], [], marker="s", ls="", mfc=C_SMALL, mec="white", ms=10,
               label="Small 12 点"),
    ], loc="lower left", fontsize=10, framealpha=0.95, borderpad=0.7)

    fig.suptitle("触觉传感器坐标分布图      Big = 32 点板      Small = 12 点板",
                 fontsize=16, fontweight="bold")
    ok_all = verify_aspect(fig, [("overlay", fig.axes[0]), ("Big32", fig.axes[1]),
                                 ("Small12", fig.axes[2])])
    fig.savefig(HERE / "coord_plot_all.png", dpi=160, facecolor="white")
    plt.close(fig)

    # ============================== 单板大图 ==============================
    for name, data, rows, win, marker, title, note in (
        ("coord_plot_big32.png", big, rows_big, w_big, "o",
         f"Big：32 点板传感器坐标（{Y_NOTE}，{origin_note}）",
         "24 点主阵列：6 列 × 4 行\n"
         f"副行 7 点：通道 {SC.BIG_32_SIDE_ROW[0]}–{SC.BIG_32_SIDE_ROW[-1]}"
         "（列距 ≈5.8，另一套栅格）\n"
         f"独立点：通道 {SC.BIG_32_STANDALONE}"),
        ("coord_plot_small12.png", small, rows_small, w_small, "s",
         f"Small：12 点板传感器坐标（{Y_NOTE}，{origin_note}）",
         f"上排 3 列 × 2 行 = 6 点（通道 "
         f"{SC.SMALL_12_TOP_CHANNELS[0]}–{SC.SMALL_12_TOP_CHANNELS[-1]}，列距 ≈5.67）\n"
         f"下排 2 列 × 3 行 = 6 点（通道 "
         f"{SC.SMALL_12_BOTTOM_CHANNELS[0]}–{SC.SMALL_12_BOTTOM_CHANNELS[-1]}，"
         "列距 ≈9.24）"),
    ):
        aspect = win[4]
        size_txt = (f"尺寸 {SC.size_for(len(data[0]))[0]:.4f} × "
                    f"{SC.size_for(len(data[0]))[1]:.4f}")
        sub = f"{size_txt}　色标 = 通道号　虚线 = 同一行"
        if aspect >= 1.0:
            # 宽板：说明框放轴内空角落（文字尽量短，否则会压到数据点）
            note_text = f"点数 {len(data[0])}\n{note}"
            fig_w = 11.5
            fig = plt.figure(figsize=(fig_w, min(fig_w / aspect + 1.9, 20.0)))
            ax = fig.add_axes([0.11, 0.075, 0.865, 0.855])
            draw_points(ax, *data, rows=rows, marker=marker, size=340, label_fs=11.5)
            finish_axes(ax, win, title, sub=sub, tick_fs=9.5, origin_mark=anchored,
                        xlabel=xlabel, ylabel=ylabel)
            covered += info_box(ax, note_text, data[1], data[2], tag=name)
        else:
            # 窄高板：说明放轴外右侧，保证不遮挡任何数据点
            note_text = (f"点数 {len(data[0])}　色标 = 通道号\n"
                         f"虚线 = 同一行\n{size_txt}\n\n{note}")
            fig = plt.figure(figsize=(11.5, 14.0))
            ax_h, left = 0.86, 0.055
            ax_w = (14.0 * ax_h * aspect) / 11.5
            ax = fig.add_axes([left, 0.07, ax_w, ax_h])
            draw_points(ax, *data, rows=rows, marker=marker, size=340, label_fs=11.5)
            finish_axes(ax, win, title, tick_fs=9.5, origin_mark=anchored,
                        xlabel=xlabel, ylabel=ylabel)
            fig.text(left + ax_w + 0.045, 0.5, note_text, ha="left", va="center",
                     fontsize=9.5, family="monospace", bbox=BOX)
            print(f"    说明框[{name}] 置于轴外右侧，覆盖数据点 0 个")
        ok_all &= verify_aspect(fig, [(name, ax)])
        fig.savefig(HERE / name, dpi=170, facecolor="white")
        plt.close(fig)

    print("\n已输出: coord_plot_all.png / coord_plot_big32.png / coord_plot_small12.png")
    print(f"校验: 等比例 {'通过' if ok_all else '失败'}"
          f"　说明框遮挡 {'0 点，通过' if covered == 0 else f'{covered} 点，需检查'}")
    return 0 if (ok_all and covered == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
