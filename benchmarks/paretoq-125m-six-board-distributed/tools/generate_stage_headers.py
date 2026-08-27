#!/usr/bin/env python3
"""Generate compile-time ESP32 stage offsets from verified shard manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


MATRIX_FIELDS = {
    "self_attn.q_proj.weight": "query",
    "self_attn.k_proj.weight": "key",
    "self_attn.v_proj.weight": "value",
    "self_attn.o_proj.weight": "attention_output",
    "mlp.gate_proj.weight": "gate",
    "mlp.up_proj.weight": "up",
    "mlp.down_proj.weight": "down",
}


def matrix_literal(record: dict) -> str:
    rows, columns = (int(value) for value in record["shape"])
    row_bytes = (columns + 3) // 4
    return (
        f"{{{int(record['code_offset'])}u, {int(record['low_scale_offset'])}u, "
        f"{int(record['high_scale_offset'])}u, "
        f"{rows}u, {columns}u, {row_bytes}u}}"
    )


def generate(manifest_path: Path, output_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    layers: dict[int, dict[str, dict]] = {}
    final_norm_offset = 0xFFFFFFFF
    for record in manifest["records"]:
        name = record["name"]
        if name == "model.norm.weight":
            final_norm_offset = int(record["offset"])
            continue
        pieces = name.split(".")
        layer = int(pieces[2])
        suffix = ".".join(pieces[3:])
        layers.setdefault(layer, {})[suffix] = record

    expected = list(range(int(manifest["layers"][0]), int(manifest["layers"][1]) + 1))
    if sorted(layers) != expected:
        raise RuntimeError("layer coverage mismatch")

    lines = [
        "#pragma once",
        "",
        '#include "../common/paretoq_layout.h"',
        "",
        "namespace paretoq {",
        "",
        f"static constexpr LayerLocation kStage{manifest['stage']}Layers[] = {{",
    ]
    for layer in expected:
        records = layers[layer]
        missing = set(MATRIX_FIELDS) | {
            "input_layernorm.weight", "post_attention_layernorm.weight"
        }
        missing -= set(records)
        if missing:
            raise RuntimeError(f"layer {layer} missing {sorted(missing)}")
        fields = [f"    {layer}u,"]
        for suffix in MATRIX_FIELDS:
            fields.append(f"    {matrix_literal(records[suffix])},")
        fields.extend(
            [
                f"    {int(records['input_layernorm.weight']['offset'])}u,",
                f"    {int(records['post_attention_layernorm.weight']['offset'])}u",
            ]
        )
        lines.extend(["  {"] + fields + ["  },"])
    vocab = manifest["vocab"]
    layers_bytes = int(manifest["flash"]["layers_bytes"])
    vocab_flash_offset = int(manifest["flash"]["vocab_flash_offset"])
    lines.extend(
        [
            "};",
            "",
            f"static constexpr StageLocation kStage{manifest['stage']}Location = {{",
            f"  {int(manifest['stage'])}u,",
            f"  {expected[0]}u,",
            f"  {len(expected)}u,",
            f"  {layers_bytes}u,",
            f"  {vocab_flash_offset}u,",
            f"  {int(vocab['first'])}u,",
            f"  {int(vocab['count'])}u,",
            f"  {int(vocab['flash_rows'])}u,",
            f"  {int(vocab['psram_rows'])}u,",
            f"  {final_norm_offset}u,",
            f"  kStage{manifest['stage']}Layers",
            "};",
            "",
            "}  // namespace paretoq",
            "",
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shards", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifests = sorted(args.shards.glob("stage*-com*/manifest.json"))
    if len(manifests) != 5:
        raise RuntimeError(f"expected five manifests, found {len(manifests)}")
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        output_path = args.output / f"stage{int(manifest['stage'])}_layout.h"
        generate(manifest_path, output_path)
        print(output_path)


if __name__ == "__main__":
    main()
