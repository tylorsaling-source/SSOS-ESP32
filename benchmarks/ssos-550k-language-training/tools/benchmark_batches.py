from __future__ import annotations

import json
import time
from pathlib import Path

import torch

from model import ModelConfig, SplitModel, split_loss_backward


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    cfg = ModelConfig.load(ROOT / "config.json")
    rows = []
    for batch in (1, 2, 4, 8):
        torch.manual_seed(550984)
        model = SplitModel(cfg)
        optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4)
        x = torch.randint(0, cfg.vocab_size, (batch, 64))
        y = torch.randint(0, cfg.vocab_size, (batch, 64))
        for _ in range(2):
            optimizer.zero_grad(set_to_none=True)
            split_loss_backward(model, x, y)
            optimizer.step()
        started = time.perf_counter()
        for _ in range(12):
            optimizer.zero_grad(set_to_none=True)
            split_loss_backward(model, x, y)
            optimizer.step()
        elapsed = time.perf_counter() - started
        rows.append({"batch_size": batch, "sequence_length": 64, "seconds": elapsed, "presented_tokens_per_second": 12 * batch * 64 / elapsed})
    result = {"format": "ssos.language.batch-benchmark.v1", "rows": rows, "winner": max(rows, key=lambda row: row["presented_tokens_per_second"])}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
