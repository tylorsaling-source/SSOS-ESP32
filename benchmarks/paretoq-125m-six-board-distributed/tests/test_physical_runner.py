import json
from pathlib import Path

from tools.run_physical_benchmark import (
    completed_only_capture,
    completed_modes,
    load_capture,
    validate_capture,
    write_capture,
)


def make_mode(mode: str) -> tuple[list[dict], list[str]]:
    records = []
    for number in range(1, 6):
        records.append({
            "prompt": f"p{number:02d}",
            "mode": mode,
            "exact": True,
            "tokens": 24,
            "spi_errors": 0,
            "ttft_ms": 1.0,
            "prompt_to_finish_ms": 2.0,
            "decode_tps": 3.0,
        })
    return records, [f"BENCH_DONE mode={mode} prompts=5 all_exact=1"]


def test_capture_checkpoint_round_trip(tmp_path: Path):
    records, raw = make_mode("fast")
    output = tmp_path / "capture.json"
    write_capture(output, records, raw, complete=False,
                  requested_modes=("FAST", "REGULAR"))
    loaded_records, loaded_raw = load_capture(output)
    assert loaded_records == records
    assert loaded_raw == raw
    assert json.loads(output.read_text())["complete"] is False
    assert not output.with_suffix(".json.tmp").exists()


def test_completed_mode_can_be_validated_and_resumed():
    records, raw = make_mode("fast")
    assert completed_modes(raw) == {"fast"}
    validate_capture(records, raw, ("FAST",))


def test_resume_discards_interrupted_mode_records():
    fast_records, fast_raw = make_mode("fast")
    partial_regular = dict(fast_records[0], mode="regular")
    records, raw = completed_only_capture(
        fast_records + [partial_regular],
        [json.dumps(partial_regular)] + fast_raw,
    )
    assert records == fast_records
    assert raw == fast_raw
