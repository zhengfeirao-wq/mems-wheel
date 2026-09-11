# -*- coding: utf-8 -*-
"""触觉传感器坐标常量表（Big 32 点板 / Small 12 点板）。

本文件由 ``make_sensor_coords.py`` 生成，请勿手工改数据；要改就改原始 CSV 后重跑。

原始数据：
    coord_Big_raw.csv    sha256 71dec34cf0a3b85e
    coord_Small_raw.csv  sha256 8bac68b0fdcc92e6
生成时间：2026-09-11 21:24

坐标约定：
    * 数值与原始 CSV **逐字一致**，未做任何平移 / 缩放 / 旋转 / 翻转。
    * 每项为 ``(通道号, X_coord, Y_coord)``，按通道号升序。
    * 绘制时一般按 **Y 轴向上**（Y 大的在上）；若来源是屏幕坐标需要上下镜像，
      由使用方自行处理，本模块不替调用者决定方向。

两套坐标（12 点板与 32 点板规则完全相同）：
    * ``*_COORDS`` / ``*_XY`` —— **原始绝对坐标**，与 CSV 一致。
    * ``*_COORDS_REL`` / ``*_XY_REL`` —— **把该板自己的左下角平移到 (0, 0)**
      之后的坐标；平移量 = 该板 (x_min, y_min)，只平移不缩放。
      所以恒有 ``min(X) == 0``、``min(Y) == 0``，且所有坐标非负。
      各板平移量不同（Big 为 (127.531, 55.6552)，Small 为 (105.8507, 71.1159)），
      因此两板对齐到同一原点后可以直接比较尺寸与节距。

用法::

    from sensor_coords import coords_for, xy_for, coords_rel_for, xy_rel_for

    xy_for(17, 32)         # -> (127.531, 55.6552)   原始绝对坐标
    xy_rel_for(17, 32)     # -> (0.0, 0.0)           Big 板左下角就是它
    xy_rel_for(7, 32)      # -> (38.7583, 22.4717)   副行最右（原点化）
    coords_rel_for(12)     # -> Small 板原点化整张表
    BIG_32_SIZE            # -> (42.4614, 27.5869)   宽 × 高
    normalized_xy(32)      # -> {通道号: (u, v)}，u=X/宽, v=Y/高
"""

from __future__ import annotations

# ===========================================================================
# 一、原始坐标常量（逐字来自 CSV）
# ===========================================================================

# Big 32 点板：每项 (通道号, X, Y)，按通道号升序
BIG_32_COORDS: tuple[tuple[int, float, float], ...] = (
    (1, 127.531, 69.296),
    (2, 136.042, 69.296),
    (3, 144.1886, 69.296),
    (4, 153.1277, 69.296),
    (5, 161.567, 69.296),
    (6, 169.9924, 69.296),
    (7, 166.2893, 78.1269),
    (8, 160.3704, 78.1269),
    (9, 154.439, 78.1269),
    (10, 148.9074, 78.1269),
    (11, 143.1525, 78.1269),
    (12, 137.1624, 78.1269),
    (13, 131.48, 78.1269),
    (14, 127.531, 64.6302),
    (15, 136.042, 64.6302),
    (16, 148.9775, 83.2421),
    (17, 127.531, 55.6552),
    (18, 136.042, 55.6552),
    (19, 144.1886, 55.6552),
    (20, 153.1277, 55.6552),
    (21, 161.567, 55.6552),
    (22, 169.9924, 55.6552),
    (23, 169.9924, 64.6302),
    (24, 161.567, 64.6302),
    (25, 153.1277, 64.6302),
    (26, 144.1886, 64.6302),
    (27, 169.9924, 60.1797),
    (28, 161.567, 60.1797),
    (29, 153.1277, 60.1797),
    (30, 144.1886, 60.1797),
    (31, 136.042, 60.1797),
    (32, 127.531, 60.1797),
)

# Small 12 点板：每项 (通道号, X, Y)，按通道号升序
SMALL_12_COORDS: tuple[tuple[int, float, float], ...] = (
    (1, 105.8507, 101.0546),
    (2, 111.5158, 101.0546),
    (3, 117.2057, 101.0546),
    (4, 105.8507, 95.1531),
    (5, 111.5158, 95.1531),
    (6, 117.2057, 95.1531),
    (7, 106.9069, 83.8797),
    (8, 116.1473, 83.8797),
    (9, 106.9069, 77.4569),
    (10, 116.1473, 77.4569),
    (11, 106.9088, 71.1163),
    (12, 116.1473, 71.1159),
)

# ===========================================================================
# 二、派生常量（全部由上面的原始表算出，改原始表即自动同步）
# ===========================================================================

BIG_32_CHANNEL_COUNT: int = len(BIG_32_COORDS)
SMALL_12_CHANNEL_COUNT: int = len(SMALL_12_COORDS)

# 通道号 -> (X, Y)
BIG_32_XY: dict[int, tuple[float, float]] = {ch: (x, y) for ch, x, y in BIG_32_COORDS}
SMALL_12_XY: dict[int, tuple[float, float]] = {ch: (x, y) for ch, x, y in SMALL_12_COORDS}

# 按"通道数"索引（对应固件的 12 / 32 点板型）
COORDS_BY_CHANNEL_COUNT: dict[int, tuple[tuple[int, float, float], ...]] = {
    BIG_32_CHANNEL_COUNT: BIG_32_COORDS,
    SMALL_12_CHANNEL_COUNT: SMALL_12_COORDS,
}
XY_BY_CHANNEL_COUNT: dict[int, dict[int, tuple[float, float]]] = {
    BIG_32_CHANNEL_COUNT: BIG_32_XY,
    SMALL_12_CHANNEL_COUNT: SMALL_12_XY,
}

# 包围盒 (x_min, x_max, y_min, y_max)
BIG_32_BOUNDS: tuple[float, float, float, float] = (
    min(x for _, x, _ in BIG_32_COORDS), max(x for _, x, _ in BIG_32_COORDS),
    min(y for _, _, y in BIG_32_COORDS), max(y for _, _, y in BIG_32_COORDS),
)
SMALL_12_BOUNDS: tuple[float, float, float, float] = (
    min(x for _, x, _ in SMALL_12_COORDS), max(x for _, x, _ in SMALL_12_COORDS),
    min(y for _, _, y in SMALL_12_COORDS), max(y for _, _, y in SMALL_12_COORDS),
)

# 唯一 X / Y（升序）——就是两块板的栅格轴
BIG_32_X_AXIS: tuple[float, ...] = tuple(sorted({x for _, x, _ in BIG_32_COORDS}))
BIG_32_Y_AXIS: tuple[float, ...] = tuple(sorted({y for _, _, y in BIG_32_COORDS}))
SMALL_12_X_AXIS: tuple[float, ...] = tuple(sorted({x for _, x, _ in SMALL_12_COORDS}))
SMALL_12_Y_AXIS: tuple[float, ...] = tuple(sorted({y for _, _, y in SMALL_12_COORDS}))


def group_rows(coords, tol: float = 0.35):
    """把 Y 相差 <= tol 的通道归为一行，返回 ((Y, (通道号...)), ...)，Y 升序。

    同一行内通道号按 X 从左到右排列。Y 取该行所有点的平均值
    （正常栅格上各点 Y 完全相同；Small 板 11/12 两点相差 0.0004，
    平均后为 71.1161，仅作代表值）。
    """
    items = sorted(coords, key=lambda c: c[2])
    rows, cur = [], [items[0]]
    for it in items[1:]:
        if abs(it[2] - cur[-1][2]) <= tol:
            cur.append(it)
        else:
            rows.append(cur)
            cur = [it]
    rows.append(cur)
    return tuple(
        (round(sum(c[2] for c in r) / len(r), 4),
         tuple(c[0] for c in sorted(r, key=lambda c: c[1])))
        for r in rows
    )


# 逐行分组：每项 = (Y, (通道号...))，通道号按 X 从左到右
BIG_32_ROWS = group_rows(BIG_32_COORDS)
SMALL_12_ROWS = group_rows(SMALL_12_COORDS)

# ------- Big 板结构：24 点主阵列（6 列 × 4 行）+ 7 点副行 + 1 个独立点 -------
BIG_32_MAIN_ROWS: tuple[tuple[float, tuple[int, ...]], ...] = tuple(
    r for r in BIG_32_ROWS if len(r[1]) == 6 and r[0] < 70.0
)
BIG_32_MAIN_CHANNELS: tuple[int, ...] = tuple(
    sorted(ch for _, chs in BIG_32_MAIN_ROWS for ch in chs)
)
BIG_32_MAIN_COLUMNS: int = len(BIG_32_X_AXIS) - 7   # 主阵列 6 列（另 7 个 X 属副行体系）
BIG_32_SIDE_ROW: tuple[int, ...] = tuple(
    sorted(next(chs for _, chs in BIG_32_ROWS if len(chs) == 7))
)
BIG_32_STANDALONE: int = next(chs[0] for _, chs in BIG_32_ROWS if len(chs) == 1)

# ------- Small 板结构：3 列 × 2 行（1-6）+ 2 列 × 3 行（7-12）-------
# 按 Y 轴向上看：通道 1-6 在上方，7-12 在下方
SMALL_12_TOP_CHANNELS: tuple[int, ...] = tuple(
    sorted(ch for _, chs in SMALL_12_ROWS if len(chs) == 3 for ch in chs)
)
SMALL_12_BOTTOM_CHANNELS: tuple[int, ...] = tuple(
    sorted(ch for _, chs in SMALL_12_ROWS if len(chs) == 2 for ch in chs)
)

# 两板 X 区间互不重叠（Small 在左，Big 在右）
BIG_AND_SMALL_X_OVERLAP: bool = not (
    BIG_32_BOUNDS[1] < SMALL_12_BOUNDS[0] or SMALL_12_BOUNDS[1] < BIG_32_BOUNDS[0]
)

# ===========================================================================
# 三、原点平移：把每块板自己的左下角移到 (0, 0)
# ===========================================================================
# 只做平移，不缩放、不旋转、不镜像；12 点板与 32 点板用同一套规则。
# 平移量 = 该板自己的 (x_min, y_min)，所以平移后必然满足 min(X)=0 且 min(Y)=0。

BIG_32_ORIGIN: tuple[float, float] = (
    min(x for _, x, _ in BIG_32_COORDS), min(y for _, _, y in BIG_32_COORDS))
SMALL_12_ORIGIN: tuple[float, float] = (
    min(x for _, x, _ in SMALL_12_COORDS), min(y for _, _, y in SMALL_12_COORDS))

# 左下角 = (0, 0) 的坐标表：每项 (通道号, X, Y)
BIG_32_COORDS_REL: tuple[tuple[int, float, float], ...] = tuple(
    (ch, round(x - BIG_32_ORIGIN[0], 4), round(y - BIG_32_ORIGIN[1], 4))
    for ch, x, y in BIG_32_COORDS)
SMALL_12_COORDS_REL: tuple[tuple[int, float, float], ...] = tuple(
    (ch, round(x - SMALL_12_ORIGIN[0], 4), round(y - SMALL_12_ORIGIN[1], 4))
    for ch, x, y in SMALL_12_COORDS)

BIG_32_XY_REL: dict[int, tuple[float, float]] = {
    ch: (x, y) for ch, x, y in BIG_32_COORDS_REL}
SMALL_12_XY_REL: dict[int, tuple[float, float]] = {
    ch: (x, y) for ch, x, y in SMALL_12_COORDS_REL}

COORDS_REL_BY_CHANNEL_COUNT: dict[int, tuple[tuple[int, float, float], ...]] = {
    BIG_32_CHANNEL_COUNT: BIG_32_COORDS_REL,
    SMALL_12_CHANNEL_COUNT: SMALL_12_COORDS_REL,
}
XY_REL_BY_CHANNEL_COUNT: dict[int, dict[int, tuple[float, float]]] = {
    BIG_32_CHANNEL_COUNT: BIG_32_XY_REL,
    SMALL_12_CHANNEL_COUNT: SMALL_12_XY_REL,
}

# 原点化后的包围盒永远从 (0, 0) 开始：(0, 0, 宽, 高)
BIG_32_BOUNDS_REL: tuple[float, float, float, float] = (
    0.0, max(x for _, x, _ in BIG_32_COORDS_REL),
    0.0, max(y for _, _, y in BIG_32_COORDS_REL))
SMALL_12_BOUNDS_REL: tuple[float, float, float, float] = (
    0.0, max(x for _, x, _ in SMALL_12_COORDS_REL),
    0.0, max(y for _, _, y in SMALL_12_COORDS_REL))

# 板子尺寸（原点化包围盒的宽 × 高）
BIG_32_SIZE: tuple[float, float] = (BIG_32_BOUNDS_REL[1], BIG_32_BOUNDS_REL[3])
SMALL_12_SIZE: tuple[float, float] = (SMALL_12_BOUNDS_REL[1], SMALL_12_BOUNDS_REL[3])

# 左上角坐标（原点在左下角、Y 轴向上，所以左上角恒为 (0, 高)）
BIG_32_TOP_LEFT: tuple[float, float] = (0.0, BIG_32_SIZE[1])
SMALL_12_TOP_LEFT: tuple[float, float] = (0.0, SMALL_12_SIZE[1])

# 行分组也给出原点化版本：((Y_rel, (通道号...)), ...)
BIG_32_ROWS_REL = group_rows(BIG_32_COORDS_REL)
SMALL_12_ROWS_REL = group_rows(SMALL_12_COORDS_REL)


# ===========================================================================
# 四、小工具
# ===========================================================================


def coords_for(channel_count: int) -> tuple[tuple[int, float, float], ...]:
    """按通道数取整张表（12 或 32）——原始绝对坐标。"""
    try:
        return COORDS_BY_CHANNEL_COUNT[channel_count]
    except KeyError:
        raise ValueError(f"没有 {channel_count} 点板的坐标表") from None


def xy_for(channel: int, channel_count: int = BIG_32_CHANNEL_COUNT):
    """按通道号取 (X, Y) 原始绝对坐标；通道号从 1 开始。"""
    return XY_BY_CHANNEL_COUNT[channel_count][channel]


def bounds_for(channel_count: int = BIG_32_CHANNEL_COUNT):
    """取原始包围盒 (x_min, x_max, y_min, y_max)。"""
    return BIG_32_BOUNDS if channel_count == BIG_32_CHANNEL_COUNT else SMALL_12_BOUNDS


def coords_rel_for(channel_count: int = BIG_32_CHANNEL_COUNT):
    """按通道数取「左下角 = (0, 0)」的坐标表。"""
    try:
        return COORDS_REL_BY_CHANNEL_COUNT[channel_count]
    except KeyError:
        raise ValueError(f"没有 {channel_count} 点板的坐标表") from None


def xy_rel_for(channel: int, channel_count: int = BIG_32_CHANNEL_COUNT):
    """按通道号取「左下角 = (0, 0)」的 (X, Y)。"""
    return XY_REL_BY_CHANNEL_COUNT[channel_count][channel]


def origin_for(channel_count: int = BIG_32_CHANNEL_COUNT):
    """取该板被减掉的平移量：(x_min, y_min)。"""
    return BIG_32_ORIGIN if channel_count == BIG_32_CHANNEL_COUNT else SMALL_12_ORIGIN


def bounds_rel_for(channel_count: int = BIG_32_CHANNEL_COUNT):
    """取原点化包围盒 (0, 0, 宽, 高)。"""
    return (BIG_32_BOUNDS_REL if channel_count == BIG_32_CHANNEL_COUNT
            else SMALL_12_BOUNDS_REL)


def size_for(channel_count: int = BIG_32_CHANNEL_COUNT):
    """取板子尺寸 (宽, 高)，即原点化包围盒的宽高。"""
    return BIG_32_SIZE if channel_count == BIG_32_CHANNEL_COUNT else SMALL_12_SIZE


def normalized_xy(channel_count: int = BIG_32_CHANNEL_COUNT, *, y_up: bool = True):
    """归一化到 0..1，方便上位机按控件尺寸缩放。

    基于原点化坐标，所以直接是「相对左下角」的比例：
      u = X / 宽，v = Y / 高。
    y_up=True  : V=0 在下、V=1 在上（数学坐标）
    y_up=False : V=0 在上、V=1 在下（屏幕坐标，直接乘以控件高度即可）
    """
    w, h = size_for(channel_count)
    w = w or 1.0
    h = h or 1.0
    out = {}
    for ch, x, y in coords_rel_for(channel_count):
        v = y / h
        out[ch] = (x / w, v if y_up else 1.0 - v)
    return out


# ===========================================================================
# 五、自检
# ===========================================================================

if __name__ == "__main__":
    for name, coords, bounds, rows in (
        ("Big 32", BIG_32_COORDS, BIG_32_BOUNDS, BIG_32_ROWS),
        ("Small 12", SMALL_12_COORDS, SMALL_12_BOUNDS, SMALL_12_ROWS),
    ):
        chans = [c[0] for c in coords]
        assert chans == list(range(1, len(coords) + 1)), f"{name} 通道号必须 1..N 连续"
        assert all(len(set(c)) == 3 for c in coords), f"{name} 坐标项格式错误"
        print(f"[OK] {name}: {len(coords)} 点  X {bounds[0]:.2f}~{bounds[1]:.2f}  "
              f"Y {bounds[2]:.2f}~{bounds[3]:.2f}")
        for y, chs in rows:
            print(f"       Y={y:8.4f}  {list(chs)}")
    print(f"[OK] Big 主阵列通道 {list(BIG_32_MAIN_CHANNELS)}")
    print(f"[OK] Big 副行通道   {list(BIG_32_SIDE_ROW)}")
    print(f"[OK] Big 独立点     {BIG_32_STANDALONE}")
    print(f"[OK] Small 上排     {list(SMALL_12_TOP_CHANNELS)}")
    print(f"[OK] Small 下排     {list(SMALL_12_BOTTOM_CHANNELS)}")
    print(f"[OK] 两板 X 重叠？  {BIG_AND_SMALL_X_OVERLAP}")

    # 原点平移校验：左下角必须正好是 (0, 0)
    for name, rel, size in (("Big 32", BIG_32_COORDS_REL, BIG_32_SIZE),
                            ("Small 12", SMALL_12_COORDS_REL, SMALL_12_SIZE)):
        mnx = min(x for _, x, _ in rel)
        mny = min(y for _, _, y in rel)
        assert mnx == 0.0 and mny == 0.0, f"{name} 左下角不是 (0,0)：({mnx}, {mny})"
        assert all(x >= 0.0 and y >= 0.0 for _, x, y in rel), f"{name} 出现负坐标"
        print(f"[OK] {name} 左下角=(0.0000, 0.0000)  尺寸 {size[0]:.4f} × {size[1]:.4f}"
              f"  平移量 {origin_for(len(rel))}")

    xy = normalized_xy(32)
    print(f"[OK] 归一化示例 ch1={tuple(round(v, 4) for v in xy[1])}  "
          f"ch16={tuple(round(v, 4) for v in xy[16])}")

    # 文档示例值断言：防止 docstring / README 里的例子随数据变化而失准
    assert xy_for(7, 32) == (166.2893, 78.1269), "docstring 示例 xy_for(7,32) 已过时"
    assert xy_for(17, 32) == (127.531, 55.6552), "docstring 示例 xy_for(17,32) 已过时"
    assert xy_for(1, 12) == (105.8507, 101.0546), "docstring 示例 xy_for(1,12) 已过时"
    assert xy_rel_for(17, 32) == (0.0, 0.0), "17 号应当是 Big 板的原点"
    assert xy_rel_for(23, 32) == (42.4614, 8.975), "docstring 示例 xy_rel_for(23,32) 已过时"
    print("[OK] docstring 示例值断言通过")
