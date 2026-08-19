from __future__ import annotations

import copy
import json
from pathlib import Path

import torch
import torch.nn.functional as F

from model import ModelConfig, SplitModel, split_loss_backward


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    torch.manual_seed(0x5509)
    cfg = ModelConfig.load(ROOT / "config.json")
    continuous = SplitModel(cfg)
    split = copy.deepcopy(continuous)
    expected = {"master": 274944, "worker": 275040, "total": 549984}
    if continuous.parameter_counts() != expected:
        raise SystemExit(f"parameter gate failed: {continuous.parameter_counts()} != {expected}")

    tokens = torch.randint(0, cfg.vocab_size, (2, 17))
    targets = torch.roll(tokens, shifts=-1, dims=1)
    opt_a = torch.optim.SGD(continuous.parameters(), lr=1e-3)
    opt_b = torch.optim.SGD(split.parameters(), lr=1e-3)

    logits_a = continuous(tokens)
    loss_a = F.cross_entropy(logits_a.reshape(-1, cfg.vocab_size), targets.reshape(-1))
    loss_a.backward()
    loss_b, boundary_grad = split_loss_backward(split, tokens, targets)

    max_grad_error = 0.0
    for (name_a, param_a), (name_b, param_b) in zip(continuous.named_parameters(), split.named_parameters()):
        if name_a != name_b or param_a.grad is None or param_b.grad is None:
            raise SystemExit(f"gradient inventory mismatch at {name_a}/{name_b}")
        max_grad_error = max(max_grad_error, (param_a.grad - param_b.grad).abs().max().item())

    opt_a.step()
    opt_b.step()
    max_weight_error = max(
        (a - b).abs().max().item()
        for a, b in zip(continuous.state_dict().values(), split.state_dict().values())
    )
    result = {
        "format": "ssos.language.550k.split-gate.v1",
        "parameters": continuous.parameter_counts(),
        "loss_continuous": loss_a.item(),
        "loss_split": loss_b.item(),
        "loss_abs_error": abs(loss_a.item() - loss_b.item()),
        "max_gradient_abs_error": max_grad_error,
        "max_updated_weight_abs_error": max_weight_error,
        "boundary_gradient_l2": boundary_grad.norm().item(),
        "pass": abs(loss_a.item() - loss_b.item()) <= 1e-7 and max_grad_error <= 1e-6 and max_weight_error <= 1e-7,
    }
    print(json.dumps(result, indent=2))
    if not result["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
