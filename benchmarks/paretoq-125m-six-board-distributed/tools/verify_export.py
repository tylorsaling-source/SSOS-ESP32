#!/usr/bin/env python3
"""Independently verify every exported ParetoQ shard against the checkpoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from export_paretoq import bf16_bytes, sha256_file, unpack_2bit


def read_slice(path: Path, offset: int, size: int) -> bytes:
    with path.open("rb") as stream:
        stream.seek(offset)
        payload = stream.read(size)
    if len(payload) != size:
        raise RuntimeError(f"short read from {path}: wanted {size}, got {len(payload)}")
    return payload


def verify_matrix(source: torch.Tensor, codes: bytes, low_scales: bytes, high_scales: bytes) -> int:
    rows, columns = source.shape
    code_tensor = torch.from_numpy(
        unpack_2bit(codes, source.numel()).reshape(rows, columns).astype(np.int16)
    )
    low = torch.frombuffer(bytearray(low_scales), dtype=torch.bfloat16).float()[:, None]
    high = torch.frombuffer(bytearray(high_scales), dtype=torch.bfloat16).float()[:, None]
    recovered = torch.where(
        code_tensor == 0, -high,
        torch.where(code_tensor == 1, -low, torch.where(code_tensor == 2, low, high)),
    ).to(torch.bfloat16)
    if not torch.equal(recovered, source.detach().cpu().contiguous()):
        mismatches = int(torch.count_nonzero(recovered != source.detach().cpu()))
        raise RuntimeError(f"matrix reconstruction mismatch: {mismatches} values")
    return source.numel()


def verify(checkpoint: Path, export_root: Path) -> dict:
    manifest_path = export_root / "export_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256_file(checkpoint) != manifest["source"]["sha256"]:
        raise RuntimeError("checkpoint SHA-256 mismatch")
    state = torch.load(checkpoint, map_location="cpu", weights_only=True, mmap=True)
    if not torch.equal(state["model.embed_tokens.weight"], state["lm_head.weight"]):
        raise RuntimeError("checkpoint embedding/head equality changed")

    tensor_count = 0
    value_count = 0
    covered: set[str] = set()
    node_results = []
    for node in manifest["nodes"]:
        node_root = export_root / f"stage{node['stage']}-{node['port'].lower()}"
        local_manifest = json.loads((node_root / "manifest.json").read_text(encoding="utf-8"))
        for filename, evidence in local_manifest["files"].items():
            path = node_root / filename
            if path.stat().st_size != evidence["bytes"]:
                raise RuntimeError(f"size mismatch: {path}")
            if sha256_file(path) != evidence["sha256"]:
                raise RuntimeError(f"SHA-256 mismatch: {path}")

        layer_path = node_root / "layers.bin"
        for record in local_manifest["records"]:
            name = record["name"]
            if name in covered:
                raise RuntimeError(f"tensor exported twice: {name}")
            covered.add(name)
            source = state[name]
            if record["kind"] == "four_level_2bit_matrix":
                codes = read_slice(layer_path, record["code_offset"], record["code_bytes"])
                low_scales = read_slice(
                    layer_path, record["low_scale_offset"], record["low_scale_bytes"]
                )
                high_scales = read_slice(
                    layer_path, record["high_scale_offset"], record["high_scale_bytes"]
                )
                value_count += verify_matrix(source, codes, low_scales, high_scales)
            else:
                payload = read_slice(layer_path, record["offset"], record["bytes"])
                if payload != bf16_bytes(source):
                    raise RuntimeError(f"BF16 tensor mismatch: {name}")
                value_count += source.numel()
            tensor_count += 1

        vocab = local_manifest["vocab"]
        first = int(vocab["first"])
        count = int(vocab["count"])
        expected_vocab = bf16_bytes(state["model.embed_tokens.weight"][first : first + count])
        actual_vocab = (node_root / "vocab_flash.bin").read_bytes() + (
            node_root / "vocab_psram.bin"
        ).read_bytes()
        if actual_vocab != expected_vocab:
            raise RuntimeError(f"vocabulary shard mismatch: stage {node['stage']}")
        value_count += count * int(state["model.embed_tokens.weight"].shape[1])

        node_results.append(
            {
                "stage": node["stage"],
                "port": node["port"],
                "flash_capacity_gate": (
                    local_manifest["flash"]["free_before_reserve_bytes"]
                    >= local_manifest["flash"]["required_reserve_bytes"]
                ),
                "psram_capacity_gate": local_manifest["psram"]["free_bytes"] >= 0,
            }
        )

    expected = {
        name
        for name in state
        if name not in {"model.embed_tokens.weight", "lm_head.weight"}
    }
    if covered != expected:
        missing = sorted(expected - covered)
        extra = sorted(covered - expected)
        raise RuntimeError(f"tensor coverage mismatch: missing={missing}, extra={extra}")

    result = {
        "schema": "paretoq125m.ssos.export-verification.v1",
        "checkpoint_sha256": manifest["source"]["sha256"],
        "tensor_records_verified": tensor_count,
        "model_values_verified": value_count,
        "transformer_exact": True,
        "embedding_head_byte_identical": True,
        "vocabulary_exact": True,
        "file_hashes_exact": True,
        "tensor_coverage_exact": True,
        "nodes": node_results,
    }
    (export_root / "verification.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--export", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.checkpoint, args.export), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
