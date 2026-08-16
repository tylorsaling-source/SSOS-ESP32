#!/usr/bin/env python3
"""Project a basic_surv observation into SSOS 9-D and optionally infer on-device."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("observation", help="JSON file containing exactly 48 ordered floats, or - for stdin")
    parser.add_argument(
        "--model",
        type=Path,
        default=root / "models" / "basic_surv_esp4" / "basic_surv_esp4_ssos_9d.npz",
    )
    parser.add_argument("--port", help="optional serial port such as COM4 or /dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    text = sys.stdin.read() if args.observation == "-" else Path(args.observation).read_text(encoding="utf-8")
    observation = np.asarray(json.loads(text), dtype=np.float32)
    if observation.shape != (48,) or not np.isfinite(observation).all():
        raise SystemExit("observation must be a JSON array of exactly 48 finite numbers")

    artifact = np.load(args.model, allow_pickle=False)
    projection_weight = artifact["projection_weight"].astype(np.float32)
    projection_bias = artifact["projection_bias"].astype(np.float32)
    head_weight = artifact["head_weight"].astype(np.float32)
    if projection_weight.shape != (8, 48) or projection_bias.shape != (8,) or head_weight.shape != (8, 9):
        raise SystemExit("model artifact has an unexpected tensor shape")

    latent8 = np.tanh(projection_weight @ observation + projection_bias)
    tensor9 = np.concatenate((latent8, np.ones(1, dtype=np.float32)))
    expected = head_weight @ tensor9
    result: dict[str, object] = {
        "tensor9": tensor9.tolist(),
        "expected_y8": expected.tolist(),
        "expected_argmax": int(expected.argmax()),
    }

    if args.port:
        try:
            import serial
        except ImportError as exc:
            raise SystemExit("serial use requires: python -m pip install pyserial") from exc
        with serial.Serial(args.port, args.baud, timeout=3, write_timeout=3, dsrdtr=False, rtscts=False) as device:
            device.dtr = False
            device.rts = False
            command = "MINFER x=" + ",".join(format(float(value), ".9g") for value in tensor9) + "\n"
            device.reset_input_buffer()
            device.write(command.encode("ascii"))
            device.flush()
            response = device.readline().decode("ascii", errors="replace").strip()
        if not response.startswith("OK model y8="):
            raise SystemExit(f"device inference failed: {response or 'no response'}")
        result["device_response"] = response

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
