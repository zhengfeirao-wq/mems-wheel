"""软件校零（tare）：把静止基线从压力值里减掉，同时完整保留原始值。

设计原则
--------
1. **不销毁原始数据**：`frame.pressure` 永远不会被修改。校零只是一个"视图"，
   任何时刻都能用 `TareFilter.raw()` 或 `offsets` 还原。
2. **可回溯**：每次校零都写进追加式 journal（JSONL），带时间戳与质量指标，
   因此可以事后统计"5 天里每次开机的零点漂移"。
3. **不骗人**：饱和/无数据/不稳定的通道会被明确标记，不会静默给一个假零点。

典型用法
--------
    from tactile500 import TactileSystem
    from tactile500.tare import tare_now, TareFilter, TareJournal

    system = TactileSystem().open()
    journal = TareJournal()

    # 采集系统启动时，夹爪张开、无接触，采 2 秒基线
    result = tare_now(system, seconds=2.0)
    journal.append(result, note="第 1 天开机")

    tared = TareFilter(result)
    item = native.get(timeout=1.0)
    shown = tared.apply_frame(item.frame)   # 0 附近
    raw = item.frame.pressure               # 原始值，一直都在

命名
----
全套统一使用 ``tare_*`` 前缀与 ``Tare*`` 类名，搜索 ``tare`` 即可找齐：

    tare_now()      采一次零点（唯一入口）
    TareResult      一次校零的完整结果
    TareFilter      把零点应用到实时帧
    TareJournal     追加式档案，用于回溯与漂移分析

单位
----
压力值是固件标定输出 × 9/80 的"固件值"，**不是 Pa 也不是 N**。
校零后是相对变化量；绝对量纲仍需实物标定。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty
from statistics import median
from typing import Iterable, Mapping, Sequence

__all__ = [
    "SATURATION",
    "SENTINEL",
    "ChannelBaseline",
    "TareResult",
    "TareFilter",
    "TareJournal",
    "tare_now",
    "measure_baseline",
    "restore",
]

#: 24 位 ADC 顶到正/负端点时，固件缩放后的值（raw = ±2^23，×9/80）。
SATURATION = 943718

#: 通道未就绪时固件发送的哨兵值（TACTILE_INVALID_PRESSURE）。
SENTINEL = -8388608

DEFAULT_JOURNAL = Path.home() / ".tactile500" / "tare" / "journal.jsonl"


@dataclass(frozen=True)
class ChannelBaseline:
    """单通道的基线统计。"""

    offset: int
    spread: int
    samples: int
    status: str  # ok | saturated | no_data | unstable

    @property
    def usable(self) -> bool:
        return self.status in ("ok", "unstable")

    def to_json(self) -> dict:
        return {"offset": self.offset, "spread": self.spread,
                "samples": self.samples, "status": self.status}

    @classmethod
    def from_json(cls, d: Mapping) -> "ChannelBaseline":
        return cls(int(d["offset"]), int(d["spread"]), int(d["samples"]), str(d["status"]))


@dataclass(frozen=True)
class TareResult:
    """一次校零的完整结果。"""

    created_ns: int
    duration_s: float
    offsets: Mapping[str, tuple[int, ...]]
    baselines: Mapping[str, tuple[ChannelBaseline, ...]]
    identities: Mapping[str, int] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @property
    def created_iso(self) -> str:
        return datetime.fromtimestamp(self.created_ns / 1e9, tz=timezone.utc).isoformat(timespec="seconds")

    def offsets_for(self, role: str) -> tuple[int, ...]:
        return tuple(self.offsets.get(role, ()))

    def statuses_for(self, role: str) -> tuple[str, ...]:
        return tuple(b.status for b in self.baselines.get(role, ()))

    def summary(self) -> str:
        parts = []
        for role, bl in self.baselines.items():
            ok = sum(1 for b in bl if b.usable)
            parts.append(f"{role} {ok}/{len(bl)}")
        return f"{self.created_iso}  {self.duration_s:.1f}s  " + "  ".join(parts)

    def to_json(self) -> dict:
        return {
            "created_ns": self.created_ns,
            "created_iso": self.created_iso,
            "duration_s": self.duration_s,
            "offsets": {r: list(v) for r, v in self.offsets.items()},
            "identities": {r: f"0x{v:02X}" for r, v in self.identities.items()},
            "baselines": {r: [b.to_json() for b in bl] for r, bl in self.baselines.items()},
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_json(cls, d: Mapping) -> "TareResult":
        return cls(
            created_ns=int(d["created_ns"]),
            duration_s=float(d.get("duration_s", 0.0)),
            offsets={r: tuple(int(x) for x in v) for r, v in (d.get("offsets") or {}).items()},
            baselines={r: tuple(ChannelBaseline.from_json(b) for b in bl)
                       for r, bl in (d.get("baselines") or {}).items()},
            identities={r: int(str(v), 16) for r, v in (d.get("identities") or {}).items()},
            warnings=tuple(d.get("warnings") or ()),
        )


def _channel_baseline(values: Sequence[int], fresh: Sequence[int], *,
                      min_samples: int, max_spread: int,
                      reject_saturated: bool) -> ChannelBaseline:
    n = len(values)
    if n < min_samples:
        return ChannelBaseline(0, 0, n, "no_data")
    if all(v == SENTINEL for v in values):
        return ChannelBaseline(0, 0, n, "no_data")

    off = int(median(values))
    if reject_saturated and abs(off) >= SATURATION - 8:
        return ChannelBaseline(0, 0, n, "saturated")

    # 稳定性用 fresh 帧评估：非 fresh 是重复值，会低估真实波动
    probe = fresh if len(fresh) >= min_samples else values
    spread = int(max(probe) - min(probe))
    ok = max(abs(min(probe)), abs(max(probe))) < SATURATION - 8
    if reject_saturated and not ok:
        return ChannelBaseline(off, spread, n, "saturated")
    if spread > max_spread:
        return ChannelBaseline(off, spread, n, "unstable")
    return ChannelBaseline(off, spread, n, "ok")


def tare_now(system, *, seconds: float = 2.0,
             roles: Sequence[str] | None = None,
             fresh_only: bool = True,
             min_samples: int = 50,
             max_spread: int = 20_000,
             reject_saturated: bool = True,
             capacity: int = 8192,
             max_frames: int = 40_000) -> TareResult:
    """采一次静止基线，得到"现在"的零点。整套功能的唯一入口。

    命名统一为 ``tare_*`` 前缀：``tare_now`` / ``TareFilter`` / ``TareJournal`` /
    ``TareResult``，搜 ``tare`` 即可找齐全部。

    调用方必须保证：**夹爪张开、无任何接触**。本函数只能通过"数值是否稳定"
    来兜底提示，无法替代这个前提。

    Args:
        system: 已 open 的 TactileSystem。
        seconds: 基线时长，建议 1~3 秒。
        roles: 只校这些角色（tactile500 角色名）；None = 全部在线板。
        fresh_only: 稳定性评估只用 fresh_mask 命中的帧（这些才是真新转换）。
        min_samples: 少于这个帧数判为 no_data。
        max_spread: 极差超过它判为 unstable。
        reject_saturated: 是否拒绝顶到满量程的通道。

    Returns:
        TareResult，可交给 TareFilter 使用，也可写进 TareJournal。
    """
    sub = system.subscribe(capacity=capacity)
    all_values: dict[str, list[list[int]]] = {}
    fresh_values: dict[str, list[list[int]]] = {}
    identities: dict[str, int] = {}
    deadline = time.monotonic() + max(0.1, seconds)
    total = 0
    try:
        while time.monotonic() < deadline and total < max_frames:
            try:
                item = sub.get(timeout=0.2)
            except Empty:
                continue
            frame = item.frame
            role = frame.role
            if roles is not None and role not in roles:
                continue
            total += 1
            identities[role] = frame.identity
            all_values.setdefault(role, []).append(list(frame.pressure))
            if frame.fresh_mask:
                fresh_values.setdefault(role, []).append(list(frame.pressure))
    finally:
        sub.close()

    warnings: list[str] = []
    if not all_values:
        warnings.append(f"{seconds:.1f} 秒内没有收到任何帧；设备是否在线？")

    offsets: dict[str, tuple[int, ...]] = {}
    baselines: dict[str, tuple[ChannelBaseline, ...]] = {}
    for role, rows in all_values.items():
        ch = len(rows[0])
        fresh_rows = fresh_values.get(role, [])
        cols = [ChannelBaseline(0, 0, 0, "no_data")] * ch
        bl = []
        for c in range(ch):
            col = [r[c] for r in rows]
            fcol = [r[c] for r in fresh_rows] if fresh_only else col
            b = _channel_baseline(col, fcol, min_samples=min_samples,
                                  max_spread=max_spread,
                                  reject_saturated=reject_saturated)
            bl.append(b)
        baselines[role] = tuple(bl)
        offsets[role] = tuple(b.offset if b.usable else 0 for b in bl)

        for c, b in enumerate(bl):
            if b.status == "saturated":
                warnings.append(f"{role} ch{c} 顶到满量程，已跳过（硬件/接线问题）")
            elif b.status == "unstable":
                warnings.append(f"{role} ch{c} 基线不稳（极差 {b.spread}），"
                                f"夹爪是否真的空载？")
            elif b.status == "no_data":
                warnings.append(f"{role} ch{c} 基线数据不足，已给 0 偏移")

    return TareResult(
        created_ns=time.time_ns(),
        duration_s=seconds,
        offsets=offsets,
        baselines=baselines,
        identities=identities,
        warnings=tuple(warnings),
    )


#: 0.4.0 使用的旧名，保留兼容；新代码请用 tare_now。
measure_baseline = tare_now


class TareFilter:
    """把 TareResult 应用到实时帧上。不修改原始数据。"""

    def __init__(self, result: TareResult, *, strict: bool = False):
        self.result = result
        self.strict = strict
        self._offsets = {r: list(v) for r, v in result.offsets.items()}

    def offsets_for(self, role: str) -> tuple[int, ...]:
        return tuple(self._offsets.get(role, ()))

    def apply(self, role: str, pressure: Sequence[int]) -> tuple[int, ...]:
        """按角色校零。未校零的角色原样返回。"""
        off = self._offsets.get(role)
        if not off:
            return tuple(pressure)
        if self.strict and len(off) != len(pressure):
            raise ValueError(f"{role} 偏移长度 {len(off)} 与通道数 {len(pressure)} 不符")
        return tuple(int(v) - off[i] for i, v in enumerate(pressure) if i < len(off))

    def apply_frame(self, frame) -> tuple[int, ...]:
        """便捷入口：直接从帧取角色与原始压力。"""
        return self.apply(frame.role, frame.pressure)

    @staticmethod
    def raw(frame) -> tuple[int, ...]:
        """永远能拿回原始值。"""
        return tuple(frame.pressure)


def restore(tared: Sequence[int], offsets: Sequence[int]) -> tuple[int, ...]:
    """把校零后的值还原成原始值。"""
    return tuple(int(v) + int(offsets[i]) for i, v in enumerate(tared))


class TareJournal:
    """追加式校零档案，用于回溯与漂移分析。

    每行一个 JSON 对象（JSONL），只追加不覆盖。
    """

    def __init__(self, path: Path | str = DEFAULT_JOURNAL):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, result: TareResult, *, note: str = "", session: str = "") -> None:
        rec = result.to_json()
        if note:
            rec["note"] = note
        if session:
            rec["session"] = session
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def history(self, *, identity: str | None = None) -> list[dict]:
        """按时间顺序读出全部校零记录；identity 形如 '0x0A' 时只留含该板的记录。"""
        if not self.path.exists():
            return []
        out: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if identity:
                if identity.upper() not in {str(v).upper() for v in (rec.get("identities") or {}).values()}:
                    continue
            out.append(rec)
        out.sort(key=lambda r: r.get("created_ns", 0))
        return out

    def latest(self, *, identity: str | None = None) -> TareResult | None:
        hist = self.history(identity=identity)
        return TareResult.from_json(hist[-1]) if hist else None

    def drift(self, *, identity: str) -> list[dict]:
        """某个 identity 的零点随时间的漂移。

        返回 [{created_iso, offsets:[...]}, ...]，相邻两项之差即本次相对上次的漂移。
        """
        rows = []
        for rec in self.history(identity=identity):
            role = next((r for r, v in (rec.get("identities") or {}).items()
                         if str(v).upper() == identity.upper()), None)
            if role is None:
                continue
            offs = (rec.get("offsets") or {}).get(role) or []
            rows.append({"created_iso": rec.get("created_iso"), "role": role,
                         "offsets": [int(x) for x in offs],
                         "note": rec.get("note", "")})
        return rows
