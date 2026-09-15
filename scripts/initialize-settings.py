#!/usr/bin/env python3
"""Explicit, bounded initialization of the NVS partition in this release."""

import argparse
import hashlib
from pathlib import Path
import struct
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def settings_region(image_dir: Path) -> tuple[int, int]:
    """Require intact release images and the exact documented settings layout."""
    checksums = {}
    for line in (image_dir / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split()
        checksums[name.lstrip('*')] = digest.lower()
    for name in ('ssos_kernel.ino.bin', 'ssos_kernel.ino.bootloader.bin',
                 'ssos_kernel.ino.partitions.bin', 'boot_app0.bin'):
        actual = hashlib.sha256((image_dir / name).read_bytes()).hexdigest()
        if actual != checksums.get(name):
            raise ValueError(f'release checksum mismatch: {name}')
    data = (image_dir / 'ssos_kernel.ino.partitions.bin').read_bytes()
    partitions = []
    for offset in range(0, len(data) - 31, 32):
        magic, kind, subtype, start, size, label, flags = struct.unpack_from('<HBBII16sI', data, offset)
        if magic != 0x50AA:
            break
        partitions.append((kind, subtype, start, size, label.rstrip(b'\0'), flags))
    nvs = [p for p in partitions if p[4] == b'nvs']
    if len(nvs) != 1 or nvs[0] != (1, 2, 0x9000, 0x5000, b'nvs', 0):
        raise ValueError('unsupported NVS layout; refusing to erase')
    for p in partitions:
        if p != nvs[0] and max(p[2], 0x9000) < min(p[2] + p[3], 0xE000):
            raise ValueError('overlapping NVS partition; refusing to erase')
    return nvs[0][2], nvs[0][3]


def erase_command(port: str, baud: int, before: str, after: str, no_stub: bool, region: tuple[int, int]) -> list[str]:
    if port.upper().removeprefix('\\\\.\\') == 'COM3':
        raise ValueError('COM3 is protected; it will never be opened or flashed')
    command = [sys.executable, '-m', 'esptool', '--chip', 'esp32s3', '--port', port,
               '--baud', str(baud), '--before', before, '--after', after]
    if no_stub:
        command.append('--no-stub')
    return command + ['erase-region', hex(region[0]), hex(region[1])]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port')
    parser.add_argument('--baud', type=int, default=460800)
    parser.add_argument('--before', choices=('default-reset', 'no-reset'), default='default-reset')
    parser.add_argument('--after', choices=('hard-reset', 'no-reset'), default='hard-reset')
    parser.add_argument('--no-stub', action='store_true')
    parser.add_argument('--yes', action='store_true')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    try:
        region = settings_region(ROOT / 'images/flash')
        command = erase_command(args.port or '<selected-port>', args.baud, args.before, args.after, args.no_stub, region)
        print('Initialize leftover settings: clear only NVS at 0x9000, length 0x5000 (20 KiB).', flush=True)
        print('This discards saved settings/model rows so the new V2 install can save reliably.', flush=True)
        if args.validate_only:
            print('Validated release images and bounded NVS layout; no device opened or changed.')
            print('Planned command: ' + ' '.join(command))
            return 0
        if not args.port:
            raise ValueError('--port is required')
        if not args.yes and input(f'Type INITIALIZE {args.port} to continue: ') != f'INITIALIZE {args.port}':
            raise ValueError('confirmation did not match; nothing was erased')
        print('HOST ' + ' '.join(command), flush=True)
        result = subprocess.run(command, check=False)
        if result.returncode:
            return result.returncode
        print('SETTINGS_INITIALIZED offset=0x9000 length=0x5000 reason=explicit-release-install', flush=True)
        return 0
    except (OSError, ValueError) as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
