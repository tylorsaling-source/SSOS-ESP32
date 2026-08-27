import json
import sys
from pathlib import Path

import numpy as np
import pytest
import torch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from export_paretoq import bf16_bytes, pack_2bit, pack_four_level_matrix, unpack_2bit


def test_all_2bit_groups_round_trip():
    codes = np.tile(np.arange(4, dtype=np.uint8), 257)
    packed = pack_2bit(codes)
    assert len(packed) == (codes.size + 3) // 4
    np.testing.assert_array_equal(unpack_2bit(packed, codes.size), codes)


def test_exact_four_level_matrix():
    matrix = torch.tensor(
        [[-0.25, -0.125, 0.125, 0.25, -0.25],
         [0.5, 0.25, -0.25, -0.5, 0.25]], dtype=torch.bfloat16
    )
    packed, low_bytes, high_bytes = pack_four_level_matrix(matrix)
    codes = torch.from_numpy(unpack_2bit(packed, matrix.numel()).reshape(matrix.shape))
    low = torch.frombuffer(bytearray(low_bytes), dtype=torch.bfloat16).float()
    high = torch.frombuffer(bytearray(high_bytes), dtype=torch.bfloat16).float()
    recovered = torch.where(
        codes == 0, -high[:, None],
        torch.where(codes == 1, -low[:, None],
                    torch.where(codes == 2, low[:, None], high[:, None])),
    ).to(torch.bfloat16)
    assert torch.equal(recovered, matrix)


def test_non_four_level_matrix_is_rejected():
    matrix = torch.tensor([[0.125, 0.25, 0.5, -0.125]], dtype=torch.bfloat16)
    with pytest.raises(ValueError, match="not exactly four-level"):
        pack_four_level_matrix(matrix)


def test_bf16_bytes_are_lossless():
    source = torch.tensor([1.0, -0.5, 0.0, 3.25], dtype=torch.bfloat16)
    recovered = torch.frombuffer(bytearray(bf16_bytes(source)), dtype=torch.bfloat16)
    assert torch.equal(source, recovered)


def test_layout_covers_layers_and_vocabulary_once():
    layout = json.loads((ROOT / "config" / "five_compute_layout.json").read_text())
    layers = []
    vocab = []
    for node in layout["nodes"]:
        layers.extend(range(node["layer_first"], node["layer_last"] + 1))
        vocab.extend(range(node["vocab_first"], node["vocab_first"] + node["vocab_count"]))
    assert layers == list(range(30))
    assert vocab == list(range(32000))
    assert layout["spi_hz"] == 40_000_000
