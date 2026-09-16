"""Bounded experiment worker: JSON stdin/stdout, existing SSH authentication.

No listening socket, arbitrary commands, shutdown operation or administrator access.
Only this worker's dedicated scratch directory is affected by fault injection.
"""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
import time
import uuid

MAX_ITEMS = 1_048_576
PTX = b'''.version 6.0
.target sm_52
.address_size 64
.visible .entry transform(.param .u64 outptr, .param .u32 count) {
 .reg .pred p;
 .reg .b32 r<7>;
 .reg .b64 d<4>;
 ld.param.u64 d1, [outptr];
 ld.param.u32 r1, [count];
 mov.u32 r2, %ctaid.x;
 mov.u32 r3, %ntid.x;
 mov.u32 r4, %tid.x;
 mad.lo.s32 r0, r2, r3, r4;
 setp.ge.u32 p, r0, r1;
 @p bra DONE;
 mul.lo.u32 r5, r0, 1664525;
 add.u32 r6, r5, 1013904223;
 mul.wide.u32 d2, r0, 4;
 add.s64 d3, d1, d2;
 st.global.u32 [d3], r6;
DONE: ret;
}
'''

class Cuda:
    def __init__(self):
        self.lib = C.WinDLL('nvcuda.dll') if os.name == 'nt' else C.CDLL('libcuda.so.1')
        self.call('cuInit', [C.c_uint], 0)
        self.device = C.c_int()
        self.call('cuDeviceGet', [C.POINTER(C.c_int), C.c_int], C.byref(self.device), 0)

    def call(self, name, types, *args):
        fn = getattr(self.lib, name)
        fn.argtypes, fn.restype = types, C.c_int
        code = fn(*args)
        if code:
            raise RuntimeError('CUDA ' + name + ' error ' + str(code))

    def transform(self, n):
        ptr = C.c_void_p
        context, module, function = ptr(), ptr(), ptr()
        allocation = C.c_uint64()
        self.call('cuCtxCreate_v2', [C.POINTER(ptr), C.c_uint, C.c_int], C.byref(context), 0, self.device)
        try:
            self.call('cuModuleLoadData', [C.POINTER(ptr), ptr], C.byref(module), C.cast(C.c_char_p(PTX), ptr))
            self.call('cuModuleGetFunction', [C.POINTER(ptr), ptr, C.c_char_p], C.byref(function), module, b'transform')
            self.call('cuMemAlloc_v2', [C.POINTER(C.c_uint64), C.c_size_t], C.byref(allocation), n*4)
            count = C.c_uint(n)
            params = (ptr*2)(C.cast(C.byref(allocation), ptr), C.cast(C.byref(count), ptr))
            self.call('cuLaunchKernel', [ptr]+[C.c_uint]*7+[ptr,C.POINTER(ptr),C.POINTER(ptr)],
                      function, (n+255)//256, 1, 1, 256, 1, 1, 0, None, params, None)
            self.call('cuCtxSynchronize', [])
            result = C.create_string_buffer(n*4)
            self.call('cuMemcpyDtoH_v2', [ptr,C.c_uint64,C.c_size_t], result, allocation, n*4)
            return result.raw
        finally:
            if allocation.value:
                self.call('cuMemFree_v2', [C.c_uint64], allocation)
            self.call('cuCtxDestroy_v2', [ptr], context)

def cpu_transform(n):
    return b''.join(struct.pack('<I', (i*1664525+1013904223)&0xffffffff) for i in range(n))

def machine_fingerprint():
    # Stable machine identity, hashed before leaving the worker. Kept in private evidence.
    if os.name == 'nt':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography') as key:
            identity = winreg.QueryValueEx(key, 'MachineGuid')[0]
    else:
        identity = Path('/etc/machine-id').read_text().strip()
    if not identity:
        raise RuntimeError('Missing machine identity')
    return hashlib.sha256(identity.encode()).hexdigest()

def receipt(data, kernel, n, elapsed):
    return dict(ok=True, kernel=kernel, count=n, sha256=hashlib.sha256(data).hexdigest(),
                elapsed_ms=elapsed*1000, process_id=os.getpid())

def active(path):
    try:
        return json.loads(path.read_text()).get('until', 0) > time.time()
    except (FileNotFoundError, ValueError):
        return False

def handle(request, directory):
    action = request.get('action')
    lease, unavailable = directory/'busy.json', directory/'unavailable.json'
    # Time-limited faults affect ONLY this experiment worker, never machine networking.
    if action in ('busy', 'unavailable'):
        seconds = int(request.get('seconds', 30))
        if not 1 <= seconds <= 300:
            raise ValueError('Fault duration must be 1..300 seconds')
        path = lease if action == 'busy' else unavailable
        with path.open('w') as out:
            json.dump({'until': time.time()+seconds}, out)
        if action == 'busy':
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--directory', str(directory), '--hold'],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return {'ok': True, 'fault': action, 'seconds': seconds}
    if action == 'clear':
        lease.unlink(missing_ok=True)
        unavailable.unlink(missing_ok=True)
        return {'ok': True}
    if active(unavailable):
        return {'ok': False, 'error': 'experiment_worker_unavailable'}
    if action == 'probe':
        gpu = False
        try:
            Cuda()
            gpu = True
        except (OSError, RuntimeError, AttributeError):
            pass
        identity_path = directory/'worker-id.txt'
        if not identity_path.exists():
            identity_path.write_text(str(uuid.uuid4()))
        return dict(ok=True, worker_id=identity_path.read_text(), machine=platform.machine(),
                    os=platform.system(), machine_fingerprint=machine_fingerprint(),
                    capabilities=['cpu']+(['cuda'] if gpu else []),
                    free_capacity=0.0 if active(lease) else 1.0, timestamp=time.time())
    if action != 'execute':
        raise ValueError('Unknown action')
    if active(lease):
        return {'ok': False, 'error': 'experiment_worker_busy'}
    n, kernel = request.get('count'), request.get('kernel')
    if type(n) is not int or not 1 <= n <= MAX_ITEMS or kernel not in ('cpu', 'cuda'):
        raise ValueError('Unsupported bounded kernel request')
    started = time.monotonic()
    data = Cuda().transform(n) if kernel == 'cuda' else cpu_transform(n)
    return receipt(data, kernel, n, time.monotonic()-started)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--hold', action='store_true')
    args = p.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    if args.hold:
        while active(args.directory/'busy.json'):
            cpu_transform(4096)
            time.sleep(.02)
        return
    try:
        request = json.loads(sys.stdin.readline(8192))
        result = handle(request, args.directory)
    except Exception as exc:
        result = {'ok': False, 'error': type(exc).__name__}
    print(json.dumps(result), flush=True)

if __name__ == '__main__':
    main()
