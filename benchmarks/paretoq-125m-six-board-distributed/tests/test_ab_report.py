import json
from pathlib import Path

import pytest

from tools.generate_ab_report import PROMPT_IDS, build_report


def make_package(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "results" / "host").mkdir(parents=True)
    (tmp_path / "results" / "physical").mkdir(parents=True)
    (tmp_path / "prebuilt" / "compute").mkdir(parents=True)
    prompts = {"decode": {"method": "greedy"},
               "prompts": [{"id": item, "text": f"input {item}"} for item in PROMPT_IDS]}
    oracle_results = [{"id": item, "output_ids": list(range(24)),
                       "output_text": f"output {item}"} for item in PROMPT_IDS]
    oracle = {"model_id": "model", "model_revision": "revision",
              "source": {"checkpoint_sha256": "a" * 64}, "results": oracle_results}
    records = []
    raw = []
    for mode, multiplier in (("fast", 1), ("regular", 2)):
        for item in PROMPT_IDS:
            records.append({"prompt": item, "mode": mode, "output_ids": list(range(24)),
                            "exact": True, "tokens": 24, "ttft_ms": 10.0 * multiplier,
                            "prompt_to_finish_ms": 100.0 * multiplier,
                            "decode_tps": 1.0 / multiplier, "spi_errors": 0})
        raw.append(f"BENCH_DONE mode={mode} prompts=5 all_exact=1")
    (tmp_path / "config" / "proof_prompts.json").write_text(json.dumps(prompts))
    (tmp_path / "results" / "host" / "oracle.json").write_text(json.dumps(oracle))
    (tmp_path / "results" / "physical" / "ab_proof.json").write_text(
        json.dumps({"records": records, "raw": raw}))
    (tmp_path / "prebuilt" / "compute" / "application.bin").write_bytes(b"app")
    return tmp_path


def test_report_requires_and_compares_both_modes(tmp_path):
    package = make_package(tmp_path)
    report, summary = build_report(package)
    assert "120/120" in report
    assert "2.000x" in report
    assert summary["all_exact"] is True


def test_report_rejects_one_token_mismatch(tmp_path):
    package = make_package(tmp_path)
    proof = package / "results" / "physical" / "ab_proof.json"
    data = json.loads(proof.read_text())
    data["records"][0]["output_ids"][0] = 999
    proof.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="differs from oracle"):
        build_report(package)
