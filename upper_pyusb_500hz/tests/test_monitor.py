import json
from pathlib import Path
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from tactile500 import read_recording
from tactile500.monitor import Monitor, make_server
from tactile500.simulation import demo_system
from helpers import wait_for


def test_http_mapping_recording_and_cache(tmp_path):
    system = demo_system()
    monitor = Monitor(system, tmp_path, simulation=True)
    server = make_server(monitor, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    base = "http://127.0.0.1:" + str(server.server_port)
    system.open()
    monitor.start()
    thread.start()
    try:
        wait_for(lambda: len(json.loads(monitor.cached()).get("boards", [])) == 4)
        wait_for(lambda: all(b.get("pressure") for b in json.loads(monitor.cached())["boards"]))
        payload = json.load(urlopen(base + "/api/snapshot", timeout=2))
        left = next(b for b in payload["boards"] if b["role"] == "left_palm")
        assert left["source_channels"][:4] == [13, 15, 5, 3]
        assert left["state"] == "updated"
        assert len(left["pressure"]) == 32
        assert payload["simulation"]
        assert b"__CONTROL_TOKEN__" not in urlopen(base, timeout=2).read()
        # A webpage on another origin must not start/stop recordings.
        with pytest.raises(HTTPError) as denied:
            urlopen(Request(base + "/api/record/start", method="POST"), timeout=2)
        assert denied.value.code == 403
        request = Request(base + "/api/record/start", method="POST",
                          headers={"X-Tactile-Control": monitor.control_token})
        rec = json.load(urlopen(request, timeout=2))
        # Repeated start is idempotent and does not create a second writer.
        again = json.load(urlopen(request, timeout=2))
        assert rec["directory"] == again["directory"]
        wait_for(lambda: monitor.recording_status()["records"] >= 500)
        stopped = json.load(urlopen(Request(base + "/api/record/stop", method="POST",
                            headers={"X-Tactile-Control": monitor.control_token}), timeout=3))
        report = stopped["last"]
        assert report["dropped"] == 0 and report["error"] is None
        count = sum(sum(1 for _ in read_recording(Path(report["directory"]) / f))
                    for f in report["files"])
        assert len(report["files"]) == 4 and count == report["records"]
        # Extra HTTP readers do not create acquisition subscriptions.
        for _ in range(10):
            json.load(urlopen(base + "/api/snapshot", timeout=2))
        assert system.status()["subscriber_drops"] == []
    finally:
        server.shutdown()
        server.server_close()
        system.close()
        monitor.close()


def test_monitor_does_not_relabel_unconfirmed_long_mapping(tmp_path):
    from helpers import FakeHub
    from tactile500 import TactileSystem
    hub = FakeHub()
    hub.roles["port3"] = 10
    with TactileSystem(enumerate_fn=hub.enumerate, transport_factory=hub.factory) as system:
        monitor = Monitor(system, tmp_path)
        wait_for(lambda: system.snapshot().slots["left_palm"].value is not None)
        board = next(b for b in monitor.snapshot_payload()["boards"] if b["role"] == "left_palm")
        assert board["source_channels"] == list(range(1, 33))
        assert "物理位置未确认" in board["mapping"]
        assert board["pressure"][0] == -1600
