#!/usr/bin/env python3
"""Build the focused V2 ZIP from an immutable Git commit, with per-file hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = ('firmware/ssos_kernel/', 'images/flash/', 'host/', 'scripts/',
            'models/basic_surv_esp4/', 'validation/v2-hardware/')
ROOT_FILES = {'LICENSE', 'NOTICE', 'CONTRIBUTING.md', 'SECURITY.md', 'GOVERNANCE.md',
              'CODE_OF_CONDUCT.md', 'arduino-cli.yaml', 'build.sh', 'flash.sh', 'ssos',
              'docs/PROTOCOL.md', 'docs/FLASHING.md', 'docs/USE_CASES.md'}


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    commit = git('rev-parse', args.ref + '^{commit}').decode().strip()
    version = git('show', commit + ':images/flash/RELEASE_VERSION').decode().strip()
    if version != '2.0.1':
        raise SystemExit('This packager targets V2.0.1 only')
    paths = git('ls-tree', '-r', '--name-only', commit).decode().splitlines()
    payload = {p: git('show', commit + ':' + p) for p in paths if p in ROOT_FILES or p.startswith(PREFIXES)}
    payload['README.md'] = git('show', commit + ':packaging/v2/README.md')
    payload['RELEASE_NOTES.md'] = git('show', commit + ':packaging/v2/RELEASE_NOTES.md')
    payload['VERSION'] = (version + '\n').encode()
    payload['PACKAGE.json'] = (json.dumps({'payload': 'SSOS-ESP32 fixed 9-input/8-output packet-backed head',
        'version': version, 'source_commit': commit, 'settings_initialization': 'default in Windows proof; explicit in flash-only installers',
        'excluded_payloads': ['Quark', 'ParetoQ', 'V3', 'V4']}, indent=2) + '\n').encode()
    payload['SHA256SUMS'] = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n'
        for name, data in sorted(payload.items())).encode()
    args.output.mkdir(parents=True, exist_ok=True)
    archive = args.output / f'SSOS_ESP32-v{version}-packet-model-bridge-release.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 14, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if name.endswith('.sh') or name == 'ssos' else 0o100644) << 16
            target.writestr(info, data)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (args.output / 'SSOS_ESP32-v2.0.1-SHA256SUMS.txt').write_text(digest + '  ' + archive.name + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'archive': str(archive), 'sha256': digest, 'files': len(payload), 'source_commit': commit}, indent=2))


if __name__ == '__main__':
    main()
