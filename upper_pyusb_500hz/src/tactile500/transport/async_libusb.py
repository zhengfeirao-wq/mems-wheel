"""Queued Bulk IN using the libusb1 backend already opened by PyUSB 1.3.1.

PyUSB's public endpoint.read is synchronous. This small adapter reuses PyUSB's
ctypes declarations and claimed handle to keep 32 requests in flight. The
private backend dependency is intentionally pinned and isolated to this file.
See libusb's asynchronous I/O API: buffers remain owned until cancellation has
completed; transfers may be resubmitted only after their completion callback.
"""
from __future__ import annotations

import ctypes as C
import queue
import threading
import time


class _Timeval(C.Structure):
    _fields_ = [("tv_sec", C.c_long), ("tv_usec", C.c_long)]


class AsyncReadPump:
    def __init__(self, transport, depth=32):
        import usb
        from usb.backend import libusb1

        if usb.__version__ != "1.3.1":
            raise RuntimeError("queued USB reader requires PyUSB 1.3.1")
        context = transport.device._ctx
        if not isinstance(context.backend, libusb1._LibUSB):
            raise RuntimeError("queued USB reader requires PyUSB libusb1 backend")
        self.transport = transport
        self.backend = context.backend
        self.handle = context.handle.handle
        self.lib = self.backend.lib
        self.lib.libusb_cancel_transfer.argtypes = [libusb1._libusb_transfer_p]
        self.lib.libusb_cancel_transfer.restype = C.c_int
        self.lib.libusb_handle_events_timeout_completed.argtypes = [
            C.c_void_p, C.POINTER(_Timeval), C.POINTER(C.c_int)]
        self.lib.libusb_handle_events_timeout_completed.restype = C.c_int
        self.queue: queue.Queue = queue.Queue(2048)
        self.stop = threading.Event()
        self.error: Exception | None = None
        self.dropped = 0
        self._pending = set()
        self._callbacks_active = 0
        self._transfers = {}
        self._buffers = []
        self._submission = {}
        self._next_submission = 0
        self._next_delivery = 0
        self._completed = {}
        self._callback = libusb1._libusb_transfer_cb_fn_p(self._on_complete)
        self._capacity = max(512, transport.read_size)
        try:
            for _ in range(depth):
                transfer = self.lib.libusb_alloc_transfer(0)
                if not transfer:
                    raise MemoryError("libusb_alloc_transfer")
                address = C.addressof(transfer.contents)
                self._transfers[address] = transfer
                buffer = (C.c_ubyte * self._capacity)()
                self._buffers.append(buffer)
                fields = transfer.contents
                fields.dev_handle = self.handle
                fields.flags = 0
                fields.endpoint = transport.endpoint_in.bEndpointAddress
                fields.type = 2  # LIBUSB_TRANSFER_TYPE_BULK
                fields.timeout = 0  # Silence is handled by the board's watchdog.
                fields.buffer = C.cast(buffer, C.c_void_p)
                fields.callback = self._callback
                fields.num_iso_packets = 0
        except Exception:
            for transfer in self._transfers.values():
                self.lib.libusb_free_transfer(transfer)
            raise
        self.thread = threading.Thread(target=self._run, name="tactile-usb-async", daemon=True)
        self.thread.start()

    def _submit(self, transfer):
        address = C.addressof(transfer.contents)
        transfer.contents.length = min(self._capacity, self.transport.read_size)
        number = self._next_submission
        self._next_submission += 1
        self._submission[address] = (number, time.monotonic_ns())
        self._pending.add(address)
        result = self.lib.libusb_submit_transfer(transfer)
        if result < 0:
            self._pending.discard(address)
            raise OSError(f"libusb_submit_transfer: {result}")

    def _on_complete(self, transfer):
        # A ctypes callback must never let exceptions escape into C.
        self._callbacks_active += 1
        try:
            ended = time.monotonic_ns()
            address = C.addressof(transfer.contents)
            self._pending.discard(address)
            number, started = self._submission.pop(address)
            fields = transfer.contents
            status = fields.status
            if status not in (0, 2, 3):
                raise OSError(f"libusb transfer status {status}")
            data = C.string_at(fields.buffer, fields.actual_length) if fields.actual_length else b""
            self._completed[number] = (started, ended, data)
            if not self.stop.is_set():
                self._submit(transfer)
            while self._next_delivery in self._completed:
                item = self._completed.pop(self._next_delivery)
                self._next_delivery += 1
                if item[2]:
                    try:
                        self.queue.put_nowait((*item, self.dropped))
                    except queue.Full:
                        try:
                            self.queue.get_nowait()
                            self.dropped += 1
                        except queue.Empty:
                            pass
                        self.queue.put_nowait((*item, self.dropped))
            if len(self._completed) > 2048:
                raise RuntimeError("USB completion order exceeded bounded backlog")
        except Exception as exc:
            self.error = exc
            self.stop.set()
        finally:
            self._callbacks_active -= 1

    def _run(self):
        cancel_sent = False
        stop_started = None
        try:
            for transfer in self._transfers.values():
                if self.stop.is_set():
                    break
                self._submit(transfer)
        except Exception as exc:
            self.error = exc
            self.stop.set()
        while self._pending or self._callbacks_active:
            if self.stop.is_set() and stop_started is None:
                stop_started = time.monotonic()
            # For a healthy streaming endpoint, drain already-submitted INs.
            # This preserves trailing bytes and avoids unnecessary cancellations.
            # Silence/error still needs cancellation; never wait indefinitely.
            should_cancel = (self.stop.is_set() and
                             (self.error is not None or time.monotonic() - stop_started >= 0.15))
            if should_cancel and not cancel_sent:
                cancel_sent = True
                for address in tuple(self._pending):
                    # -5 means that a completion is already pending.
                    result = self.lib.libusb_cancel_transfer(self._transfers[address])
                    if result not in (0, -5):
                        self.error = self.error or OSError(f"libusb_cancel_transfer: {result}")
            timeout = _Timeval(0, 10000)
            result = self.lib.libusb_handle_events_timeout_completed(
                self.backend.ctx, C.byref(timeout), None)
            if result < 0 and result != -10:
                self.error = self.error or OSError(f"libusb events: {result}")
                self.stop.set()
        # Never free a submitted transfer or its buffer before its callback.
        for transfer in self._transfers.values():
            self.lib.libusb_free_transfer(transfer)
        self._transfers.clear()
        self._buffers.clear()

    def get(self):
        try:
            return self.queue.get(timeout=0.050)
        except queue.Empty:
            if self.error:
                raise self.error
            now = time.monotonic_ns()
            return now, now, b"", self.dropped

    def close(self):
        self.stop.set()
        self.thread.join(1.0)
        if self.thread.is_alive():
            raise TimeoutError("USB cancellation has not completed; keep handle and buffers alive")
