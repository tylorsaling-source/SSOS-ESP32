import importlib.util
import json
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("validate_v2_hardware", HERE / "validate_v2_hardware.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class HardwareFixtureTests(unittest.TestCase):
    def test_fixture_is_self_consistent(self):
        fixture = MODULE.load_fixture(HERE / "fixture.json")
        self.assertEqual(len(fixture["rows_q10"]), 8)
        self.assertEqual(len(fixture["vectors"]), 3)

    def test_all_72_values_match_published_model_q10(self):
        fixture = MODULE.load_fixture(HERE / "fixture.json")
        model_path = HERE.parents[1] / "models" / "basic_surv_esp4" / "ssos_head_rows.json"
        model = json.loads(model_path.read_text(encoding="utf-8"))
        quantized = [[round(float(value) * 1024.0) for value in row] for row in model["rows"]]
        self.assertEqual(fixture["rows_q10"], quantized)

    def test_inference_parser_requires_eight_outputs(self):
        values, argmax = MODULE.parse_inference("OK model y8=1,2,3,4,5,6,7,8 argmax=7")
        self.assertEqual(values, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        self.assertEqual(argmax, 7)
        with self.assertRaises(ValueError):
            MODULE.parse_inference("OK model y8=1,2 argmax=1")


if __name__ == "__main__":
    unittest.main()
