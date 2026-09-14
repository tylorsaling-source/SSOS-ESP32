import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('settings_init', ROOT / 'scripts/initialize-settings.py')
INIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INIT)


class SettingsInitializationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.images = Path(self.temp.name)
        for name in ('ssos_kernel.ino.bin', 'ssos_kernel.ino.bootloader.bin', 'boot_app0.bin'):
            (self.images / name).write_bytes(b'test-image')
        self.partition(0x9000, 0x5000)

    def sums(self):
        (self.images / 'SHA256SUMS').write_text(''.join(
            hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n'
            for p in sorted(self.images.glob('*.bin'))))

    def partition(self, offset, size):
        (self.images / 'ssos_kernel.ino.partitions.bin').write_bytes(
            struct.pack('<HBBII16sI', 0x50AA, 1, 2, offset, size, b'nvs', 0) + b'\xff' * 32)
        self.sums()

    def test_exact_nvs_boundary(self):
        self.assertEqual(INIT.settings_region(self.images), (0x9000, 0x5000))
        command = INIT.erase_command('COM20', 460800, 'default-reset', 'hard-reset', False, (0x9000, 0x5000))
        self.assertEqual(command[-3:], ['erase-region', '0x9000', '0x5000'])
        self.assertNotIn('erase-flash', command)

    def test_rejects_changed_images(self):
        (self.images / 'ssos_kernel.ino.bin').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            INIT.settings_region(self.images)

    def test_rejects_layout_drift_even_with_valid_checksums(self):
        for offset, size in ((0, 0x1000000), (0x9000, 0x6000), (0x10000, 0x5000)):
            self.partition(offset, size)
            with self.assertRaisesRegex(ValueError, 'layout'):
                INIT.settings_region(self.images)

    def test_com3_refused_including_alias(self):
        for port in ('COM3', 'com3', '\\\\.\\COM3'):
            with self.assertRaisesRegex(ValueError, 'protected'):
                INIT.erase_command(port, 460800, 'default-reset', 'hard-reset', False, (0x9000, 0x5000))

    def test_validate_only_never_starts_esptool(self):
        with patch.object(sys, 'argv', ['init', '--port', 'COM20', '--validate-only']), \
             patch.object(INIT, 'settings_region', return_value=(0x9000, 0x5000)), \
             patch.object(INIT.subprocess, 'run') as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(INIT.main(), 0)
            run.assert_not_called()

    def test_refused_confirmation_never_starts_esptool(self):
        with patch.object(sys, 'argv', ['init', '--port', 'COM20']), \
             patch.object(INIT, 'settings_region', return_value=(0x9000, 0x5000)), \
             patch('builtins.input', return_value='no'), patch.object(INIT.subprocess, 'run') as run, \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(INIT.main(), 1)
            run.assert_not_called()

    def test_esptool_failure_is_not_reported_as_initialized(self):
        with patch.object(sys, 'argv', ['init', '--port', 'COM20', '--yes']), \
             patch.object(INIT, 'settings_region', return_value=(0x9000, 0x5000)), \
             patch.object(INIT.subprocess, 'run') as run, contextlib.redirect_stdout(io.StringIO()) as output:
            run.return_value.returncode = 2
            self.assertEqual(INIT.main(), 2)
            self.assertNotIn('SETTINGS_INITIALIZED', output.getvalue())


if __name__ == '__main__':
    unittest.main()
