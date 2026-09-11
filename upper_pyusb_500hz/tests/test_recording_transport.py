import json
import struct

import pytest

from tactile500.recording import MAGIC, RECORD, read_recording
from tactile500.transport.pyusb_ch340 import CH340PyUsbTransport, configure_921600_8n1
from helpers import packet


def test_recording_rejects_truncation_and_crc_damage(tmp_path):
    raw = packet()
    metadata = json.dumps({"format_version": 2, "path": "port1"}).encode()
    data = MAGIC + struct.pack("<I", len(metadata)) + metadata
    data += RECORD.pack(100, 90, 1, len(raw), 0) + raw
    path = tmp_path / "capture.t5raw"
    path.write_bytes(data)
    assert next(read_recording(path)).frame.raw == raw
    for corrupt in (data[:-1], data[:-1] + bytes([data[-1] ^ 1]), data[:13]):
        path.write_bytes(corrupt)
        with pytest.raises((ValueError, json.JSONDecodeError)):
            list(read_recording(path))


def test_pyusb_read_timeout_is_bounded_by_callers_deadline():
    class USBTimeoutError(Exception):
        pass

    class Core:
        pass

    Core.USBTimeoutError = USBTimeoutError

    class Endpoint:
        def __init__(self):
            self.timeouts = []

        def read(self, size, timeout):
            self.timeouts.append(timeout)
            return b"data"

    transport = CH340PyUsbTransport("p", read_timeout_ms=1000)
    endpoint = Endpoint()
    transport.endpoint_in, transport._usb_core = endpoint, Core
    assert transport.read(0.005) == b"data"
    assert 1 <= endpoint.timeouts[0] <= 5


def test_bridge_sequence_preserves_proven_921600_configuration():
    class Device:
        def __init__(self):
            self.calls = []

        def ctrl_transfer(self, request_type, request, value, index, payload, timeout):
            self.calls.append((request_type, request, value, index))
            return bytes(2)

    dev = Device()
    configure_921600_8n1(dev)
    assert dev.calls == [
        (0xC0, 0x5F, 0, 0), (0x40, 0xA1, 0, 0),
        (0x40, 0x9A, 0x1312, 0xD982), (0x40, 0x9A, 0x0F2C, 7),
        (0xC0, 0x95, 0x2518, 0), (0xC0, 0x95, 0x0706, 0),
        (0x40, 0x9A, 0x2727, 0), (0x40, 0xA1, 0xC39C, 0xF387),
        (0x40, 0x9A, 0x0F2C, 7), (0x40, 0x9A, 0x2727, 0),
        (0x40, 0xA4, 0x9F, 0),
    ]
