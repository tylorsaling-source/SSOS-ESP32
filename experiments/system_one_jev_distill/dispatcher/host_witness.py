"""Read-only host responsiveness and boot identity; contains no power controls."""
import hashlib
import json
import os
import subprocess
from pathlib import Path
from worker import machine_fingerprint


def witness():
    if os.name == 'nt':
        result = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
            "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')"],
            capture_output=True, text=True, timeout=15)
        if result.returncode or not result.stdout.strip():
            raise RuntimeError('Cannot read host boot identity')
        boot = result.stdout.strip().encode()
    else:
        boot = Path('/proc/sys/kernel/random/boot_id').read_bytes().strip()
    return {'ok': True, 'boot_id': hashlib.sha256(boot).hexdigest(),
            'machine_fingerprint': machine_fingerprint()}


if __name__ == '__main__':
    print(json.dumps(witness()), flush=True)
