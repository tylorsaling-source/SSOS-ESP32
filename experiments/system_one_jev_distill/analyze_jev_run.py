"""Post-run baselines and worker-count diagnostics; no API calls or gate changes."""
import argparse
import json
from pathlib import Path

import numpy as np


def analyze(run: Path, seed: int):
    records = [json.loads(line) for line in (run / "jev_teacher.jsonl").read_text().splitlines()]
    states = [json.loads(line)["state"] for line in (run / "states.jsonl").read_text().splitlines()]
    if len(records) != len(states):
        raise ValueError("Require a complete teacher collection aligned to the state file.")
    x = np.array([row["x8"] for row in records])
    y = np.array([row["targets"] for row in records])
    order = np.random.default_rng(seed).permutation(len(records))
    tr, te = order[:int(len(records) * .8)], order[int(len(records) * .8):]
    report = json.loads((run / "distilled/report.json").read_text())
    rows = np.array(json.loads((run / "distilled/ssos_head_rows.json").read_text())["rows"])
    p = 1 / (1 + np.exp(-np.c_[x, np.ones(len(records))] @ rows.T))
    heads = []
    for i, name in enumerate(report["question_names"]):
        majority = np.mean(y[tr, i] >= .5) >= .5
        heads.append({
            "name": name,
            "test_teacher_positive_rate": float(np.mean(y[te, i] >= .5)),
            "student_agreement": float(np.mean((p[te, i] >= .5) == (y[te, i] >= .5))),
            "training_majority_baseline_agreement": float(np.mean(majority == (y[te, i] >= .5))),
            "student_mae": float(np.mean(abs(p[te, i] - y[te, i]))),
            "training_mean_probability_baseline_mae": float(np.mean(abs(y[tr, i].mean() - y[te, i]))),
        })
    ready = np.array([state["workers"]["ready"] for state in states])
    groups = []
    for count in range(5):
        sub, train = te[ready[te] == count], tr[ready[tr] == count]
        if not len(train) or not len(sub):
            raise ValueError("Worker-count diagnostic requires all groups in both splits.")
        groups.append({
            "ready_workers": count, "train_examples": len(train), "test_examples": len(sub),
            "training_teacher_mean_probability": float(y[train, 3].mean()),
            "test_teacher_mean_probability": float(y[sub, 3].mean()),
            "student_mean_probability": float(p[sub, 3].mean()),
            "test_teacher_positive_rate": float(np.mean(y[sub, 3] >= .5)),
            "student_agreement": float(np.mean((p[sub, 3] >= .5) == (y[sub, 3] >= .5))),
        })
    lookup = np.array([y[tr[ready[tr] == count], 3].mean() for count in range(5)])
    return {
        "teacher_models": sorted({row["teacher_model"] for row in records}),
        "mean_training_majority_baseline_agreement": float(np.mean([h["training_majority_baseline_agreement"] for h in heads])),
        "per_head": heads, "wake_worker_by_ready_count": groups,
        "wake_worker_training_group_mean_baseline_test_agreement": float(np.mean((lookup[ready[te]] >= .5) == (y[te, 3] >= .5))),
        "note": "Post-run diagnostic; original gate unchanged. Baselines are fitted only on training data. No new Jev requests.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args()
    result = analyze(args.run, args.seed)
    path = args.run / "diagnostics.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote post-run diagnostics: {path}")
