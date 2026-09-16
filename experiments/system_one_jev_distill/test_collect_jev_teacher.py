"""Offline credential-safe failure and partial-result checks; never calls Jev."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import collect_jev_teacher as collector


class CollectorTests(unittest.TestCase):
    def run_collector(self, rows, responses):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        source = Path(directory.name) / "states.jsonl"
        target = Path(directory.name) / "teacher.jsonl"
        source.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
        client = MagicMock()
        client.system_one.side_effect = responses
        manager = MagicMock()
        manager.__enter__.return_value = client
        self.client = client
        with patch.object(collector, "TypeSafeClient", return_value=manager), \
             patch("sys.argv", ["collector", str(source), str(target)]), \
             contextlib.redirect_stdout(io.StringIO()):
            try:
                collector.main()
                error = None
            except SystemExit as exc:
                error = str(exc)
        return target.read_text(encoding="utf-8"), error

    def answer(self, value=0.7):
        return SimpleNamespace(model="offline-mock", nouls={
            name: SimpleNamespace(noul=value) for name in collector.QUESTIONS
        })

    def test_partial_results_survive_without_echoing_error_credentials(self):
        failure = RuntimeError("Bearer TEST_SECRET_MUST_NOT_APPEAR")
        failure.status = 401
        row = {"x8": [0.0] * 8, "state": {"sample_id": 0}}
        output, error = self.run_collector([row, row], [self.answer(), failure])
        self.assertEqual(len(output.splitlines()), 1)
        self.assertEqual(json.loads(output)["targets"], [0.7] * 8)
        self.assertIn("HTTP 401", error)
        self.assertNotIn("TEST_SECRET", error)

    def test_invalid_input_stops_before_api_request(self):
        output, error = self.run_collector([{"x8": [2.0] * 8, "state": {}}], [])
        self.client.system_one.assert_not_called()
        self.assertEqual(output, "")
        self.assertIn("[-1,1]", error)

    def test_invalid_teacher_probability_is_not_saved(self):
        row = {"x8": [0.0] * 8, "state": {}}
        output, error = self.run_collector([row], [self.answer(float("nan"))])
        self.assertEqual(output, "")
        self.assertIn("invalid probability", error)


if __name__ == "__main__":
    unittest.main()
