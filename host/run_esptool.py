import sys
import types
import fcntl
import serial

_orig_flock = fcntl.flock
_orig_ioctl = fcntl.ioctl

def _flock(fd, op):
    try:
        return _orig_flock(fd, op)
    except OSError:
        return None

def _ioctl(fd, op, *args, **kwargs):
    try:
        return _orig_ioctl(fd, op, *args, **kwargs)
    except OSError as e:
        if e.errno in (13, 25):
            return 0
        raise

fcntl.flock = _flock
fcntl.ioctl = _ioctl

tools = types.ModuleType("serial.tools")
tools.__path__ = []
lp = types.ModuleType("serial.tools.list_ports")
lp.comports = lambda *a, **k: []
tools.list_ports = lp
lpc = types.ModuleType("serial.tools.list_ports_common")

class ListPortInfo:
    def __init__(self, device=None, **kwargs):
        self.device = device
        self.description = ""
        self.hwid = ""
        self.vid = None
        self.pid = None
        self.serial_number = None
        self.location = None
        self.manufacturer = None
        self.product = None
        self.interface = None

lpc.ListPortInfo = ListPortInfo
tools.list_ports_common = lpc
serial.tools = tools
sys.modules["serial.tools"] = tools
sys.modules["serial.tools.list_ports"] = lp
sys.modules["serial.tools.list_ports_common"] = lpc

_orig_url = serial.serial_for_url

def _serial_for_url(*args, **kwargs):
    kwargs["exclusive"] = False
    return _orig_url(*args, **kwargs)

serial.serial_for_url = _serial_for_url

import esptool

if __name__ == "__main__":
    esptool.main(sys.argv[1:])
