#!/usr/bin/env python3
"""Collect eight Jev Noul probabilities for SSOS distillation examples."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from typesafe_sdk import Noul, TypeSafeClient

QUESTIONS = {
    "route_fast_path": "Given the state, should this work be routed through the fast path now?",
    "persist_state": "Given the state, should current state be persisted now to avoid meaningful loss?",
    "prefetch_context": "Given the state, would prefetching the likely next context be useful now?",
    "wake_worker": "Given the state, should an additional worker be woken or activated now?",
    "retry_transport": "Given the state, should the most recent transport operation be retried?",
    "request_more_state": "Is the available state insufficient for a reliable automatic decision?",
    "state_anomalous": "Does the current state appear anomalous relative to normal operation?",
    "fallback_deterministic": "Should the system fall back to its deterministic safe/default path now?",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path, help="JSONL rows with state and x8")
    ap.add_argument("output", type=Path, help="JSONL teacher dataset")
    args = ap.parse_args()

    typed_questions = {name: Noul(instructions=text) for name, text in QUESTIONS.items()}
    rows = args.input.read_text(encoding="utf-8").splitlines()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with TypeSafeClient() as client, args.output.open("w", encoding="utf-8") as out:
        for lineno, line in enumerate(rows, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            x8 = row.get("x8")
            if not isinstance(x8, list) or len(x8) != 8:
                raise SystemExit(f"line {lineno}: x8 must contain exactly 8 values")
            try:
                x8 = [float(value) for value in x8]
            except (TypeError, ValueError) as exc:
                raise SystemExit(f"line {lineno}: x8 contains a non-numeric value") from exc
            if not all(math.isfinite(value) and -1.0 <= value <= 1.0 for value in x8):
                raise SystemExit(f"line {lineno}: x8 values must be finite and in [-1,1]")

            state = row.get("state")
            if not isinstance(state, (str, dict, list)):
                raise SystemExit(f"line {lineno}: state must be text, an object, or an array")

            response = client.system_one(state=state, questions=typed_questions)
            missing = [name for name in QUESTIONS if name not in response.nouls]
            if missing:
                raise SystemExit(f"line {lineno}: Jev response missing Noul answers: {', '.join(missing)}")
            targets = [float(response.nouls[name].noul) for name in QUESTIONS]
            if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in targets):
                raise SystemExit(f"line {lineno}: Jev returned an invalid probability")

            out.write(json.dumps({"x8": x8, "targets": targets}, separators=(",", ":")) + "\n")
            print(f"{lineno}: " + " ".join(f"{name}={targets[i]:.3f}" for i, name in enumerate(QUESTIONS)))


if __name__ == "__main__":
    main()
