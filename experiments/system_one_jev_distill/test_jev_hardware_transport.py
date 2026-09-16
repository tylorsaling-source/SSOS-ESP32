"""Verify fragmented serial responses are not mistaken for complete scores."""
import unittest
from unittest.mock import MagicMock

from validate_jev_hardware import Device


class SerialFramingTests(unittest.TestCase):
    def test_retries_only_read_only_inference(self):
        device = Device.__new__(Device)
        device.transcript = MagicMock()
        device.device = MagicMock()
        device._command_once = MagicMock(side_effect=[TimeoutError(), "complete"])
        self.assertEqual(device.command("MINFER x=test", lambda _: True), "complete")
        self.assertEqual(device.retry_count, 1)
        device._command_once = MagicMock(side_effect=TimeoutError())
        with self.assertRaises(TimeoutError):
            device.command("SAVE", lambda _: True)
        self.assertEqual(device._command_once.call_count, 1)

    def test_split_response_waits_for_newline(self):
        device = Device.__new__(Device)
        device.timeout = 1
        device.transcript = MagicMock()
        device.device = MagicMock()
        device.device.readline.side_effect = [b"OK model y8=1,2,", b"", b"3,4,5,6,7,8 argmax=7\n"]
        line = device.command("MINFER x=test", lambda value: value.startswith("OK model y8="))
        self.assertEqual(line, "OK model y8=1,2,3,4,5,6,7,8 argmax=7")
        self.assertEqual(device.device.readline.call_count, 3)


if __name__ == "__main__":
    unittest.main()
