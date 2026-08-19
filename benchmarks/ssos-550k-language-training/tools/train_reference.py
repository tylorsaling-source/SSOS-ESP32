from __future__ import annotations

import argparse
import json
import math
import os
import random
import tempfile
from pathlib import Path

import torch
from tokenizers import ByteLevelBPETokenizer

from model import ModelConfig, SplitModel, split_loss_backward


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CHECKPOINTS = ROOT / "checkpoints"


def atomic_save(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        torch.save(payload, temp_path)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def load_tokens() -> torch.Tensor:
    corpus = DATA / "corpus.txt"
    vocab = DATA / "ssos-550k-vocab.json"
    merges = DATA / "ssos-550k-merges.txt"
    if not corpus.exists() or not vocab.exists() or not merges.exists():
        raise SystemExit("prepare the corpus first with tools/prepare_corpus.py")
    tokenizer = ByteLevelBPETokenizer(str(vocab), str(merges))
    ids = tokenizer.encode(corpus.read_text(encoding="utf-8")).ids
    return torch.tensor(ids, dtype=torch.long)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--sequence-length", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--min-learning-rate", type=float, default=3e-5)
    parser.add_argument("--warmup-steps", type=int, default=2_000)
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--eval-every", type=int, default=25)
    parser.add_argument("--eval-batches", type=int, default=8)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--initial-presented-tokens", type=int)
    parser.add_argument("--target-tokens-per-parameter", type=float)
    parser.add_argument("--schedule-origin", choices=("global", "run"), default="global")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--seed", type=int, default=550984)
    args = parser.parse_args()
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    cfg = ModelConfig.load(ROOT / "config.json")
    corpus_manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    corpus_identity = {
        key: corpus_manifest[key]
        for key in ("corpus_sha256", "vocab_sha256", "merges_sha256")
    }
    if args.sequence_length > cfg.max_seq_len:
        raise SystemExit("sequence length exceeds model context")
    tokens = None
    validation_tokens = None
    if not args.plan_only:
        all_tokens = load_tokens()
        if len(all_tokens) <= args.sequence_length + 1:
            raise SystemExit("corpus is too small")
        split_at = int(len(all_tokens) * 0.95)
        tokens = all_tokens[:split_at]
        validation_tokens = all_tokens[split_at:]
    model = SplitModel(cfg)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, betas=(0.9, 0.95), weight_decay=0.1)
    first_step = 1
    presented_before_run = 0
    parent_checkpoint = None
    if args.resume:
        checkpoint = torch.load(args.resume, map_location="cpu", weights_only=False)
        if checkpoint.get("format") not in {
            "ssos.language.550k.checkpoint.v1",
            "ssos.language.550k.checkpoint.v2",
        }:
            raise SystemExit("unsupported checkpoint format")
        if checkpoint.get("corpus_identity") != corpus_identity:
            raise SystemExit("checkpoint tokenizer/corpus identity does not match the active data")
        model.master.load_state_dict(checkpoint["master"])
        model.worker.load_state_dict(checkpoint["worker"])
        optimizer.load_state_dict(checkpoint["optimizer"])
        if "rng_state" in checkpoint:
            torch.random.set_rng_state(checkpoint["rng_state"])
        first_step = int(checkpoint["step"]) + 1
        parent_checkpoint = str(args.resume.resolve())
        if "presented_tokens" in checkpoint:
            presented_before_run = int(checkpoint["presented_tokens"])
        elif args.initial_presented_tokens is not None:
            presented_before_run = args.initial_presented_tokens
        else:
            presented_before_run = int(checkpoint["step"]) * args.batch_size * args.sequence_length
    elif args.initial_presented_tokens not in (None, 0):
        raise SystemExit("initial presented tokens require --resume")

    parameters = model.parameter_counts()["total"]
    tokens_per_step = args.batch_size * args.sequence_length
    last_step = args.steps
    if args.target_tokens_per_parameter is not None:
        if args.target_tokens_per_parameter <= 0:
            raise SystemExit("target tokens per parameter must be positive")
        target_presented_tokens = math.ceil(parameters * args.target_tokens_per_parameter)
        remaining = target_presented_tokens - presented_before_run
        if remaining <= 0:
            raise SystemExit("target tokens per parameter already reached")
        last_step = first_step - 1 + math.ceil(remaining / tokens_per_step)
    else:
        target_presented_tokens = presented_before_run + max(0, last_step - first_step + 1) * tokens_per_step
    if last_step < first_step:
        raise SystemExit("last step precedes the first resumable step")
    start_event = {
        "event": "training_start",
        "parameters": model.parameter_counts(),
        "train_tokens": None if tokens is None else len(tokens),
        "validation_tokens": None if validation_tokens is None else len(validation_tokens),
        "first_step": first_step,
        "last_step": last_step,
        "tokens_per_step": tokens_per_step,
        "presented_before_run": presented_before_run,
        "target_presented_tokens": target_presented_tokens,
        "target_tokens_per_parameter": target_presented_tokens / parameters,
        "schedule_origin": args.schedule_origin,
    }
    print(json.dumps(start_event))
    if args.plan_only:
        return

    def learning_rate(step: int) -> float:
        if args.schedule_origin == "run":
            ratio = (step - first_step) / max(1, last_step - first_step)
            cosine = 0.5 * (1.0 + math.cos(math.pi * min(1.0, max(0.0, ratio))))
            return args.min_learning_rate + cosine * (args.learning_rate - args.min_learning_rate)
        if step <= args.warmup_steps:
            return args.learning_rate * step / max(1, args.warmup_steps)
        ratio = (step - args.warmup_steps) / max(1, last_step - args.warmup_steps)
        cosine = 0.5 * (1.0 + math.cos(math.pi * min(1.0, ratio)))
        return args.min_learning_rate + cosine * (args.learning_rate - args.min_learning_rate)

    def evaluate() -> float:
        model.eval()
        losses = []
        with torch.no_grad():
            span = len(validation_tokens) - args.sequence_length - 1
            for index in range(args.eval_batches):
                start = (index * max(1, span // args.eval_batches)) % max(1, span)
                x_eval = validation_tokens[start : start + args.sequence_length].unsqueeze(0)
                y_eval = validation_tokens[start + 1 : start + args.sequence_length + 1].unsqueeze(0)
                logits = model(x_eval)
                losses.append(torch.nn.functional.cross_entropy(logits.reshape(-1, cfg.vocab_size), y_eval.reshape(-1)).item())
        model.train()
        return sum(losses) / len(losses)

    for step in range(first_step, last_step + 1):
        lr = learning_rate(step)
        for group in optimizer.param_groups:
            group["lr"] = lr
        starts = torch.randint(0, len(tokens) - args.sequence_length - 1, (args.batch_size,))
        x = torch.stack([tokens[s : s + args.sequence_length] for s in starts])
        y = torch.stack([tokens[s + 1 : s + args.sequence_length + 1] for s in starts])
        optimizer.zero_grad(set_to_none=True)
        loss, boundary_gradient = split_loss_backward(model, x, y)
        grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        if not torch.isfinite(loss) or not torch.isfinite(grad_norm):
            raise SystemExit("non-finite training state")
        optimizer.step()
        presented_tokens = presented_before_run + (step - first_step + 1) * tokens_per_step
        print(json.dumps({
            "event": "step",
            "step": step,
            "loss": loss.item(),
            "grad_norm": float(grad_norm),
            "boundary_grad_norm": boundary_gradient.norm().item(),
            "learning_rate": lr,
            "presented_tokens": presented_tokens,
            "tokens_per_parameter": presented_tokens / parameters,
            "corpus_passes": presented_tokens / len(tokens),
        }))
        if step % args.eval_every == 0 or step == last_step:
            print(json.dumps({"event": "validation", "step": step, "loss": evaluate()}))
        if step % args.checkpoint_every == 0 or step == last_step:
            atomic_save({
                "format": "ssos.language.550k.checkpoint.v2",
                "step": step,
                "presented_tokens": presented_tokens,
                "config": cfg.__dict__,
                "master": model.master.state_dict(),
                "worker": model.worker.state_dict(),
                "optimizer": optimizer.state_dict(),
                "rng_state": torch.random.get_rng_state(),
                "corpus_identity": corpus_identity,
                "parent_checkpoint": parent_checkpoint,
                "schedule": {
                    "learning_rate": args.learning_rate,
                    "min_learning_rate": args.min_learning_rate,
                    "warmup_steps": args.warmup_steps,
                    "schedule_origin": args.schedule_origin,
                    "first_step": first_step,
                    "target_steps": last_step,
                    "batch_size": args.batch_size,
                    "sequence_length": args.sequence_length,
                    "target_presented_tokens": target_presented_tokens,
                    "target_tokens_per_parameter": target_presented_tokens / parameters,
                },
            }, CHECKPOINTS / f"step-{step:08d}.pt")


if __name__ == "__main__":
    main()
