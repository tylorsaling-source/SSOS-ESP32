#!/usr/bin/env python3
"""Generate the fixed five-prompt token proof corpus for the ESP32 master."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def values(items: list[int]) -> str:
    return ", ".join(f"{int(item)}u" for item in items)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    oracle = json.loads(args.oracle.read_text(encoding="utf-8"))
    if oracle["prompt_count"] != 5:
        raise RuntimeError("proof header requires exactly five prompts")
    lines = [
        "#pragma once", "", "#include <stdint.h>", "", "namespace paretoq {", "",
        "struct ProofPrompt {", "  const char* id;", "  const uint16_t* input_ids;",
        "  uint16_t input_count;", "  const uint16_t* expected_ids;",
        "  uint16_t output_count;", "};", "",
    ]
    for result in oracle["results"]:
        name = result["id"].upper()
        lines.append(f"static constexpr uint16_t k{name}Input[] = {{{values(result['input_ids'])}}};")
        lines.append(f"static constexpr uint16_t k{name}Expected[] = {{{values(result['output_ids'])}}};")
    lines.extend(["", "static constexpr ProofPrompt kProofPrompts[] = {"])
    for result in oracle["results"]:
        name = result["id"].upper()
        lines.append(
            f'  {{"{result["id"]}", k{name}Input, {len(result["input_ids"])}u, '
            f'k{name}Expected, {len(result["output_ids"])}u}},'
        )
    lines.extend(["};", "", "static constexpr uint32_t kProofPromptCount = 5u;",
                  "", "}  // namespace paretoq", ""])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
