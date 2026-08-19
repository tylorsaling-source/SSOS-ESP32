from __future__ import annotations

import argparse
from pathlib import Path

import torch
from tokenizers import ByteLevelBPETokenizer

from model import ModelConfig, SplitModel


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load(checkpoint_path: Path):
    cfg = ModelConfig.load(ROOT / "config.json")
    model = SplitModel(cfg)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model.master.load_state_dict(checkpoint["master"])
    model.worker.load_state_dict(checkpoint["worker"])
    model.eval()
    tokenizer = ByteLevelBPETokenizer(
        str(DATA / "ssos-550k-vocab.json"),
        str(DATA / "ssos-550k-merges.txt"),
    )
    return cfg, model, tokenizer, int(checkpoint["step"])


@torch.no_grad()
def generate(cfg, model, tokenizer, prompt: str, count: int, temperature: float, top_k: int) -> str:
    ids = tokenizer.encode(prompt).ids
    if not ids:
        ids = [0]
    for _ in range(count):
        context = ids[-cfg.max_seq_len :]
        x = torch.tensor(context, dtype=torch.long).unsqueeze(0)
        logits = model(x)[0, -1] / max(temperature, 1e-5)
        values, indices = torch.topk(logits, min(top_k, cfg.vocab_size))
        probabilities = torch.softmax(values, dim=-1)
        next_id = indices[torch.multinomial(probabilities, 1)].item()
        ids.append(next_id)
        if next_id == 2:
            break
    return tokenizer.decode(ids)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("prompt")
    parser.add_argument("--tokens", type=int, default=80)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--seed", type=int, default=550984)
    args = parser.parse_args()
    torch.manual_seed(args.seed)
    cfg, model, tokenizer, step = load(args.checkpoint)
    print(f"[checkpoint step {step}]")
    print(generate(cfg, model, tokenizer, args.prompt, args.tokens, args.temperature, args.top_k))


if __name__ == "__main__":
    main()
