from __future__ import annotations

import os
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "host-reference" / "quality-latest.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-step", type=int, required=True)
    parser.add_argument("--interval", type=int, default=10_000)
    parser.add_argument("--start-step", type=int)
    args = parser.parse_args()
    milestone = args.interval if args.start_step is None else args.start_step
    while milestone <= args.target_step:
        checkpoint = ROOT / "checkpoints" / f"step-{milestone:08d}.pt"
        while not checkpoint.exists():
            time.sleep(5)
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "quality_gate.py"), str(checkpoint), "--tokens", "80"],
            check=True,
            capture_output=True,
            text=True,
        )
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        history = OUTPUT.parent / f"quality-step-{milestone:08d}.json"
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=OUTPUT.parent, delete=False) as handle:
            handle.write(result.stdout)
            temp = Path(handle.name)
        os.replace(temp, history)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=OUTPUT.parent, delete=False) as handle:
            handle.write(result.stdout)
            latest_temp = Path(handle.name)
        os.replace(latest_temp, OUTPUT)
        milestone += args.interval
    if args.target_step % args.interval:
        checkpoint = ROOT / "checkpoints" / f"step-{args.target_step:08d}.pt"
        while not checkpoint.exists():
            time.sleep(5)
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "quality_gate.py"), str(checkpoint), "--tokens", "80"], check=True, capture_output=True, text=True)
        OUTPUT.write_text(result.stdout, encoding="utf-8")


if __name__ == "__main__":
    main()
