"""PyUSB transport for the CH340 bridge (Linux/Ubuntu and beyond).

The CH340 is used passively: the MCU streams continuously, the host only reads
Bulk IN. Opening does require CH340 bridge configuration over EP0 vendor
control transfers (921600 8N1 plus DTR/RTS); that is *bridge* configuration, not
an MCU command.

This module deliberately refuses to take an interface that a kernel driver
already owns. On the target robot the kernel ships no ``ch341`` module at all,
so the interface is free; on a stock Ubuntu image ``ch341`` binds and the
correct answer is to stop and let an administrator decide, never to detach.
"""

from __future__ import annotations

import errno
import time
from typing import Any

from .base import (
    DeviceDescriptor,
    TransportBusy,
    TransportError,
    TransportFault,
    TransportUnavailable,
)

VID = 0x1A86
PID = 0x7523
BAUDRATE = 921600

CMD_READ_VERSION = 0x5F
CMD_READ_REG = 0x95
CMD_WRITE_REG = 0x9A
CMD_SERIAL_INIT = 0xA1
CMD_MODEM_CTRL = 0xA4

READ_SIZE = 64
READ_TIMEOUT_MS = 50
CONTROL_TIMEOUT_MS = 500


class _CoreWithBackend:
    """Pin the discovered libusb backend while delegating other attributes."""

    def __init__(self, core: Any, backend: Any) -> None:
        self._core = core
        self._backend = backend

    def find(self, **kwargs: Any) -> Any:
        return self._core.find(backend=self._backend, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._core, name)


def _usb_modules(usb_core: Any | None, usb_util: Any | None) -> tuple[Any, Any]:
    if usb_core is not None and usb_util is not None:
        return usb_core, usb_util
    try:
        from usb import core as imported_core
        from usb import util as imported_util
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise TransportError(
            "PyUSB is required for the CH340 transport (pip install pyusb)"
        ) from exc
    if usb_core is None:
        backend = None
        try:
            import libusb_package  # type: ignore[import-not-found]

            backend = libusb_package.get_libusb1_backend()
        except Exception:  # noqa: BLE001 - optional convenience on Windows
            backend = None
        usb_core = imported_core if backend is None else _CoreWithBackend(imported_core, backend)
    if usb_util is None:
        usb_util = imported_util
    return usb_core, usb_util


def topology_path(device: Any) -> str:
    """Stable USB topology identity, e.g. ``1-1.4.1``.

    Falls back to a display-only string that carries no identity guarantee; call
    :func:`enumerate_devices` and check ``DeviceDescriptor.stable_identity``
    before trusting a path.
    """

    ports = tuple(getattr(device, "port_numbers", ()) or ())
    if ports:
        return f"{int(device.bus)}-" + ".".join(str(int(port)) for port in ports)
    return f"bus-{int(device.bus):03d}-address-{int(device.address):03d}"


def _optional_string(usb_util: Any, device: Any, index: Any) -> str | None:
    if not index:
        return None
    try:
        return str(usb_util.get_string(device, index))
    except Exception:  # noqa: BLE001 - descriptors are optional diagnostics
        return None


def enumerate_devices(*, usb_core: Any | None = None, usb_util: Any | None = None) -> list[DeviceDescriptor]:
    """Return every CH340 with its stable topology path, sorted deterministically."""

    core, util = _usb_modules(usb_core, usb_util)
    found = list(core.find(find_all=True, idVendor=VID, idProduct=PID) or [])
    descriptors = [
        DeviceDescriptor(
            path=topology_path(device),
            bus=int(device.bus),
            address=int(device.address),
            port_numbers=tuple(int(port) for port in (getattr(device, "port_numbers", ()) or ())),
            vid=int(getattr(device, "idVendor", VID)),
            pid=int(getattr(device, "idProduct", PID)),
            product=None,  # 热插拔枚举不读取可能阻塞的设备字符串。
            serial=None,
            speed=int(getattr(device, "speed", 0) or 0) or None,
        )
        for device in found
    ]
    return sorted(descriptors, key=lambda item: (item.path, item.address))


def select_device(path: str, *, usb_core: Any | None = None, usb_util: Any | None = None) -> Any:
    """Return the single CH340 whose stable topology path is exactly ``path``."""

    core, _ = _usb_modules(usb_core, usb_util)
    candidates = list(core.find(find_all=True, idVendor=VID, idProduct=PID) or [])
    matches = [
        device
        for device in candidates
        if tuple(getattr(device, "port_numbers", ()) or ()) and topology_path(device) == path
    ]
    if len(matches) != 1:
        available = ", ".join(topology_path(device) for device in candidates) or "none"
        raise TransportUnavailable(
            f"USB path {path!r} resolved to {len(matches)} CH340 devices; available: {available}"
        )
    return matches[0]


def _control_out(device: Any, request: int, value: int, index: int) -> None:
    try:
        device.ctrl_transfer(0x40, request, value, index, [], timeout=CONTROL_TIMEOUT_MS)
    except Exception as exc:
        raise TransportFault(f"CH340 control OUT request=0x{request:02x} value=0x{value:04x}: {exc}") from exc


def _control_in(device: Any, request: int, value: int, index: int, length: int = 2) -> bytes:
    try:
        return bytes(device.ctrl_transfer(0xC0, request, value, index, length, timeout=CONTROL_TIMEOUT_MS))
    except Exception as exc:
        raise TransportFault(f"CH340 control IN request=0x{request:02x} value=0x{value:04x}: {exc}") from exc


def configure_921600_8n1(device: Any) -> None:
    """CH340 bridge configuration for 921600 8N1 with DTR/RTS asserted.

    Byte-for-byte the sequence proven on the target hardware by the 100Hz
    collector; changing it needs hardware validation.
    """

    _control_in(device, CMD_READ_VERSION, 0, 0)
    _control_out(device, CMD_SERIAL_INIT, 0, 0)
    _control_out(device, CMD_WRITE_REG, 0x1312, 0xD982)
    _control_out(device, CMD_WRITE_REG, 0x0F2C, 0x0007)
    _control_in(device, CMD_READ_REG, 0x2518, 0)
    _control_in(device, CMD_READ_REG, 0x0706, 0)
    _control_out(device, CMD_WRITE_REG, 0x2727, 0)
    _control_out(device, CMD_SERIAL_INIT, 0xC39C, 0xF387)
    _control_out(device, CMD_WRITE_REG, 0x0F2C, 0x0007)
    _control_out(device, CMD_WRITE_REG, 0x2727, 0)
    _control_out(device, CMD_MODEM_CTRL, 0x9F, 0)  # DTR + RTS asserted


def release_modem(device: Any) -> None:
    """Drop DTR/RTS so the MCU sees a clean disconnect."""

    _control_out(device, CMD_MODEM_CTRL, 0xFF, 0)


def _is_timeout(exc: BaseException, usb_core: Any) -> bool:
    timeout_type = getattr(usb_core, "USBTimeoutError", None)
    if timeout_type is not None and isinstance(exc, timeout_type):
        return True
    if getattr(exc, "errno", None) in {errno.ETIMEDOUT, 60, 110}:
        return True
    for attribute in ("backend_error_code", "libusb_error_code", "_libusb_errno"):
        if getattr(exc, attribute, None) == -7:  # LIBUSB_ERROR_TIMEOUT
            return True
    return False


def _product_string(device: Any, usb_util: Any) -> str | None:
    return _optional_string(usb_util, device, getattr(device, "iProduct", 0))


class CH340PyUsbTransport:
    """Passive CH340 reader: open, bulk-IN reads, close."""

    def __init__(
        self,
        path: str,
        *,
        usb_core: Any | None = None,
        usb_util: Any | None = None,
        read_size: int = READ_SIZE,
        read_timeout_ms: int = READ_TIMEOUT_MS,
        configure_bridge: bool = True,
        settle_seconds: float = 0.05,
        sleep: Any = time.sleep,
    ) -> None:
        if read_size < 1:
            raise ValueError("read_size must be positive")
        self.path = path
        self.read_size = int(read_size)
        self.read_timeout_ms = int(read_timeout_ms)
        self.configure_bridge = bool(configure_bridge)
        self.settle_seconds = float(settle_seconds)
        self._sleep = sleep
        self._usb_core_arg = usb_core
        self._usb_util_arg = usb_util
        self._usb_core: Any | None = None
        self._usb_util: Any | None = None
        self.device: Any | None = None
        self.endpoint_in: Any | None = None
        self.endpoint_out: Any | None = None
        self.descriptor: dict[str, object] = {}
        self._claimed = False
        self._closed = True

    # -- lifecycle ---------------------------------------------------------

    def open(self) -> None:
        if not self._closed:
            raise TransportError(f"transport {self.path!r} is already open")
        usb_core, usb_util = _usb_modules(self._usb_core_arg, self._usb_util_arg)
        device = None
        asserted = False
        try:
            device = select_device(self.path, usb_core=usb_core, usb_util=usb_util)
            if self._kernel_driver_active(device, usb_core):
                raise TransportBusy(
                    "CH340 interface 0 is owned by a kernel driver; "
                    "refusing to detach it (administrator decision required)"
                )
            try:
                active_configuration = device.get_active_configuration()
            except usb_core.USBError:
                active_configuration = None
            if active_configuration is None:
                device.set_configuration()
            usb_util.claim_interface(device, 0)
            asserted = True
            configuration = device.get_active_configuration()
            interface = configuration[(0, 0)]
            endpoint_in = usb_util.find_descriptor(
                interface,
                custom_match=lambda endpoint: (
                    usb_util.endpoint_direction(endpoint.bEndpointAddress)
                    == usb_util.ENDPOINT_IN
                    and endpoint.bmAttributes & 0x03 == usb_util.ENDPOINT_TYPE_BULK
                ),
            )
            endpoint_out = usb_util.find_descriptor(
                interface,
                custom_match=lambda endpoint: (
                    usb_util.endpoint_direction(endpoint.bEndpointAddress)
                    == usb_util.ENDPOINT_OUT
                    and endpoint.bmAttributes & 0x03 == usb_util.ENDPOINT_TYPE_BULK
                ),
            )
            if endpoint_in is None:
                raise TransportFault("CH340 bulk IN endpoint not found")
            max_packet = int(getattr(endpoint_in, "wMaxPacketSize", 0) or 0)
            if max_packet and self.read_size % max_packet:
                raise TransportError(
                    f"read_size={self.read_size} must be a multiple of the bulk "
                    f"endpoint's wMaxPacketSize={max_packet}; otherwise the device "
                    f"sends more bytes than requested and libusb reports "
                    f"LIBUSB_ERROR_OVERFLOW. Recommended: {max_packet * 5}."
                )
            if self.configure_bridge:
                configure_921600_8n1(device)
                if self.settle_seconds:
                    self._sleep(self.settle_seconds)
                self._drain(endpoint_in, usb_core)
            self._usb_core, self._usb_util = usb_core, usb_util
            self.device = device
            self.endpoint_in = endpoint_in
            self.endpoint_out = endpoint_out
            self._claimed = True
            self._closed = False
            self.descriptor = {
                "path": self.path,
                "bus": int(device.bus),
                "address": int(device.address),
                "port_numbers": tuple(int(p) for p in (getattr(device, "port_numbers", ()) or ())),
                "product": _product_string(device, usb_util),
                "speed": int(getattr(device, "speed", 0) or 0) or None,
                "endpoint_in": f"0x{endpoint_in.bEndpointAddress:02x}",
                "endpoint_out": (
                    f"0x{endpoint_out.bEndpointAddress:02x}" if endpoint_out is not None else None
                ),
                "wMaxPacketSize": int(getattr(endpoint_in, "wMaxPacketSize", 0) or 0),
            }
        except TransportError:
            self._cleanup(device, usb_util, asserted)
            raise
        except Exception as exc:  # noqa: BLE001 - normalise backend failures
            self._cleanup(device, usb_util, asserted)
            if "busy" in str(exc).lower() or getattr(exc, "errno", None) == errno.EBUSY:
                raise TransportBusy(
                    f"CH340 {self.path!r} is held by another owner: {exc}"
                ) from exc
            raise TransportFault(f"cannot open CH340 {self.path!r}: {exc}") from exc

    def read(self, timeout: float = 1.0) -> bytes:
        """Return available bytes, or ``b""`` when ``timeout`` expires."""

        if self.endpoint_in is None or self._usb_core is None:
            raise TransportError(f"transport {self.path!r} is not open")
        deadline = time.monotonic() + max(0.001, timeout)
        while True:
            try:
                remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
                return bytes(self.endpoint_in.read(
                    self.read_size, timeout=min(self.read_timeout_ms, remaining_ms)))
            except Exception as exc:  # noqa: BLE001
                if _is_timeout(exc, self._usb_core):
                    if time.monotonic() >= deadline:
                        return b""
                    continue
                if getattr(exc, "errno", None) in {errno.EOVERFLOW, 75} or "overflow" in str(exc).lower():
                    raise TransportFault(
                        f"CH340 {self.path!r} read overflow: read_size={self.read_size} "
                        f"is not a multiple of wMaxPacketSize, so the device returned "
                        f"more bytes than requested: {exc}"
                    ) from exc
                raise TransportFault(f"CH340 {self.path!r} read failed: {exc}") from exc

    def discard(self) -> int:
        """Drop bytes that arrived before the current session."""

        if self.endpoint_in is None or self._usb_core is None:
            raise TransportError(f"transport {self.path!r} is not open")
        return self._drain(self.endpoint_in, self._usb_core)

    def close(self) -> None:
        if self._closed:
            return
        device, usb_util = self.device, self._usb_util
        self._closed = True
        self.endpoint_in = None
        self.endpoint_out = None
        self.device = None
        if device is not None and self.configure_bridge:
            try:
                release_modem(device)
            except Exception:  # noqa: BLE001 - best effort on shutdown
                pass
        self._cleanup(device, usb_util, self._claimed)
        self._claimed = False

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _kernel_driver_active(device: Any, usb_core: Any) -> bool:
        try:
            return bool(device.is_kernel_driver_active(0))
        except (NotImplementedError, AttributeError):
            return False
        except Exception as exc:  # noqa: BLE001
            if hasattr(usb_core, "USBError") and isinstance(exc, usb_core.USBError):
                return False
            raise

    def _drain(self, endpoint: Any, usb_core: Any) -> int:
        packet = int(getattr(endpoint, "wMaxPacketSize", 32) or 32)
        total = 0
        for _ in range(16):
            try:
                chunk = bytes(endpoint.read(packet, timeout=1))
            except Exception as exc:  # noqa: BLE001
                if _is_timeout(exc, usb_core):
                    break
                raise
            if not chunk:
                break
            total += len(chunk)
        return total

    def _cleanup(self, device: Any, usb_util: Any, claimed: bool) -> None:
        if device is None or usb_util is None:
            return
        if claimed:
            try:
                usb_util.release_interface(device, 0)
            except Exception:  # noqa: BLE001
                pass
        try:
            usb_util.dispose_resources(device)
        except Exception:  # noqa: BLE001
            pass


def transport_factory(path: str, **kwargs: Any) -> CH340PyUsbTransport:
    return CH340PyUsbTransport(path, **kwargs)


__all__ = [
    "VID",
    "PID",
    "BAUDRATE",
    "CH340PyUsbTransport",
    "configure_921600_8n1",
    "enumerate_devices",
    "release_modem",
    "select_device",
    "topology_path",
    "transport_factory",
]
