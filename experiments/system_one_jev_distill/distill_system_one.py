#!/usr/bin/env python3
"""Distill System-One style atomic judgments into SSOS V2's 9->8 Q10 head.

Two modes:
  1) synthetic: generate a deliberately mildly-nonlinear teacher and measure how
     well the fixed 72-weight head approximates it.
  2) jsonl: fit from recorded teacher examples. Each line must contain:
       {"x8": [8 normalized features], "targets": [8 probabilities]}

The ninth SSOS input is reserved as a constant bias of 1.0.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np

QUESTION_NAMES = [
    "route_fast_path",
    "persist_state",
    "prefetch_context",
    "wake_worker",
    "retry_transport",
    "request_more_state",
    "state_anomalous",
    "fallback_deterministic",
]


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))


def synthetic_dataset(n: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Create normalized 8-D states and nonlinear teacher probabilities.

    This does not emulate Jev's hidden architecture. It stress-tests whether
    SSOS's fixed linear head can approximate atomic probabilistic judgments
    whose boundaries contain modest interactions/nonlinearities.
    """
    rng = np.random.default_rng(seed)
    x = rng.uniform(-1.0, 1.0, (n, 8)).astype(np.float32)
    w = rng.normal(0.0, 1.0, (8, 8))
    b = rng.normal(0.0, 0.3, 8)
    z = x @ w.T + b
    z[:, 0] += 1.4*x[:, 0]*x[:, 1] - 0.8*np.maximum(0.0, x[:, 2])
    z[:, 1] += 1.2*np.sin(np.pi*x[:, 3]) - 0.9*x[:, 4]*x[:, 5]
    z[:, 2] += 1.5*(x[:, 6]**2 - 0.33) + 0.7*x[:, 0]*x[:, 7]
    z[:, 3] += 1.0*np.tanh(2.0*x[:, 1]*x[:, 4])
    z[:, 4] += 1.3*np.maximum(0.0, x[:, 2] + x[:, 3] - 0.4)
    z[:, 5] += -1.1*np.abs(x[:, 5]) + 0.9*x[:, 6]*x[:, 7]
    z[:, 6] += 1.2*np.cos(np.pi*x[:, 0])*x[:, 2]
    z[:, 7] += (x[:, 1] > 0.25).astype(float) - 0.5*(x[:, 1] < -0.25).astype(float)
    return x, sigmoid(z).astype(np.float32)


def load_jsonl(path: Path) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = [], []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        x = np.asarray(row["x8"], dtype=np.float32)
        y = np.asarray(row["targets"], dtype=np.float32)
        if x.shape != (8,) or y.shape != (8,):
            raise ValueError(f"line {lineno}: expected x8[8] and targets[8]")
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError(f"line {lineno}: non-finite value")
        if np.any((y < 0.0) | (y > 1.0)):
            raise ValueError(f"line {lineno}: targets must be probabilities in [0,1]")
        xs.append(x)
        ys.append(y)
    if len(xs) < 32:
        raise ValueError("need at least 32 teacher examples")
    return np.stack(xs), np.stack(ys)


def fit_head(x8: np.ndarray, targets: np.ndarray, seed: int, steps: int = 1200, lr: float = 0.25):
    rng = np.random.default_rng(seed)
    n = len(x8)
    order = rng.permutation(n)
    cut = max(1, int(n * 0.8))
    tr, te = order[:cut], order[cut:]
    x9 = np.concatenate([x8, np.ones((n, 1), dtype=np.float32)], axis=1)
    w = np.zeros((8, 9), dtype=np.float64)
    for _ in range(steps):
        p = sigmoid(x9[tr] @ w.T)
        grad = ((p - targets[tr]).T @ x9[tr]) / len(tr)
        w -= lr * grad

    q10 = np.rint(w * 1024.0).astype(np.int32)
    wq = q10.astype(np.float64) / 1024.0
    p_float = sigmoid(x9[te] @ w.T)
    p_q10 = sigmoid(x9[te] @ wq.T)

    per_head = []
    for i, name in enumerate(QUESTION_NAMES):
        per_head.append({
            "name": name,
            "brier_q10": float(np.mean((p_q10[:, i] - targets[te, i])**2)),
            "mae_q10": float(np.mean(np.abs(p_q10[:, i] - targets[te, i]))),
            "threshold_agreement_q10": float(np.mean((p_q10[:, i] >= 0.5) == (targets[te, i] >= 0.5))),
        })
    report = {
        "examples": int(n),
        "train_examples": int(len(tr)),
        "test_examples": int(len(te)),
        "weights": 72,
        "encoding": "signed-q10",
        "mean_brier_q10": float(np.mean((p_q10 - targets[te])**2)),
        "mean_mae_q10": float(np.mean(np.abs(p_q10 - targets[te]))),
        "mean_threshold_agreement_q10": float(np.mean((p_q10 >= 0.5) == (targets[te] >= 0.5))),
        "max_probability_delta_float_vs_q10": float(np.max(np.abs(p_float - p_q10))),
        "per_head": per_head,
    }
    return q10, report


def model_document(q10: np.ndarray) -> dict[str, object]:
    return {
        "layout": "row-major 8x9 float32",
        "skills": QUESTION_NAMES,
        "rows": (q10.astype(np.float64) / 1024.0).tolist(),
        "encoding_note": "Rows are already snapped to signed Q10 so the existing V2 installer reproduces them exactly.",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher-jsonl", type=Path)
    ap.add_argument("--synthetic-examples", type=int, default=50000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path("system_one_distill_out"))
    args = ap.parse_args()

    if args.teacher_jsonl:
        x, y = load_jsonl(args.teacher_jsonl)
        source = str(args.teacher_jsonl)
    else:
        x, y = synthetic_dataset(args.synthetic_examples, args.seed)
        source = "synthetic_mildly_nonlinear_teacher"

    q10, report = fit_head(x, y, args.seed)
    report["teacher_source"] = source
    report["question_names"] = QUESTION_NAMES
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "ssos_head_rows.json").write_text(json.dumps(model_document(q10), indent=2) + "\n", encoding="utf-8")
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
