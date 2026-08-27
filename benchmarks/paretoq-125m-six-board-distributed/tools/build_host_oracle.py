#!/usr/bin/env python3
"""Generate the fixed laptop oracle used by both physical benchmark paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_oracle(model_path: Path, prompt_path: Path, output_path: Path) -> dict:
    specification = json.loads(prompt_path.read_text(encoding="utf-8"))
    decode = specification["decode"]
    tokenizer = AutoTokenizer.from_pretrained(
        model_path, use_fast=False, legacy=True, local_files_only=True
    )
    tokenizer.pad_token_id = int(decode["pad_token_id"])
    model = AutoModelForCausalLM.from_pretrained(
        model_path, local_files_only=True, dtype=torch.bfloat16
    ).eval()

    results = []
    with torch.inference_mode():
        for item in specification["prompts"]:
            started = time.perf_counter_ns()
            encoded = tokenizer(item["text"], return_tensors="pt", add_special_tokens=True)
            generated = model.generate(
                **encoded,
                max_new_tokens=int(decode["max_new_tokens"]),
                do_sample=bool(decode["do_sample"]),
                use_cache=bool(decode["use_cache"]),
                bos_token_id=int(decode["bos_token_id"]),
                eos_token_id=int(decode["eos_token_id"]),
                pad_token_id=int(decode["pad_token_id"]),
            )
            input_count = int(encoded["input_ids"].shape[1])
            output_ids = generated[0, input_count:].tolist()
            elapsed_ns = time.perf_counter_ns() - started
            results.append(
                {
                    "id": item["id"],
                    "category": item["category"],
                    "prompt": item["text"],
                    "input_ids": encoded["input_ids"][0].tolist(),
                    "output_ids": output_ids,
                    "output_text": tokenizer.decode(output_ids, skip_special_tokens=False),
                    "generated_tokens": len(output_ids),
                    "prompt_to_finish_ms": elapsed_ns / 1_000_000.0,
                }
            )
            print(
                f"{item['id']}: {len(output_ids)} tokens in {elapsed_ns / 1_000_000.0:.1f} ms",
                flush=True,
            )

    checkpoint = model_path / "pytorch_model.bin"
    tokenizer_file = model_path / "tokenizer.model"
    artifact = {
        "schema": "paretoq125m.ssos.host-oracle.v1",
        "model_id": "facebook/MobileLLM-ParetoQ-125M-2-bit",
        "model_revision": "2e367775142fafa944e28a1e8a1fc428e8554fab",
        "source": {
            "checkpoint_sha256": sha256_file(checkpoint),
            "tokenizer_sha256": sha256_file(tokenizer_file),
        },
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "platform": platform.platform(),
        },
        "decode": decode,
        "prompt_count": len(results),
        "generated_token_count": sum(item["generated_tokens"] for item in results),
        "results": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    text_path = output_path.with_suffix(".txt")
    with text_path.open("w", encoding="utf-8") as stream:
        for item in results:
            stream.write(f"[{item['id']}] PROMPT\n{item['prompt']}\n")
            stream.write(f"[{item['id']}] OUTPUT\n{item['output_text']}\n\n")
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--prompts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    artifact = build_oracle(args.model, args.prompts, args.output)
    print(
        json.dumps(
            {
                "prompt_count": artifact["prompt_count"],
                "generated_token_count": artifact["generated_token_count"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
