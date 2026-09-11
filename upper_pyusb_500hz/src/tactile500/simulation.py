"""Four paced V2 sources for UI demonstrations and reproducible host load tests.

This uses the actual stream decoder and acquisition threads, but not libusb.
"""
from __future__ import annotations

import binascii
import math
import struct
import time

from .api import TactileSystem
from .transport.base import DeviceDescriptor


class DemoHub:
    roles = {"demo-left12": 8, "demo-right12": 9,
             "demo-left32": 14, "demo-right32": 15}

    def enumerate(self):
        return [DeviceDescriptor(path, 0, i + 1, (i + 1,), 0x1A86, 0x7523)
                for i, path in enumerate(self.roles)]

    def factory(self, path):
        identity = self.roles[path]

        class Transport:
            descriptor = {"simulation": True, "wMaxPacketSize": 32}

            def open(self):
                self.sequence = 0
                self.started = time.monotonic()

            def read(self, timeout):
                self.sequence += 1
                time.sleep(max(0, self.started + self.sequence * 0.002 - time.monotonic()))
                n = 32 if identity & 2 else 12
                seq = self.sequence
                raw = bytearray((0xA5, 0x5A, 20 + 5 * n, 0x21, identity, 0))
                raw += struct.pack("<III", seq & 0xFFFFFFFF,
                                   (seq * 2000) & 0xFFFFFFFF, (1 << n) - 1)
                raw += struct.pack("<" + "h" * n, *[300 + i % 10 for i in range(n)])
                for i in range(n):
                    value = round(1000 * math.sin(seq * 0.008 + i * 0.3) + i * 150)
                    raw += value.to_bytes(3, "little", signed=True)
                return bytes(raw + struct.pack("<H", binascii.crc_hqx(raw, 0xFFFF)))

            def close(self):
                pass

        return Transport()


def demo_system() -> TactileSystem:
    hub = DemoHub()
    return TactileSystem(enumerate_fn=hub.enumerate, transport_factory=hub.factory)
