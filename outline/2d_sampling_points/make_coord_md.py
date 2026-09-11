# -*- coding: utf-8 -*-
"""由常量模块 sensor_coords.py 生成 Markdown 版布局图：传感器坐标图.md

内容：
  1) 嵌入 coord_plot_*.png
  2) 纯文本 ASCII 坐标图（不依赖图片也能看）
  3) 逐行坐标表 + 通道号
  4) 结构分析、常量模块用法、待确认项

用法：python make_coord_md.py
"""
from __future__ import annotations

import csv
import hashlib
from datetime import datetime
from pathlib import Path

import sensor_coords as SC

HERE = Path(__file__).resolve().parent
CSV_BIG = HERE / "coord_Big_raw.csv"
CSV_SMALL = HERE / "coord_Small_raw.csv"
OUT = HERE / "传感器坐标图.md"

X_SCALE = 1.10       # 每个字符列代表的 X 单位数
X_SCALE_OVERLAY = 0.70   # 叠加图：两板共用原点，需更细的列分辨率才不会挤在一起
Y_SCALE = 2.20       # 单板图：每个字符行代表的 Y 单位数
Y_SCALE_OVERLAY = 1.00   # 叠加图更精细，否则不同板的近邻 Y 会被并到同一行
LABEL_W = 2
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else "n/a"


def render_ascii(points, y_scale=Y_SCALE, x_scale=X_SCALE):
    """points: [(label, x, y)]；返回 (文本, 窗口, 被挪位的标签数)。

    字符列/行分别按 X/Y 独立缩放，是"位置示意"，不是等比例。
    """
    xs = [p[1] for p in points]
    ys = [p[2] for p in points]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    cols = int(round((x1 - x0) / x_scale)) + LABEL_W + 2
    rows = int(round((y1 - y0) / y_scale)) + 1

    grid = [[" "] * cols for _ in range(rows)]
    ylab = [""] * rows
    warn, shifted = [], 0

    col_of = lambda x: int(round((x - x0) / x_scale))
    row_of = lambda y: int(round((y1 - y) / y_scale))     # Y 向上：y 大 → 行号小

    # Y 刻度只标「该行真实存在的点」的 Y 值；同值去重，不同值用 / 并列
    for label, x, y in points:
        r = max(0, min(rows - 1, row_of(y)))
        text = f"{y:.2f}"
        if not ylab[r]:
            ylab[r] = text
        elif text not in ylab[r].split("/"):
            ylab[r] = f"{ylab[r]}/{text}"

    # 放标签：先右移、再左移找不冲突的位置，保证不丢字
    for label, x, y in sorted(points, key=lambda p: (row_of(p[2]), p[1])):
        r = max(0, min(rows - 1, row_of(y)))
        c = max(0, min(cols - LABEL_W, col_of(x)))
        txt = label[:LABEL_W]
        placed = None
        for cc in list(range(c, cols - len(txt) + 1)) + list(range(c - 1, -1, -1)):
            if all(grid[r][cc + k] == " " for k in range(len(txt))):
                placed = cc
                break
        if placed is None:
            warn.append(label)
            continue
        if placed != c:
            shifted += 1
        for k, ch in enumerate(txt):
            grid[r][placed + k] = ch

    tick = [" "] * cols
    t = int(-(-x0 // 5)) * 5          # 从 >= x0 的第一个 5 的倍数开始（含 0）
    while t <= x1:
        c = col_of(t)
        s = f"{t:.0f}"
        if c >= 0 and c + len(s) <= cols and all(tick[c + k] == " "
                                                 for k in range(len(s))):
            for k, ch in enumerate(s):
                tick[c + k] = ch
        t += 5
    tick_s = "".join(tick).rstrip()

    lines = ["      X→  " + tick_s,
             "            " + "─" * (len(tick_s) + 1)]
    for r in range(rows):
        body = "".join(grid[r]).rstrip()
        lines.append(f"{ylab[r] or ' ' * 8} │{body}")
    if warn:
        lines.append(f"      ! 无法放置的标签: {', '.join(warn)}")
    return "\n".join(lines), (x0, x1, y0, y1), shifted


def main() -> int:
    # 一律使用「左下角 = (0, 0)」的原点化坐标（12 点板与 32 点板同一规则）
    big = SC.BIG_32_COORDS_REL
    small = SC.SMALL_12_COORDS_REL

    big_pts = [(str(ch), x, y) for ch, x, y in big]
    small_pts = [(str(ch), x, y) for ch, x, y in small]
    both_pts = big_pts + [(LETTERS[ch - 1], x, y) for ch, x, y in small]

    ascii_big, win_big, shift_big = render_ascii(big_pts)
    ascii_small, win_small, shift_small = render_ascii(small_pts)
    ascii_both, win_both, shift_both = render_ascii(
        both_pts, y_scale=Y_SCALE_OVERLAY, x_scale=X_SCALE_OVERLAY)

    md = []
    A = md.append
    A("# 触觉传感器坐标图（Big 32 点 / Small 12 点）")
    A("")
    A(f"生成时间：{datetime.now():%Y-%m-%d %H:%M}　|　"
      "坐标方向：**Y 轴向上**　|　**每块板左下角 = (0, 0)**")
    A("")
    A("| 板 | 点数 | 平移量 (x_min, y_min) | 原点化后尺寸 宽 × 高 | 原始数据 SHA-256（前 16 位） |")
    A("|---|---:|---|---|---|")
    A(f"| Big 32 点 | {SC.BIG_32_CHANNEL_COUNT} | "
      f"({SC.BIG_32_ORIGIN[0]}, {SC.BIG_32_ORIGIN[1]}) | "
      f"{SC.BIG_32_SIZE[0]:.4f} × {SC.BIG_32_SIZE[1]:.4f} | `{sha16(CSV_BIG)}` |")
    A(f"| Small 12 点 | {SC.SMALL_12_CHANNEL_COUNT} | "
      f"({SC.SMALL_12_ORIGIN[0]}, {SC.SMALL_12_ORIGIN[1]}) | "
      f"{SC.SMALL_12_SIZE[0]:.4f} × {SC.SMALL_12_SIZE[1]:.4f} | `{sha16(CSV_SMALL)}` |")
    A("")
    A("**本页所有坐标都是「左下角 = (0, 0)」的平移结果**："
      "平移量 = 该板自己的 (x_min, y_min)，**只平移、不缩放、不旋转、不镜像**。"
      "12 点板与 32 点板用的是同一套规则，所以两板对齐到同一原点后可以直接比尺寸和节距。")
    A("")
    A("原始绝对坐标（与 CSV 逐字一致）仍完整保留在常量模块的 "
      "`*_COORDS` / `*_XY` 里，随时可以取回。")
    A("")
    A("---")
    A("")
    A("## 一、图形版")
    A("")
    A("> 三个面板都是**等比例**（1 单位 X = 1 单位 Y），形状未被拉伸；"
      "生成时逐面板校验 `ratio = 1.0000`。")
    A("")
    A("### 1.1 总览")
    A("")
    A("![总览](coord_plot_all.png)")
    A("")
    A("### 1.2 Big 32 点板")
    A("")
    A("![Big 32点](coord_plot_big32.png)")
    A("")
    A("### 1.3 Small 12 点板")
    A("")
    A("![Small 12点](coord_plot_small12.png)")
    A("")
    A("---")
    A("")
    A("## 二、纯文本坐标图（不依赖图片）")
    A("")
    A("字符列按比例对应 X、字符行按比例对应 Y（Y 轴向上），**原点在左下角**。"
      "**数字 = Big 板通道号，字母 = Small 板通道号**（A=1 … L=12）。")
    A("左侧刻度只标「该行真实存在的点」的 Y 值，空行不带刻度。")
    A("")
    A("> 文字版只保证「列↔X、行↔Y 各自的比例关系」，两个方向是独立缩放的，"
      "所以它是**位置示意**，不是等比例图；等比例请看上面的 PNG。")
    A("")

    A("### 2.1 Big 32 点板")
    A("")
    A("```text")
    A(ascii_big)
    A("```")
    A("")
    A(f"坐标范围：X {win_big[0]:.2f} ~ {win_big[1]:.2f}　Y {win_big[2]:.2f} ~ {win_big[3]:.2f}"
      "（原点化）")
    A("")

    A("### 2.2 Small 12 点板")
    A("")
    A("```text")
    A(ascii_small)
    A("```")
    A("")
    A(f"坐标范围：X {win_small[0]:.2f} ~ {win_small[1]:.2f}　"
      f"Y {win_small[2]:.2f} ~ {win_small[3]:.2f}（原点化）")
    A("")

    A("### 2.3 两块板叠加（各自左下角对齐到 (0, 0)）")
    A("")
    A("```text")
    A(ascii_both)
    A("```")
    A("")
    A(f"坐标范围：X {win_both[0]:.2f} ~ {win_both[1]:.2f}　"
      f"Y {win_both[2]:.2f} ~ {win_both[3]:.2f}（原点化）")
    A("")
    if shift_both:
        A(f"> ⚠️ 文字版里有 {shift_both} 个标签因为与另一块板的点落在同一字符格而被右移，"
          "位置有约 ±1 字符的偏差；精确位置请看 PNG 的 (c) 面板。")
        A("")
    A("> 读法提醒：两板共用原点后，Small 的 11 号 (1.058, 0.0004) 与 Big 的 17 号 (0, 0) "
      "只差约 1 个单位，文字版里会紧挨着显示（`17K` = Big 的 17 + Small 的 K，"
      "`18 L` = Big 的 18 + Small 的 L）。字母是 Small、数字是 Big，位置本身没有挪动。")
    A("")
    A("两板共用同一个原点，所以可以直接比较：**Big 宽 42.46、Small 宽 11.36**，"
      "高度接近（27.59 / 29.94）。")
    A("")
    A("---")
    A("")

    # ---------------------------------------------------------------- 表格
    A("## 三、逐行坐标表（左下角 = (0, 0)）")
    A("")
    A("行按 Y 升序（第 1 行在最下面，与图中 Y 轴向上一致）。"
      "通道号按 X 从左到右。X 从 0 起算。")
    A("")

    for title, rows, xy in (("3.1 Big 32 点板", SC.BIG_32_ROWS_REL, SC.BIG_32_XY_REL),
                            ("3.2 Small 12 点板", SC.SMALL_12_ROWS_REL, SC.SMALL_12_XY_REL)):
        A(f"### {title}")
        A("")
        A("| 行 | Y | 点数 | 通道号（左 → 右） | 逐个 X | 列间距 |")
        A("|---:|---:|---:|---|---|---|")
        for k, (y, chans) in enumerate(rows, 1):
            xr = [xy[c][0] for c in chans]
            gaps = " / ".join(f"{xr[j + 1] - xr[j]:.2f}" for j in range(len(xr) - 1)) or "—"
            A(f"| {k} | {y:.4f} | {len(chans)} | `{' '.join(str(c) for c in chans)}` | "
              f"{' '.join(f'{v:.2f}' for v in xr)} | {gaps} |")
        A("")

    A("---")
    A("")

    # ---------------------------------------------------------------- 分析
    A("## 四、结构分析")
    A("")
    A("### 4.1 Big 32 点板 = 24 点主阵列 + 7 点副行 + 1 个独立点")
    A("")
    A(f"- **主阵列 6 列 × 4 行 = 24 点**：通道 "
      f"`{', '.join(str(c) for c in SC.BIG_32_MAIN_CHANNELS)}`。")
    A(f"  X 轴 {len(SC.BIG_32_X_AXIS)} 个取值里有 6 个属主阵列，列距 ≈ 8.5；"
      "Y 为 "
      + " / ".join(f"{y:.4f}" for y, _ in SC.BIG_32_MAIN_ROWS)
      + "，行距 ≈ 4.5 → 单元格约 **8.5 × 4.5**。")
    side_y = next(y for y, chs in SC.BIG_32_ROWS_REL if len(chs) == 7)
    A(f"- **副行 7 点**：通道 `{', '.join(str(c) for c in SC.BIG_32_SIDE_ROW)}`，"
      f"Y = {side_y:.4f}，列距 ≈ 5.8，与主阵列不是同一套栅格。")
    sx, sy = SC.BIG_32_XY_REL[SC.BIG_32_STANDALONE]
    A(f"- **独立点**：通道 {SC.BIG_32_STANDALONE} 在 ({sx:.4f}, {sy:.4f})，"
      "两套栅格都对不上。")
    A("")
    A("### 4.2 Small 12 点板 = 两块不同节距的子阵列")
    A("")
    A(f"- **上排 3 列 × 2 行 = 6 点**：通道 "
      f"`{', '.join(str(c) for c in SC.SMALL_12_TOP_CHANNELS)}`，列距 ≈ 5.67。")
    A(f"- **下排 2 列 × 3 行 = 6 点**：通道 "
      f"`{', '.join(str(c) for c in SC.SMALL_12_BOTTOM_CHANNELS)}`，列距 ≈ 9.24。")
    A("")
    A("> 原始数据里通道 11 的 Y = 71.1163、通道 12 的 Y = 71.1159，相差 0.0004；"
      "原点化后分别是 0.0004 和 0.0000。两者视为同一行，"
      "表中该行 Y 取平均 0.0002（`SMALL_12_ROWS_REL` 的定义如此）。")
    A("")
    A("### 4.3 两板关系（原点化后可直接比较）")
    A("")
    A("| 项 | Big 32 点 | Small 12 点 |")
    A("|---|---|---|")
    A(f"| 平移量 (x_min, y_min) | ({SC.BIG_32_ORIGIN[0]}, {SC.BIG_32_ORIGIN[1]}) | "
      f"({SC.SMALL_12_ORIGIN[0]}, {SC.SMALL_12_ORIGIN[1]}) |")
    A(f"| 尺寸 宽 × 高 | {SC.BIG_32_SIZE[0]:.4f} × {SC.BIG_32_SIZE[1]:.4f} | "
      f"{SC.SMALL_12_SIZE[0]:.4f} × {SC.SMALL_12_SIZE[1]:.4f} |")
    A(f"| X 取值个数 | {len(SC.BIG_32_X_AXIS)} | {len(SC.SMALL_12_X_AXIS)} |")
    A(f"| Y 取值个数（行数） | {len(SC.BIG_32_Y_AXIS)} | {len(SC.SMALL_12_Y_AXIS)} |")
    A("| 主节距 | 列 ≈8.5 / 行 ≈4.5（主阵列）<br>副行 列 ≈5.8 | 上排 列 ≈5.67<br>下排 列 ≈9.24 |")
    A("")
    A("两板共用同一个原点（各自左下角），所以可以直接看：**Big 明显更宽"
      f"（{SC.BIG_32_SIZE[0]:.1f} vs {SC.SMALL_12_SIZE[0]:.1f}）**，高度接近"
      f"（{SC.BIG_32_SIZE[1]:.1f} vs {SC.SMALL_12_SIZE[1]:.1f}）。")
    A("")
    A("原始绝对坐标下两板的 X 区间是**不重叠**的"
      f"（`BIG_AND_SMALL_X_OVERLAP = {SC.BIG_AND_SMALL_X_OVERLAP}`），"
      "Small 整体在 Big 左侧约 10 个单位 —— 这一点在原点化后不再体现，"
      "如需查看请用 `--raw` 出图。")
    A("")
    A("---")
    A("")

    # ---------------------------------------------------------------- 常量模块
    A("## 五、常量模块 `sensor_coords.py`")
    A("")
    A("坐标已写成 Python 常量，上位机可直接 import，不需要再解析 CSV：")
    A("")
    A("```python")
    A("from sensor_coords import (")
    A("    # 原始绝对坐标（与 CSV 逐字一致）")
    A("    BIG_32_COORDS, SMALL_12_COORDS,        # ((通道号, X, Y), ...) 通道号 1..N")
    A("    BIG_32_XY, SMALL_12_XY,                # {通道号: (X, Y)}")
    A("    BIG_32_BOUNDS, SMALL_12_BOUNDS,        # (x_min, x_max, y_min, y_max)")
    A("    # 左下角 = (0, 0) 的原点化坐标")
    A("    BIG_32_COORDS_REL, SMALL_12_COORDS_REL,")
    A("    BIG_32_XY_REL, SMALL_12_XY_REL,")
    A("    BIG_32_ORIGIN, SMALL_12_ORIGIN,        # 被减掉的平移量")
    A("    BIG_32_SIZE, SMALL_12_SIZE,            # 宽 × 高")
    A("    BIG_32_BOUNDS_REL, SMALL_12_BOUNDS_REL,  # (0, 0, 宽, 高)")
    A("    # 栅格与结构")
    A("    BIG_32_X_AXIS, BIG_32_Y_AXIS, BIG_32_ROWS, BIG_32_ROWS_REL,")
    A("    BIG_32_MAIN_CHANNELS, BIG_32_SIDE_ROW, BIG_32_STANDALONE,")
    A("    SMALL_12_TOP_CHANNELS, SMALL_12_BOTTOM_CHANNELS,")
    A("    # 工具")
    A("    xy_for, xy_rel_for, coords_for, coords_rel_for,")
    A("    origin_for, size_for, bounds_for, bounds_rel_for, normalized_xy,")
    A(")")
    A("")
    A("xy_for(17, 32)       # -> (127.531, 55.6552)   原始绝对坐标")
    A("xy_rel_for(17, 32)   # -> (0.0, 0.0)           Big 板左下角就是它")
    A("xy_rel_for(7, 32)    # -> (38.7583, 22.4717)   副行最右（原点化）")
    A("normalized_xy(32)    # -> {通道号: (u, v)}，u = X/宽, v = Y/高")
    A("```")
    A("")
    A("| 常量 | 含义 |")
    A("|---|---|")
    A("| `BIG_32_COORDS` / `SMALL_12_COORDS` | **原始绝对坐标**，逐字来自 CSV |")
    A("| `BIG_32_COORDS_REL` / `SMALL_12_COORDS_REL` | **左下角 = (0, 0)** 的坐标 |")
    A("| `*_ORIGIN` | 该板被减掉的平移量 `(x_min, y_min)` |")
    A("| `*_SIZE` / `*_BOUNDS_REL` | 原点化后的宽高与包围盒 `(0, 0, 宽, 高)` |")
    A("| `*_XY` / `*_XY_REL` / `COORDS*_BY_CHANNEL_COUNT` | 按通道号 / 按通道数索引 |")
    A("| `*_BOUNDS` / `*_X_AXIS` / `*_Y_AXIS` | 原始包围盒与栅格轴 |")
    A("| `*_ROWS` / `*_ROWS_REL` | 逐行分组 `(Y, (通道号...))`，行内按 X 左→右 |")
    A("| `BIG_32_MAIN_CHANNELS` / `BIG_32_SIDE_ROW` / `BIG_32_STANDALONE` | Big 板三段结构 |")
    A("| `SMALL_12_TOP_CHANNELS` / `SMALL_12_BOTTOM_CHANNELS` | Small 板两块子阵列 |")
    A("")
    A("除原始坐标外，其余常量全部**由原始表推导**（包括平移后的相对坐标），"
      "改原始表即自动同步，不会出现数据与派生值不一致。")
    A("")
    A("---")
    A("")

    A("## 六、待确认项")
    A("")
    A("1. **Y 轴方向**：本图按「Y 轴向上」绘制。若来源是图像/屏幕坐标（Y 向下），"
      "跑 `python plot_coords.py --flip` 即可上下镜像；"
      "上位机可用 `normalized_xy(32, y_up=False)` 直接拿到屏幕坐标。")
    A("2. **`sensor_Number` 的口径**：是 MCU 原始通道 `ch01–ch32`，"
      "还是网页显示位置 `CH01–CH32`？"
      "后者需套 `嵌入式代码/Applications/Tactile500/docs/BOARD_VARIANTS_AND_CHANNEL_MAP.md` "
      "里的短线换序表 `SHORT_POSITION_TO_CHANNEL`。")
    A("")
    A("## 七、重新生成")
    A("")
    A("```powershell")
    A("python make_sensor_coords.py            # CSV  ->  sensor_coords.py（常量）")
    A("python plot_coords.py                   # 常量 ->  PNG（左下角 = (0,0)）")
    A("python plot_coords.py --raw             # 常量 ->  PNG（原始绝对坐标）")
    A("python plot_coords.py --flip            # 常量 ->  PNG（Y 轴向下）")
    A("python plot_coords.py --verify-csv      # 校验常量与 CSV 逐字一致")
    A("python make_coord_md.py                 # 常量 ->  本 Markdown")
    A("python sensor_coords.py                 # 常量模块自检")
    A("```")
    A("")
    A("`plot_coords.py` 会逐面板校验等比例（`ratio` 必须为 `1.0000`）"
      "以及说明框覆盖的数据点数（必须为 `0`）。")
    A("")

    OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"已写出 {OUT.name}（{len('\n'.join(md))} 字符）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
