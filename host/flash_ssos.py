#!/data/data/com.termux/files/usr/bin/python3
"""Flash SSOS-S3 over Termux USB CDC (no /dev/tty)."""
import os
import sys
import time
import ctypes
import ctypes.util
from types import SimpleNamespace

# pyserial on Android cannot list ports; stub it before esptool imports.
import serial  # noqa: F401
import types

_tools = types.ModuleType("serial.tools")
_lp = types.ModuleType("serial.tools.list_ports")
_lp.comports = lambda *a, **k: []
_tools.list_ports = _lp
serial.tools = _tools
sys.modules["serial.tools"] = _tools
sys.modules["serial.tools.list_ports"] = _lp

from esptool.cmds import detect_chip, write_flash  # noqa: E402

LIBUSB = ctypes.CDLL("/data/data/com.termux/files/usr/lib/libusb-1.0.so")
LIBUSB_OPTION_NO_DEVICE_DISCOVERY = 2
EP_IN, EP_OUT = 0x81, 0x01


class InitOption(ctypes.Structure):
    _fields_ = [("option", ctypes.c_int), ("value", ctypes.c_uint64)]


LIBUSB.libusb_init_context.argtypes = [
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.POINTER(InitOption),
    ctypes.c_int,
]
LIBUSB.libusb_wrap_sys_device.argtypes = [
    ctypes.c_void_p,
    ctypes.c_long,
    ctypes.POINTER(ctypes.c_void_p),
]
LIBUSB.libusb_bulk_transfer.argtypes = [
    ctypes.c_void_p,
    ctypes.c_uint8,
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_int),
    ctypes.c_uint,
]
LIBUSB.libusb_control_transfer.argtypes = [
    ctypes.c_void_p,
    ctypes.c_uint8,
    ctypes.c_uint8,
    ctypes.c_uint16,
    ctypes.c_uint16,
    ctypes.c_void_p,
    ctypes.c_uint16,
    ctypes.c_uint,
]
LIBUSB.libusb_claim_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
LIBUSB.libusb_detach_kernel_driver.argtypes = [ctypes.c_void_p, ctypes.c_int]
LIBUSB.libusb_kernel_driver_active.argtypes = [ctypes.c_void_p, ctypes.c_int]


class UsbSerial:
    def __init__(self, fd):
        self.port = "usbcdc"
        self.name = "usbcdc"
        self._dtr = False
        self._rts = False
        self.timeout = 0.2
        self.baudrate = 115200
        self._buf = bytearray()
        self._open = False
        self._fd = fd
        self._ctx = ctypes.c_void_p()
        self._h = ctypes.c_void_p()
        opts = (InitOption * 1)()
        opts[0].option = LIBUSB_OPTION_NO_DEVICE_DISCOVERY
        r = LIBUSB.libusb_init_context(ctypes.byref(self._ctx), opts, 1)
        if r:
            raise IOError(f"libusb_init_context {r}")
        r = LIBUSB.libusb_wrap_sys_device(self._ctx, fd, ctypes.byref(self._h))
        if r:
            raise IOError(f"libusb_wrap_sys_device {r}")
        for iface in (0, 1):
            if LIBUSB.libusb_kernel_driver_active(self._h, iface) == 1:
                LIBUSB.libusb_detach_kernel_driver(self._h, iface)
            LIBUSB.libusb_claim_interface(self._h, iface)
        coding = (ctypes.c_uint8 * 7)(0x00, 0xC2, 0x01, 0x00, 0, 0, 8)
        LIBUSB.libusb_control_transfer(self._h, 0x21, 0x20, 0, 0, coding, 7, 500)
        self._apply_lines()
        self._open = True

    def isOpen(self):
        return self._open

    def open(self):
        self._open = True

    def close(self):
        self._open = False

    def fileno(self):
        return -1

    def _apply_lines(self):
        val = (1 if self._dtr else 0) | ((1 if self._rts else 0) << 1)
        LIBUSB.libusb_control_transfer(self._h, 0x21, 0x22, val, 0, None, 0, 500)

    def setDTR(self, state):
        self._dtr = bool(state)
        self._apply_lines()

    def setRTS(self, state):
        self._rts = bool(state)
        self._apply_lines()

    @property
    def dtr(self):
        return self._dtr

    @dtr.setter
    def dtr(self, state):
        self.setDTR(state)

    @property
    def rts(self):
        return self._rts

    @rts.setter
    def rts(self, state):
        self.setRTS(state)

    def _pull(self, timeout_ms):
        buf = (ctypes.c_uint8 * 256)()
        xfer = ctypes.c_int(0)
        r = LIBUSB.libusb_bulk_transfer(
            self._h, EP_IN, buf, 256, ctypes.byref(xfer), timeout_ms
        )
        if r == 0 and xfer.value > 0:
            self._buf.extend(bytes(buf[: xfer.value]))
        elif r not in (0, -7):
            print(f"usb bulk IN err={r} xfer={xfer.value}", file=sys.stderr, flush=True)

    def read(self, size=1):
        if size <= 0:
            return b""
        timeout = 30.0 if self.timeout is None else max(float(self.timeout), 0.05)
        deadline = time.time() + timeout
        while len(self._buf) < size and time.time() < deadline:
            remain = max(5, int((deadline - time.time()) * 1000))
            self._pull(min(remain, 250))
        n = min(size, len(self._buf))
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out

    def write(self, data):
        raw = bytes(data)
        sent = 0
        while sent < len(raw):
            chunk = raw[sent : sent + 64]
            buf = (ctypes.c_uint8 * len(chunk)).from_buffer_copy(chunk)
            xfer = ctypes.c_int(0)
            r = LIBUSB.libusb_bulk_transfer(
                self._h, EP_OUT, buf, len(chunk), ctypes.byref(xfer), 1000
            )
            if r != 0:
                print(f"usb bulk OUT err={r}", file=sys.stderr, flush=True)
                break
            if xfer.value <= 0:
                break
            sent += xfer.value
        return sent

    def flush(self):
        pass

    def flushInput(self):
        self._buf.clear()
        self._pull(20)

    def flushOutput(self):
        pass

    def reset_input_buffer(self):
        self.flushInput()

    def reset_output_buffer(self):
        self.flushOutput()

    @property
    def in_waiting(self):
        self._pull(1)
        return len(self._buf)

    def inWaiting(self):
        return self.in_waiting


def main():
    fd = None
    for a in sys.argv[1:]:
        if a.isdigit():
            fd = int(a)
    if fd is None:
        print("flash_ssos: no USB fd (run via termux-usb -e)", file=sys.stderr)
        return 2

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    build = os.path.join(root, "firmware", "build")
    files = [
        (0x0, os.path.join(build, "ssos_kernel.ino.bootloader.bin")),
        (0x8000, os.path.join(build, "ssos_kernel.ino.partitions.bin")),
        (0x10000, os.path.join(build, "ssos_kernel.ino.bin")),
    ]
    for _, path in files:
        if not os.path.isfile(path):
            print("missing", path, file=sys.stderr)
            return 3

    print("Opening USB CDC fd", fd)
    port = UsbSerial(fd)
    print("Connecting...")
    esp = None
    last = None
    for mode in ("usb_reset", "no_reset"):
        try:
            print("  mode", mode)
            esp = detect_chip(port, baud=115200, connect_mode=mode, connect_attempts=7)
            break
        except Exception as e:
            last = e
            print("  failed:", e)
            port.flushInput()
    if esp is None:
        raise last
    print("Chip:", esp.CHIP_NAME, "stub_already=", getattr(esp, "IS_STUB", False), flush=True)
    if not getattr(esp, "IS_STUB", False):
        print("Uploading stub...", flush=True)
        try:
            esp = esp.run_stub()
            time.sleep(0.3)
            port.flushInput()
            print("Stub running", flush=True)
        except Exception as e:
            print("Stub failed, staying in ROM:", e, flush=True)
    print("Attaching SPI flash...", flush=True)
    esp.flash_spi_attach(0)
    esp.flash_set_parameters(4 * 1024 * 1024)
    print("Writing flash...", flush=True)
    block = esp.FLASH_WRITE_SIZE
    for addr, path in files:
        data = open(path, "rb").read()
        pad = (-len(data)) % block
        if pad:
            data = data + b"\xff" * pad
        nblocks = len(data) // block
        print(f"  {path} -> 0x{addr:x} ({len(data)} bytes, {nblocks} blocks)", flush=True)
        esp.flash_begin(len(data), addr)
        for seq in range(nblocks):
            chunk = data[seq * block : (seq + 1) * block]
            try:
                esp.flash_block(chunk, seq)
            except (StopIteration, Exception) as e:
                print(f"    retry seq {seq}: {e}", flush=True)
                esp.flush_input()
                time.sleep(0.05)
                esp.flash_block(chunk, seq)
            if seq % 8 == 0 or seq + 1 == nblocks:
                print(f"    {seq + 1}/{nblocks}", flush=True)
        print("    ok", flush=True)
    print("Leaving flash mode...")
    try:
        esp.flash_finish(False)
    except Exception as e:
        print("  flash_finish:", e)
    try:
        esp.hard_reset()
    except Exception as e:
        print("  hard_reset:", e)
    print("SSOS-S3 flash done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
