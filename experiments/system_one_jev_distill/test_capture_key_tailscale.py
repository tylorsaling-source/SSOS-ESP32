"""Loopback-only HTTP tests using invented credentials and identities."""
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest

from capture_key_tailscale import CaptureServer, store_key


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.saved = []
        self.server = CaptureServer(("127.0.0.1", 0), "https://test.example:8447",
                                    "test@example.com", "test-token", time.monotonic() + 60,
                                    self.saved.append)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method="POST", path="/capture", override=None, body=None):
        headers = {"Host": "test.example:8447", "Tailscale-User-Login": "test@example.com",
                   "Origin": "https://test.example:8447", "X-Capture-Token": "test-token",
                   "Content-Type": "application/json"}
        headers.update(override or {})
        for key in list(headers):
            if headers[key] is None:
                del headers[key]
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        connection.request(method, path, body=json.dumps({"key": "offline-test-secret"}) if body is None else body,
                           headers=headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_exactly_one_save_and_no_secret_echo(self):
        status, headers, body = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(self.saved, ["offline-test-secret"])
        self.assertNotIn(b"offline-test-secret", body)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.request()[0], 410)
        self.assertEqual(len(self.saved), 1)

    def test_identity_host_origin_and_token_are_required(self):
        for override in ({"Tailscale-User-Login": None}, {"Tailscale-User-Login": "other@example.com"},
                         {"Host": "evil.example"}, {"Origin": "https://evil.example"},
                         {"X-Capture-Token": "wrong"}):
            with self.subTest(override=override):
                self.assertEqual(self.request(override=override)[0], 403)
        self.assertEqual(self.saved, [])

    def test_expiry_and_payload_bounds(self):
        self.assertEqual(self.request(body="x" * 8193)[0], 413)
        self.assertEqual(self.request(body='{"key":"bad\\nkey"}')[0], 400)
        self.server.deadline = time.monotonic() - 1
        self.assertEqual(self.request()[0], 410)
        self.assertEqual(self.saved, [])

    def test_password_form_and_script_have_no_external_dependencies(self):
        status, headers, body = self.request("GET", "/", body="")
        self.assertEqual(status, 200)
        self.assertIn(b'type="password"', body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn(b"test-token", body)
        self.assertEqual(self.request("GET", "/app.js", body="")[0], 200)

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI required")
    def test_stdin_storage_is_encrypted_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "credential" / "test.dpapi"
            store_key("offline-test-secret", target)
            encrypted = target.read_text()
            self.assertNotIn("offline-test-secret", encrypted)
            self.assertGreater(len(encrypted), 100)
            with self.assertRaises(RuntimeError):
                store_key("replacement-test-secret", target)
            self.assertEqual(target.read_text(), encrypted)


if __name__ == "__main__":
    unittest.main()
