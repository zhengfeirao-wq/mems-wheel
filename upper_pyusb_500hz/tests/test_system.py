import queue
import time

from tactile500 import Recorder, TactileSystem, read_recording
from tactile500.api import ReceivedFrame, _Board
from tactile500.mapping import SHORT_POSITION_TO_CHANNEL, physical_values
from tactile500.protocol import decode_frame
from helpers import FakeHub, packet, wait_for


def test_four_boards_failed_open_unplug_role_swap_and_slow_consumer(tmp_path):
    hub = FakeHub()
    hub.failures["port1"] = 3
    system = TactileSystem(enumerate_fn=hub.enumerate, transport_factory=hub.factory,
                           scan_interval=0.02)
    slow = system.subscribe(2)
    recorder = Recorder(system, tmp_path / "capture")
    system.open()
    try:
        wait_for(lambda: len([b for b in system.status()["boards"] if b.get("frames", 0) >= 20]) >= 3)
        assert hub.opens.get("port1", 0) >= 1
        wait_for(lambda: all(b.get("frames", 0) > 20 for b in system.status()["boards"]))
        assert len(system.status()["boards"]) == 4
        with hub.lock:
            hub.present.remove("port1")
        wait_for(lambda: system.status()["roles"]["left_fingers"] == "offline")
        before = next(b["frames"] for b in system.status()["boards"] if b["path"] == "port4")
        time.sleep(0.06)
        after = next(b["frames"] for b in system.status()["boards"] if b["path"] == "port4")
        assert after > before + 10
        with hub.lock:
            hub.present.add("port1")
            hub.roles["port1"], hub.roles["port3"] = hub.roles["port3"], hub.roles["port1"]
        wait_for(lambda: all(system.status()["roles"][r] == "updated" for r in system.expected_roles))
        roles = {b["path"]: b["role"] for b in system.status()["boards"]}
        assert roles["port1"] == "left_palm" and roles["port3"] == "left_fingers"
        assert slow.dropped > 0
        assert slow._queue.qsize() <= 2
    finally:
        system.close()
        report = recorder.close()
        slow.close()
    assert report["error"] is None and report["dropped"] == 0
    count = sum(1 for file in (tmp_path / "capture").glob("*.t5raw") for _ in read_recording(file))
    assert count == report["records"] and count > 100


def test_snapshot_causal_reuse_stale_missing_and_ambiguous():
    system = TactileSystem(stale_seconds=0.020)
    a = ReceivedFrame(decode_frame(packet()), "a", 1, 90_000_000, 100_000_000)
    b = ReceivedFrame(decode_frame(packet(sequence=2)), "a", 1, 101_000_000, 102_000_000)
    board = _Board("a", connected=True, latest=b)
    board.history.extend([a, b])
    system._boards["a"] = board
    first = system.snapshot(101_000_000)
    assert first.slots["left_fingers"].value is a
    assert first.slots["right_fingers"].state == "missing"
    second = system.snapshot(101_500_000, previous=first)
    assert second.slots["left_fingers"].state == "reused"
    assert system.snapshot(130_000_000).slots["left_fingers"].state == "stale"
    system._boards["duplicate"] = _Board("duplicate", connected=True, latest=a)
    assert system.snapshot(101_000_000).slots["left_fingers"].state == "ambiguous"


def test_physical_mapping_moves_freshness_with_values():
    frame = decode_frame(packet(14, fresh=1 << 12))
    temp, press, fresh = physical_values(frame)
    assert len(set(SHORT_POSITION_TO_CHANNEL)) == 32
    assert temp[0] == frame.temperature[12] and press[0] == frame.pressure[12]
    assert fresh == 1
