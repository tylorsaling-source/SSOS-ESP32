#!/usr/bin/env python3
"""Interpret the existing SSOS V2 MINFER output as eight System-One probabilities."""
from __future__ import annotations

import argparse
import json
import math

QUESTIONS = [
    "route_fast_path", "persist_state", "prefetch_context", "wake_worker",
    "retry_transport", "request_more_state", "state_anomalous", "fallback_deterministic",
]


def sigmoid(v: float) -> float:
    if v >= 0:
        e = math.exp(-v)
        return 1.0 / (1.0 + e)
    e = math.exp(v)
    return e / (1.0 + e)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("x", nargs=8, type=float, help="eight normalized features in [-1,1]")
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    args = ap.parse_args()

    try:
        import serial
    except ImportError as exc:
        raise SystemExit("serial use requires: python -m pip install pyserial") from exc

    x9 = args.x + [1.0]
    cmd = "MINFER x=" + ",".join(format(v, ".9g") for v in x9) + "\n"
    with serial.Serial(args.port, args.baud, timeout=3, write_timeout=3, dsrdtr=False, rtscts=False) as dev:
        dev.dtr = False
        dev.rts = False
        dev.reset_input_buffer()
        dev.write(cmd.encode("ascii"))
        dev.flush()
        line = dev.readline().decode("ascii", errors="replace").strip()
    if not line.startswith("OK model y8="):
        raise SystemExit(f"device inference failed: {line or 'no response'}")
    raw = line.split("y8=", 1)[1].split()[0]
    logits = [float(v) for v in raw.split(",")]
    if len(logits) != 8:
        raise SystemExit(f"expected 8 logits, got {len(logits)}")
    probs = [sigmoid(v) for v in logits]
    print(json.dumps({
        "x9": x9,
        "decisions": {
            name: {"logit": logits[i], "probability": probs[i], "active": probs[i] >= 0.5}
            for i, name in enumerate(QUESTIONS)
        }
    }, indent=2))


if __name__ == "__main__":
    main()
