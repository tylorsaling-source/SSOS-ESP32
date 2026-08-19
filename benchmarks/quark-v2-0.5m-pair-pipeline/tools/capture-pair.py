"""Capture and fail-close five physical two-context pipeline runs."""

import argparse
import json
import statistics
import time
from pathlib import Path

import serial

TARGET_TOK_S = 36.938876


def run(master: str, trials: int) -> dict:
    device = serial.Serial()
    device.port = master
    device.baudrate = 115200
    device.timeout = 0.05
    device.dtr = False
    device.rts = False
    device.open()
    device.dtr = False
    device.rts = False

    runs = []
    try:
        for trial in range(1, trials + 1):
            device.reset_input_buffer()
            device.write(b"RUN\n")
            device.flush()
            streams = []
            result = None
            errors = []
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and result is None:
                line = device.readline().decode("utf-8", "replace").strip()
                if not line.startswith("{"):
                    continue
                event = json.loads(line)
                kind = event.get("event")
                if kind == "quark_pipeline_stream":
                    streams.append(event)
                elif kind == "quark_pipeline_result":
                    result = event
                elif kind == "pipeline_error":
                    errors.append(event)
            if result is None:
                raise TimeoutError(f"trial {trial} timed out")
            runs.append(
                {
                    "trial": trial,
                    "streams": streams,
                    "result": result,
                    "errors": errors,
                }
            )
            print(json.dumps(runs[-1], separators=(",", ":")))
    finally:
        device.close()

    rates = [float(item["result"]["aggregate_tok_s"]) for item in runs]
    passed = (
        len(runs) == trials
        and all(not item["errors"] for item in runs)
        and all(len(item["streams"]) == 2 for item in runs)
        and all(
            stream.get("oracle_match") == "24/24"
            for item in runs
            for stream in item["streams"]
        )
        and all(item["result"].get("oracle_match") == "48/48" for item in runs)
        and all(rate >= TARGET_TOK_S for rate in rates)
    )
    return {
        "master": master,
        "target_tok_s": TARGET_TOK_S,
        "runs": runs,
        "summary": {
            "trials": len(runs),
            "min_tok_s": min(rates),
            "median_tok_s": statistics.median(rates),
            "max_tok_s": max(rates),
            "passed": passed,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", required=True)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run(args.master, args.trials)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    raise SystemExit(0 if payload["summary"]["passed"] else 1)


if __name__ == "__main__":
    main()
