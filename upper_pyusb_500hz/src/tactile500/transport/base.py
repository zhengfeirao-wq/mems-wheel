"""Transport abstraction: anything that can deliver raw device bytes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class TransportError(RuntimeError):
    """Base class for transport failures."""


class TransportUnavailable(TransportError):
    """The requested device is not present."""


class TransportBusy(TransportError):
    """Another owner holds the device interface (kernel driver or a service)."""


class TransportFault(TransportError):
    """The link failed while in use."""


@dataclass(frozen=True, slots=True)
class DeviceDescriptor:
    """Read-only identity of an enumerated device."""

    path: str
    bus: int
    address: int
    port_numbers: tuple[int, ...]
    vid: int
    pid: int
    product: str | None = None
    serial: str | None = None
    speed: int | None = None
    extra: dict[str, object] = field(default_factory=dict)

    @property
    def stable_identity(self) -> bool:
        """True when the path is a real topology path (not a display fallback)."""

        return bool(self.port_numbers)

    def describe(self) -> str:
        product = self.product or "CH340"
        return (
            f"{self.path} bus={self.bus} addr={self.address} "
            f"ports={self.port_numbers} {product}"
        )


@runtime_checkable
class Transport(Protocol):
    """A synchronous byte source.

    ``read`` returns as soon as any bytes are available and ``b""`` when the
    timeout expires without data. It must never block forever.
    """

    path: str

    def open(self) -> None: ...

    def read(self, timeout: float) -> bytes: ...

    def discard(self) -> int: ...

    def close(self) -> None: ...


__all__ = [
    "Transport",
    "TransportError",
    "TransportUnavailable",
    "TransportBusy",
    "TransportFault",
    "DeviceDescriptor",
]
