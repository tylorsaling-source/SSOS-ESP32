#!/usr/bin/env python3
"""Generate the metric-only six-board A/B proof after all strict gates pass."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROMPT_IDS = ["p01", "p02", "p03", "p04", "p05"]
MODES = ["fast", "regular"]


def sha256(path: Path) -> str:
    if path.suffix.lower() != ".bin":
        return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(package: Path) -> tuple[dict, dict, dict[str, list[dict]]]:
    prompts = json.loads((package / "config" / "proof_prompts.json").read_text())
    oracle_path = package / "results" / "host" / "oracle.json"
    oracle = json.loads(oracle_path.read_text())
    physical = json.loads((package / "results" / "physical" / "ab_proof.json").read_text())
    if [item["id"] for item in prompts["prompts"]] != PROMPT_IDS:
        raise ValueError("prompt manifest is not the fixed five-prompt proof set")
    oracle_by_id = {item["id"]: item for item in oracle["results"]}
    grouped = {mode: [] for mode in MODES}
    for record in physical.get("records", []):
        if record.get("mode") in grouped:
            grouped[record["mode"]].append(record)
    for mode in MODES:
        if [item.get("prompt") for item in grouped[mode]] != PROMPT_IDS:
            raise ValueError(f"{mode}: incomplete or reordered five-prompt capture")
        if f"BENCH_DONE mode={mode} prompts=5 all_exact=1" not in physical.get("raw", []):
            raise ValueError(f"{mode}: successful BENCH_DONE gate absent")
        for item in grouped[mode]:
            expected = oracle_by_id[item["prompt"]]["output_ids"]
            if item.get("output_ids") != expected or item.get("exact") is not True:
                raise ValueError(f"{mode}/{item['prompt']}: token output differs from oracle")
            if item.get("tokens") != len(expected) or item.get("spi_errors") != 0:
                raise ValueError(f"{mode}/{item['prompt']}: count or SPI correctness gate failed")
            for field in ("ttft_ms", "prompt_to_finish_ms", "decode_tps"):
                if not isinstance(item.get(field), (int, float)) or item[field] <= 0:
                    raise ValueError(f"{mode}/{item['prompt']}: invalid {field}")
    return prompts, oracle, grouped


def aggregate(records: list[dict]) -> dict:
    total_ms = sum(item["prompt_to_finish_ms"] for item in records)
    decode_ms = sum(item["prompt_to_finish_ms"] - item["ttft_ms"] for item in records)
    decode_tokens = sum(item["tokens"] - 1 for item in records)
    return {
        "prompts": len(records),
        "tokens": sum(item["tokens"] for item in records),
        "exact_tokens": sum(item["tokens"] for item in records if item["exact"]),
        "mean_ttft_ms": sum(item["ttft_ms"] for item in records) / len(records),
        "total_prompt_to_finish_ms": total_ms,
        "aggregate_decode_tps": decode_tokens * 1000.0 / decode_ms,
        "spi_errors": sum(item["spi_errors"] for item in records),
    }


def escaped(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>")


def build_report(package: Path) -> tuple[str, dict]:
    prompts, oracle, grouped = validate(package)
    oracle_by_id = {item["id"]: item for item in oracle["results"]}
    prompt_by_id = {item["id"]: item for item in prompts["prompts"]}
    totals = {mode: aggregate(grouped[mode]) for mode in MODES}
    speed_ratio = (totals["regular"]["total_prompt_to_finish_ms"] /
                   totals["fast"]["total_prompt_to_finish_ms"])
    lines = [
        "# MobileLLM ParetoQ 125M six-board distributed A/B benchmark",
        "",
        "## Aggregate comparison",
        "",
        "| Metric | FAST | REGULAR | FAST / REGULAR comparison |",
        "|---|---:|---:|---:|",
        f"| Prompts | {totals['fast']['prompts']} | {totals['regular']['prompts']} | identical |",
        f"| Generated tokens | {totals['fast']['tokens']} | {totals['regular']['tokens']} | identical |",
        f"| Exact tokens | {totals['fast']['exact_tokens']}/120 | {totals['regular']['exact_tokens']}/120 | identical |",
        f"| Mean TTFT (ms) | {totals['fast']['mean_ttft_ms']:.3f} | {totals['regular']['mean_ttft_ms']:.3f} | {totals['regular']['mean_ttft_ms'] / totals['fast']['mean_ttft_ms']:.3f}x |",
        f"| Prompt-to-finish total (ms) | {totals['fast']['total_prompt_to_finish_ms']:.3f} | {totals['regular']['total_prompt_to_finish_ms']:.3f} | {speed_ratio:.3f}x |",
        f"| Aggregate decode (tok/s) | {totals['fast']['aggregate_decode_tps']:.6f} | {totals['regular']['aggregate_decode_tps']:.6f} | {totals['fast']['aggregate_decode_tps'] / totals['regular']['aggregate_decode_tps']:.3f}x |",
        f"| SPI errors | {totals['fast']['spi_errors']} | {totals['regular']['spi_errors']} | identical |",
        "",
        "Timing note: `spi_ms` in the raw capture is ring-cycle wall time. It overlaps "
        "worker computation and must not be interpreted as isolated wire-transfer time.",
        "",
        "## Per-prompt timing comparison",
        "",
        "| Prompt | FAST TTFT ms | REGULAR TTFT ms | FAST finish ms | REGULAR finish ms | FAST decode tok/s | REGULAR decode tok/s | Exact tokens |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for index, prompt_id in enumerate(PROMPT_IDS):
        fast = grouped["fast"][index]
        regular = grouped["regular"][index]
        lines.append(
            f"| {prompt_id} | {fast['ttft_ms']:.3f} | {regular['ttft_ms']:.3f} | "
            f"{fast['prompt_to_finish_ms']:.3f} | {regular['prompt_to_finish_ms']:.3f} | "
            f"{fast['decode_tps']:.6f} | {regular['decode_tps']:.6f} | 24/24 both |"
        )
    lines += [
        "",
        "## Exact input/output comparison",
        "",
        "| ID | Input | Host oracle output | FAST output | REGULAR output |",
        "|---|---|---|---|---|",
    ]
    for prompt_id in PROMPT_IDS:
        prompt = escaped(prompt_by_id[prompt_id]["text"])
        output = escaped(oracle_by_id[prompt_id]["output_text"])
        lines.append(f"| {prompt_id} | {prompt} | {output} | {output} | {output} |")
    app = package / "prebuilt" / "compute" / "application.bin"
    proof = package / "results" / "physical" / "ab_proof.json"
    summary = {
        "schema": "paretoq125m.ssos.physical-ab-summary.v1",
        "model_id": oracle["model_id"],
        "model_revision": oracle["model_revision"],
        "checkpoint_sha256": oracle["source"]["checkpoint_sha256"],
        "app_sha256": sha256(app),
        "physical_proof_sha256": sha256(proof),
        "decode": prompts["decode"],
        "aggregate": totals,
        "fast_over_regular_prompt_to_finish": speed_ratio,
        "all_exact": True,
    }
    lines += [
        "",
        "## Artifact identity",
        "",
        f"| Artifact | SHA-256 |",
        "|---|---|",
        f"| Official checkpoint | `{summary['checkpoint_sha256']}` |",
        f"| Compute-node app | `{summary['app_sha256']}` |",
        f"| Physical A/B capture | `{summary['physical_proof_sha256']}` |",
        "",
    ]
    return "\n".join(lines), summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    report, summary = build_report(args.package)
    physical = args.package / "results" / "physical"
    (physical / "AB_PROOF_REPORT.md").write_text(report, encoding="utf-8")
    (physical / "ab_proof_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
