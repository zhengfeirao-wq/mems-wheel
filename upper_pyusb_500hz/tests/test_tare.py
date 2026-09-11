"""校零模块测试：基线测量、应用、还原、档案与漂移。"""

import json
import time

import pytest

from tactile500 import TactileSystem
from tactile500.tare import (SATURATION, SENTINEL, ChannelBaseline, TareFilter,
                             TareJournal, TareResult, _channel_baseline,
                             tare_now, restore)
from helpers import FakeHub


# ---------- 端到端：用假系统采基线 ----------

def test_baseline_is_the_resting_value_and_tared_is_zero():
    hub = FakeHub()
    system = TactileSystem(enumerate_fn=hub.enumerate, transport_factory=hub.factory,
                           scan_interval=0.02)
    system.open()
    try:
        result = tare_now(system, seconds=0.4, min_samples=20)
        assert result.offsets, "没有采到任何板"
        # 假帧的压力值是 channel*100-1600，静置基线应当正好等于它
        for role, offsets in result.offsets.items():
            n = len(offsets)
            assert offsets == tuple(c * 100 - 1600 for c in range(n)), (role, offsets)
            assert all(b.status == "ok" for b in result.baselines[role])
            assert not result.warnings

        # 应用后应当全为 0
        tared = TareFilter(result)
        for role, offsets in result.offsets.items():
            shown = tared.apply(role, offsets)
            assert set(shown) == {0}

        # 还原后回到原始值
        assert restore(tared.apply("left_palm", result.offsets["left_palm"]),
                       result.offsets["left_palm"]) == result.offsets["left_palm"]
    finally:
        system.close()


def test_frame_keeps_raw_after_tare():
    """校零只影响视图，原始帧必须原封不动。"""
    hub = FakeHub()
    system = TactileSystem(enumerate_fn=hub.enumerate, transport_factory=hub.factory,
                           scan_interval=0.02)
    system.open()
    sub = system.subscribe(capacity=4096)
    try:
        result = tare_now(system, seconds=0.3, min_samples=20)
        tared = TareFilter(result)
        item = sub.get(timeout=3.0)
        frame = item.frame
        raw = tuple(frame.pressure)
        assert raw != tuple(tared.apply_frame(frame)) or set(raw) == {0}
        assert tuple(frame.pressure) == raw, "原始值被改动了"
        assert TareFilter.raw(frame) == raw
    finally:
        sub.close()
        system.close()


# ---------- 通道级判定 ----------

def test_saturated_channel_is_rejected():
    values = [SATURATION] * 100
    b = _channel_baseline(values, values, min_samples=10, max_spread=20_000,
                          reject_saturated=True)
    assert b.status == "saturated"
    assert b.offset == 0, "饱和通道不能给偏移，否则等于把故障抹掉"

    neg = [-SATURATION] * 100
    assert _channel_baseline(neg, neg, min_samples=10, max_spread=20_000,
                             reject_saturated=True).status == "saturated"


def test_unstable_channel_is_flagged_but_still_tared():
    values = [0] * 195 + [60_000] * 5
    b = _channel_baseline(values, values, min_samples=10, max_spread=20_000,
                          reject_saturated=True)
    assert b.status == "unstable"
    assert b.offset == 0
    assert b.spread == 60_000


def test_no_data_channel():
    b = _channel_baseline([], [], min_samples=10, max_spread=20_000, reject_saturated=True)
    assert b.status == "no_data" and b.offset == 0

    sent = [SENTINEL] * 50
    assert _channel_baseline(sent, sent, min_samples=10, max_spread=20_000,
                             reject_saturated=True).status == "no_data"


def test_spread_uses_fresh_samples_only():
    """非 fresh 是重复值，会低估波动；稳定性必须按 fresh 评估。"""
    repeated = [500] * 100
    fresh = [500, 501, 502]
    b = _channel_baseline(repeated, fresh, min_samples=2, max_spread=20_000,
                          reject_saturated=True)
    assert b.status == "ok"
    assert b.spread == 2, "应当用 fresh 样本算极差"


# ---------- 档案与漂移 ----------

def _fake_result(offsets, identities, created_ns):
    bl = {r: tuple(ChannelBaseline(o, 0, 100, "ok") for o in offs)
          for r, offs in offsets.items()}
    return TareResult(created_ns=created_ns, duration_s=2.0, offsets=offsets,
                      baselines=bl, identities=identities)


def test_journal_append_history_and_drift(tmp_path):
    journal = TareJournal(tmp_path / "journal.jsonl")
    day1 = _fake_result({"left_palm": (100, 200, 300)}, {"left_palm": 0x0A}, 1_700_000_000_000_000_000)
    day5 = _fake_result({"left_palm": (160, 250, 340)}, {"left_palm": 0x0A}, 1_700_400_000_000_000_000)
    journal.append(day1, note="第 1 天开机")
    journal.append(day5, note="第 5 天开机")

    hist = journal.history()
    assert len(hist) == 2
    assert hist[0]["note"] == "第 1 天开机"

    only_left = journal.history(identity="0x0a")
    assert len(only_left) == 2
    assert journal.history(identity="0x0B") == []

    drift = journal.drift(identity="0x0a")
    assert [d["created_iso"] for d in drift] == [day1.created_iso, day5.created_iso]
    delta = [b - a for a, b in zip(drift[0]["offsets"], drift[1]["offsets"])]
    assert delta == [60, 50, 40], "5 天漂移应当可算出来"

    latest = journal.latest(identity="0x0a")
    assert isinstance(latest, TareResult)
    assert latest.offsets["left_palm"] == (160, 250, 340)


def test_journal_skips_corrupt_lines(tmp_path):
    path = tmp_path / "journal.jsonl"
    journal = TareJournal(path)
    journal.append(_fake_result({"left_palm": (1,)}, {"left_palm": 0x0A}, 1))
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{ this is not json\n\n")
    journal.append(_fake_result({"left_palm": (2,)}, {"left_palm": 0x0A}, 2))
    assert len(journal.history()) == 2


def test_result_json_round_trip(tmp_path):
    original = _fake_result({"left_palm": (10, -20), "right_fingers": (7,)},
                            {"left_palm": 0x0A, "right_fingers": 0x09}, 123)
    again = TareResult.from_json(json.loads(json.dumps(original.to_json())))
    assert again.offsets == original.offsets
    assert again.identities == original.identities
    assert again.created_ns == original.created_ns
    assert [b.status for b in again.baselines["left_palm"]] == ["ok", "ok"]


# ---------- 应用器边界 ----------

def test_filter_leaves_untared_roles_untouched():
    result = _fake_result({"left_palm": (100, 100)}, {"left_palm": 0x0A}, 1)
    f = TareFilter(result)
    assert f.apply("right_fingers", (5, 6, 7)) == (5, 6, 7)
    assert f.offsets_for("right_fingers") == ()


def test_filter_strict_rejects_length_mismatch():
    result = _fake_result({"left_palm": (100, 100)}, {"left_palm": 0x0A}, 1)
    TareFilter(result).apply("left_palm", (1, 2, 3))  # 宽松模式不报错
    with pytest.raises(ValueError):
        TareFilter(result, strict=True).apply("left_palm", (1, 2, 3))

def test_old_name_still_works():
    """0.4.0 的 measure_baseline 必须继续可用。"""
    import tactile500.tare as tare
    assert tare.measure_baseline is tare.tare_now
    from tactile500 import measure_baseline, tare_now
    assert measure_baseline is tare_now