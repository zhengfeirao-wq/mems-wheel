import binascii
import struct
import threading
import time

from tactile500.transport.base import DeviceDescriptor


def packet(identity=8, sequence=1, timestamp=2000, fresh=None, status=0):
    n = 32 if identity & 2 else 12
    fresh = (1 << n) - 1 if fresh is None else fresh
    data = bytearray((0xA5, 0x5A, 20 + 5 * n, 0x21, identity, status))
    data += struct.pack("<III", sequence & 0xFFFFFFFF, timestamp & 0xFFFFFFFF, fresh)
    data += struct.pack("<" + "h" * n, *range(-n, 0))
    for channel in range(n):
        data += int(channel * 100 - 1600).to_bytes(3, "little", signed=True)
    return bytes(data + struct.pack("<H", binascii.crc_hqx(data, 0xFFFF)))


class FakeHub:
    def __init__(self):
        self.roles = {"port1": 8, "port2": 9, "port3": 14, "port4": 15}
        self.present = set(self.roles)
        self.failures = {}
        self.opens = {}
        self.lock = threading.Lock()

    def enumerate(self):
        with self.lock:
            return [DeviceDescriptor(p, 1, i + 1, (i + 1,), 0x1A86, 0x7523)
                    for i, p in enumerate(sorted(self.present))]

    def factory(self, path):
        hub = self

        class Transport:
            descriptor = {"wMaxPacketSize": 32, "simulation": True}
            read_size = 64

            def open(self):
                with hub.lock:
                    hub.opens[path] = hub.opens.get(path, 0) + 1
                    if path not in hub.present or hub.failures.get(path, 0):
                        hub.failures[path] = max(0, hub.failures.get(path, 0) - 1)
                        raise OSError("simulated device unavailable")
                    self.identity = hub.roles[path]
                self.sequence = 0
                self.next_due = time.monotonic() + 0.002

            def read(self, timeout):
                with hub.lock:
                    if path not in hub.present or hub.roles[path] != self.identity:
                        raise OSError("simulated unplug")
                time.sleep(max(0, self.next_due - time.monotonic()))
                self.next_due += 0.002
                self.sequence += 1
                return packet(self.identity, self.sequence, self.sequence * 2000)

            def close(self):
                pass

        return Transport()


def wait_for(predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    assert predicate(), "condition did not become true"
