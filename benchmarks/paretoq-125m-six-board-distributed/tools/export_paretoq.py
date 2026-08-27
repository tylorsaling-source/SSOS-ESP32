#!/usr/bin/env python3
"""Losslessly export Meta ParetoQ MobileLLM 125M into five ESP32 shards."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch


ALIGNMENT = 64
MATRIX_SUFFIXES = (
    "self_attn.q_proj.weight",
    "self_attn.k_proj.weight",
    "self_attn.v_proj.weight",
    "self_attn.o_proj.weight",
    "mlp.gate_proj.weight",
    "mlp.up_proj.weight",
    "mlp.down_proj.weight",
)
NORM_SUFFIXES = (
    "input_layernorm.weight",
    "post_attention_layernorm.weight",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bf16_bytes(tensor: torch.Tensor) -> bytes:
    if tensor.dtype != torch.bfloat16:
        raise ValueError(f"expected BF16, got {tensor.dtype}")
    words = tensor.detach().cpu().contiguous().view(torch.uint16).numpy()
    if sys.byteorder != "little":
        words = words.byteswap()
    return words.tobytes()


def pack_2bit(codes: np.ndarray) -> bytes:
    flat = np.asarray(codes, dtype=np.uint8).reshape(-1)
    if np.any(flat > 3):
        raise ValueError("2-bit codes must be in [0, 3]")
    padding = (-flat.size) % 4
    if padding:
        flat = np.pad(flat, (0, padding), constant_values=0)
    shifts = np.array([0, 2, 4, 6], dtype=np.uint8)
    return np.bitwise_or.reduce(flat.reshape(-1, 4) << shifts, axis=1).tobytes()


def unpack_2bit(packed: bytes, value_count: int) -> np.ndarray:
    values = np.frombuffer(packed, dtype=np.uint8)
    shifts = np.array([0, 2, 4, 6], dtype=np.uint8)
    codes = ((values[:, None] >> shifts[None, :]) & 0x03).astype(np.uint8)
    return codes.reshape(-1)[:value_count]


def pack_four_level_matrix(tensor: torch.Tensor) -> tuple[bytes, bytes, bytes]:
    if tensor.ndim != 2 or tensor.dtype != torch.bfloat16:
        raise ValueError("quantized matrix must be two-dimensional BF16")
    source = tensor.detach().cpu().contiguous().float()
    absolute = source.abs()
    high = absolute.amax(dim=1)
    low = absolute.amin(dim=1)
    if torch.any(low <= 0) or torch.any(low == high):
        raise ValueError("each row must contain exactly two nonzero magnitudes")
    is_high = absolute == high[:, None]
    is_low = absolute == low[:, None]
    if not torch.all(is_high | is_low):
        mismatches = int(torch.count_nonzero(~(is_high | is_low)))
        raise ValueError(f"matrix is not exactly four-level: {mismatches} values")
    negative = source < 0
    # 0=-high, 1=-low, 2=+low, 3=+high.
    codes = torch.where(
        negative,
        torch.where(is_high, 0, 1),
        torch.where(is_high, 3, 2),
    ).to(torch.uint8)
    low_bf16 = low.to(torch.bfloat16)
    high_bf16 = high.to(torch.bfloat16)
    reconstructed = torch.where(
        codes == 0, -high_bf16.float()[:, None],
        torch.where(
            codes == 1, -low_bf16.float()[:, None],
            torch.where(codes == 2, low_bf16.float()[:, None], high_bf16.float()[:, None]),
        ),
    )
    if not torch.equal(reconstructed, source):
        mismatches = int(torch.count_nonzero(reconstructed != source))
        raise ValueError(f"lossless four-level reconstruction failed: {mismatches} mismatches")
    return pack_2bit(codes.numpy()), bf16_bytes(low_bf16), bf16_bytes(high_bf16)


def aligned_write(stream, payload: bytes) -> tuple[int, int, str]:
    padding = (-stream.tell()) % ALIGNMENT
    if padding:
        stream.write(bytes(padding))
    offset = stream.tell()
    stream.write(payload)
    return offset, len(payload), hashlib.sha256(payload).hexdigest()


def layer_keys(state: dict[str, torch.Tensor], first: int, last: int) -> list[str]:
    keys: list[str] = []
    for layer in range(first, last + 1):
        prefix = f"model.layers.{layer}."
        for suffix in MATRIX_SUFFIXES + NORM_SUFFIXES:
            name = prefix + suffix
            if name not in state:
                raise KeyError(name)
            keys.append(name)
    return keys


def export_node(
    state: dict[str, torch.Tensor],
    embedding: torch.Tensor,
    node: dict,
    layout: dict,
    output_root: Path,
) -> dict:
    stage = int(node["stage"])
    node_root = output_root / f"stage{stage}-{node['port'].lower()}"
    node_root.mkdir(parents=True, exist_ok=True)
    layer_path = node_root / "layers.bin"
    records: list[dict] = []

    keys = layer_keys(state, int(node["layer_first"]), int(node["layer_last"]))
    if stage == len(layout["nodes"]) - 1:
        keys.append("model.norm.weight")

    with layer_path.open("wb") as stream:
        for name in keys:
            tensor = state[name]
            if tensor.ndim == 2:
                codes, low_scales, high_scales = pack_four_level_matrix(tensor)
                code_offset, code_bytes, code_sha = aligned_write(stream, codes)
                low_scale_offset, low_scale_bytes, low_scale_sha = aligned_write(stream, low_scales)
                high_scale_offset, high_scale_bytes, high_scale_sha = aligned_write(stream, high_scales)
                records.append(
                    {
                        "name": name,
                        "kind": "four_level_2bit_matrix",
                        "shape": list(tensor.shape),
                        "code_offset": code_offset,
                        "code_bytes": code_bytes,
                        "code_sha256": code_sha,
                        "low_scale_offset": low_scale_offset,
                        "low_scale_bytes": low_scale_bytes,
                        "low_scale_sha256": low_scale_sha,
                        "high_scale_offset": high_scale_offset,
                        "high_scale_bytes": high_scale_bytes,
                        "high_scale_sha256": high_scale_sha,
                    }
                )
            else:
                payload = bf16_bytes(tensor)
                offset, size, digest = aligned_write(stream, payload)
                records.append(
                    {
                        "name": name,
                        "kind": "bfloat16",
                        "shape": list(tensor.shape),
                        "offset": offset,
                        "bytes": size,
                        "sha256": digest,
                    }
                )

    layer_bytes = layer_path.stat().st_size
    partition_bytes = int(layout["model_partition_bytes"])
    reserve_bytes = int(layout["model_partition_reserve_bytes"])
    flash_sector_bytes = 4096
    vocab_flash_offset = (
        (layer_bytes + flash_sector_bytes - 1) // flash_sector_bytes
    ) * flash_sector_bytes
    flash_vocab_budget = partition_bytes - reserve_bytes - vocab_flash_offset
    row_bytes = int(embedding.shape[1]) * 2
    if flash_vocab_budget < 0:
        raise RuntimeError(f"stage {stage} layers exceed its flash budget")

    vocab_first = int(node["vocab_first"])
    vocab_count = int(node["vocab_count"])
    flash_rows = min(vocab_count, flash_vocab_budget // row_bytes)
    psram_rows = vocab_count - flash_rows
    vocab = embedding[vocab_first : vocab_first + vocab_count].contiguous()
    flash_payload = bf16_bytes(vocab[:flash_rows])
    psram_payload = bf16_bytes(vocab[flash_rows:])
    flash_path = node_root / "vocab_flash.bin"
    psram_path = node_root / "vocab_psram.bin"
    flash_path.write_bytes(flash_payload)
    psram_path.write_bytes(psram_payload)

    local_layers = int(node["layer_last"]) - int(node["layer_first"]) + 1
    kv_bytes = (
        2
        * local_layers
        * int(layout["context_tokens"])
        * int(layout["num_kv_heads"])
        * int(layout["head_dim"])
        * 2
    )
    workspace_bytes = int(layout["psram_workspace_reserve_bytes"])
    psram_total = len(psram_payload) + kv_bytes + workspace_bytes
    flash_used_bytes = vocab_flash_offset + len(flash_payload)
    if flash_used_bytes + reserve_bytes > partition_bytes:
        raise RuntimeError(f"stage {stage} flash capacity gate failed")
    if psram_total > int(layout["psram_bytes"]):
        raise RuntimeError(f"stage {stage} PSRAM capacity gate failed")

    result = {
        "stage": stage,
        "port": node["port"],
        "mac": node["mac"],
        "layers": [int(node["layer_first"]), int(node["layer_last"])],
        "vocab": {
            "first": vocab_first,
            "count": vocab_count,
            "flash_rows": flash_rows,
            "psram_rows": psram_rows,
            "row_bytes": row_bytes,
        },
        "flash": {
            "partition_bytes": partition_bytes,
            "required_reserve_bytes": reserve_bytes,
            "layers_bytes": layer_bytes,
            "vocab_flash_offset": vocab_flash_offset,
            "alignment_gap_bytes": vocab_flash_offset - layer_bytes,
            "vocab_bytes": len(flash_payload),
            "used_bytes": flash_used_bytes,
            "free_before_reserve_bytes": partition_bytes - flash_used_bytes,
        },
        "psram": {
            "capacity_bytes": int(layout["psram_bytes"]),
            "vocab_bytes": len(psram_payload),
            "kv_bytes": kv_bytes,
            "workspace_reserve_bytes": workspace_bytes,
            "used_bytes": psram_total,
            "free_bytes": int(layout["psram_bytes"]) - psram_total,
        },
        "files": {
            "layers.bin": {"bytes": layer_bytes, "sha256": sha256_file(layer_path)},
            "vocab_flash.bin": {"bytes": len(flash_payload), "sha256": sha256_file(flash_path)},
            "vocab_psram.bin": {"bytes": len(psram_payload), "sha256": sha256_file(psram_path)},
        },
        "records": records,
    }
    (node_root / "manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def export(checkpoint: Path, layout_path: Path, output_root: Path) -> dict:
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    state = torch.load(checkpoint, map_location="cpu", weights_only=True, mmap=True)
    embedding = state["model.embed_tokens.weight"].detach().cpu().contiguous()
    head = state["lm_head.weight"].detach().cpu().contiguous()
    if not torch.equal(embedding, head):
        raise RuntimeError("input embedding and output head are not byte-identical")
    if sum(int(n["vocab_count"]) for n in layout["nodes"]) != int(embedding.shape[0]):
        raise RuntimeError("vocabulary shard counts do not cover the model vocabulary")
    expected_first = 0
    for node in layout["nodes"]:
        if int(node["vocab_first"]) != expected_first:
            raise RuntimeError("vocabulary ranges are not contiguous")
        expected_first += int(node["vocab_count"])

    output_root.mkdir(parents=True, exist_ok=True)
    nodes = [export_node(state, embedding, node, layout, output_root) for node in layout["nodes"]]
    manifest = {
        "schema": "paretoq125m.ssos.export.v1",
        "model_id": layout["model_id"],
        "model_revision": layout["model_revision"],
        "source": {
            "checkpoint": str(checkpoint),
            "bytes": checkpoint.stat().st_size,
            "sha256": sha256_file(checkpoint),
        },
        "lossless_transformer_reconstruction": True,
        "shared_embedding_and_head": True,
        "nodes": nodes,
    }
    (output_root / "export_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = export(args.checkpoint, args.layout, args.output)
    summary = {
        "source_sha256": manifest["source"]["sha256"],
        "nodes": [
            {
                "stage": node["stage"],
                "flash_used": node["flash"]["used_bytes"],
                "flash_free_before_reserve": node["flash"]["free_before_reserve_bytes"],
                "psram_used": node["psram"]["used_bytes"],
                "psram_free": node["psram"]["free_bytes"],
            }
            for node in manifest["nodes"]
        ],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
