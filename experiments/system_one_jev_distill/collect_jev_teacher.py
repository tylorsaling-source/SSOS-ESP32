#!/usr/bin/env python3
"""Collect eight Jev Noul probabilities for SSOS distillation examples."""
from __future__ import annotations

import argparse
import json
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

    client = TypeSafeClient()
    typed_questions = {k: Noul(instructions=v) for k, v in QUESTIONS.items()}

    with args.output.open("w", encoding="utf-8") as out:
        for lineno, line in enumerate(args.input.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            x8 = row.get("x8")
            if not isinstance(x8, list) or len(x8) != 8:
                raise SystemExit(f"line {lineno}: x8 must contain exactly 8 values")
            state = row.get("state")
            if state is None:
                raise SystemExit(f"line {lineno}: missing state")
            state_text = state if isinstance(state, str) else json.dumps(state, sort_keys=True, separators=(",", ":"))
            response = client.system_one(state=state_text, questions=typed_questions)
            targets = [float(response.answers[name].noul) for name in QUESTIONS]
            record = {"x8": [float(v) for v in x8], "targets": targets}
            out.write(json.dumps(record, separators=(",", ":")) + "\n")
            print(f"{lineno}: " + " ".join(f"{name}={targets[i]:.3f}" for i, name in enumerate(QUESTIONS)))


if __name__ == "__main__":
    main()
