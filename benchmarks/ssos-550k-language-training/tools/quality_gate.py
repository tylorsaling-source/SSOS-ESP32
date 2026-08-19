from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import torch

from generate import generate, load


PROMPTS = [
    "The northern bridge shifted after heavy rain, so the team first",
    "A scout reports smoke beyond the ridge but cannot identify its source. We know",
    "The stored water looks clear, but before anyone drinks it",
    "Nara asked, \"Why did the shelter flood?\" Tomas answered,",
    "The compass and the visible landmark disagree. Rather than guessing, the navigator",
]


def repetition(text: str) -> float:
    words = re.findall(r"[A-Za-z']+", text.lower())
    pairs = list(zip(words, words[1:]))
    return 0.0 if not pairs else 1.0 - len(set(pairs)) / len(pairs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--tokens", type=int, default=80)
    args = parser.parse_args()
    cfg, model, tokenizer, step = load(args.checkpoint)
    rows = []
    for index, prompt in enumerate(PROMPTS):
        torch.manual_seed(550984 + index)
        text = generate(cfg, model, tokenizer, prompt, args.tokens, 0.75, 40)
        lower = text.lower()
        rows.append({
            "prompt": prompt,
            "text": text,
            "repeated_bigram_fraction": repetition(text),
            "contains_blocked_story_opening": any(x in lower for x in ("once upon a time", "magical kingdom", "little fairy")),
        })
    result = {
        "format": "ssos.language.550k.quality.v1",
        "checkpoint_step": step,
        "samples": rows,
        "blocked_openings": sum(row["contains_blocked_story_opening"] for row in rows),
        "mean_repeated_bigram_fraction": sum(row["repeated_bigram_fraction"] for row in rows) / len(rows),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
