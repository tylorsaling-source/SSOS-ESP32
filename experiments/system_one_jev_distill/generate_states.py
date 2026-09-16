#!/usr/bin/env python3
"""Generate deterministic SSOS-like states plus their compact x8 projection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np


def clamp(v: float) -> float:
    return float(max(-1.0, min(1.0, v)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("output", type=Path)
    ap.add_argument("--count", type=int, default=1024)
    ap.add_argument("--seed", type=int, default=1337)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for i in range(args.count):
            queue_depth = int(rng.integers(0, 65))
            queue_capacity = 64
            free_heap = int(rng.integers(24_000, 420_001))
            free_heap_nominal = 420_000
            transport_error_rate = float(rng.beta(1.3, 7.0))
            worker_ready_count = int(rng.integers(0, 5))
            worker_total = 4
            novelty = float(rng.beta(1.4, 2.0))
            confidence = float(rng.beta(2.0, 1.6))
            persistence_cost = float(rng.beta(1.5, 1.8))
            deadline_ms = int(rng.choice([0, 10, 25, 50, 100, 250, 500, 1000, 5000]))
            retry_count = int(rng.integers(0, 5))
            state_age_ms = int(rng.integers(0, 30_001))
            unsaved_updates = int(rng.integers(0, 33))

            urgency01 = 0.0 if deadline_ms == 0 else 1.0 / (1.0 + deadline_ms / 100.0)
            queue01 = queue_depth / queue_capacity
            memory_pressure01 = 1.0 - free_heap / free_heap_nominal
            transport_health01 = 1.0 - transport_error_rate
            worker_capacity01 = worker_ready_count / worker_total

            x8 = [
                clamp(2.0 * urgency01 - 1.0),
                clamp(2.0 * queue01 - 1.0),
                clamp(2.0 * memory_pressure01 - 1.0),
                clamp(2.0 * transport_health01 - 1.0),
                clamp(2.0 * worker_capacity01 - 1.0),
                clamp(2.0 * novelty - 1.0),
                clamp(2.0 * confidence - 1.0),
                clamp(2.0 * persistence_cost - 1.0),
            ]

            state = {
                "sample_id": i,
                "queue": {"depth": queue_depth, "capacity": queue_capacity},
                "memory": {"free_heap_bytes": free_heap, "nominal_free_heap_bytes": free_heap_nominal},
                "transport": {"recent_error_rate": round(transport_error_rate, 6), "retry_count": retry_count},
                "workers": {"ready": worker_ready_count, "total": worker_total},
                "decision_context": {
                    "deadline_ms": deadline_ms,
                    "state_age_ms": state_age_ms,
                    "state_novelty": round(novelty, 6),
                    "confidence_margin": round(confidence, 6),
                    "persistence_loss_cost": round(persistence_cost, 6),
                    "unsaved_updates": unsaved_updates,
                },
            }
            f.write(json.dumps({"state": state, "x8": x8}, separators=(",", ":")) + "\n")

    print(f"wrote {args.count} states to {args.output}")


if __name__ == "__main__":
    main()
