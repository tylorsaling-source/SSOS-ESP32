import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLASH_BYTES = 16 * 1024 * 1024
MODEL_OFFSET = 0x1A0000
MODEL_BYTES = 0xE60000


def test_five_compute_stage_flash_placement_is_exact_and_bounded():
    layout = json.loads((ROOT / "config" / "five_compute_layout.json").read_text())
    assert [node["port"] for node in layout["nodes"]] == [
        "COM4", "COM7", "COM8", "COM9", "COM11"
    ]
    assert all(node["port"] != "COM3" for node in layout["nodes"])
    assert MODEL_OFFSET + MODEL_BYTES == FLASH_BYTES
    for node in layout["nodes"]:
        stage = node["stage"]
        directory = next((ROOT / "artifacts" / "manifests").glob(f"stage{stage}-com*"))
        manifest = json.loads((directory / "manifest.json").read_text())
        assert manifest["stage"] == stage
        assert manifest["port"] == node["port"]
        assert manifest["files"]["layers.bin"]["bytes"] == manifest["flash"]["layers_bytes"]
        assert manifest["files"]["vocab_flash.bin"]["bytes"] == manifest["flash"]["vocab_bytes"]
        vocab_offset = manifest["flash"]["vocab_flash_offset"]
        assert vocab_offset % 4096 == 0
        assert vocab_offset >= manifest["flash"]["layers_bytes"]
        assert vocab_offset + manifest["flash"]["vocab_bytes"] == manifest["flash"]["used_bytes"]
        assert manifest["flash"]["alignment_gap_bytes"] == vocab_offset - manifest["flash"]["layers_bytes"]
        assert manifest["flash"]["free_before_reserve_bytes"] >= manifest["flash"]["required_reserve_bytes"]
        assert manifest["flash"]["used_bytes"] <= MODEL_BYTES


def test_generated_five_prompt_header_matches_oracle_ids():
    oracle = json.loads((ROOT / "results" / "host" / "oracle.json").read_text())
    header = (ROOT / "firmware" / "generated" / "proof_prompts.h").read_text()
    assert oracle["prompt_count"] == 5
    assert "kProofPromptCount = 5u" in header
    for result in oracle["results"]:
        name = result["id"].upper()
        input_match = re.search(rf"k{name}Input\[\] = \{{([^}}]+)\}}", header)
        output_match = re.search(rf"k{name}Expected\[\] = \{{([^}}]+)\}}", header)
        assert input_match and output_match
        parse = lambda match: [int(value.rstrip("u")) for value in match.group(1).split(", ")]
        assert parse(input_match) == result["input_ids"]
        assert parse(output_match) == result["output_ids"]


def test_fast_host_runtime_is_exact_for_all_five_prompts():
    proof = json.loads((ROOT / "results" / "host" / "host_c_fast.json").read_text())
    assert proof["prompt_count"] == 5
    assert proof["generated_token_count"] == 120
    assert proof["all_exact"] is True
    assert all(item["expected_output_ids"] == item["observed_output_ids"]
               for item in proof["results"])


def test_deployer_requires_exact_six_board_authorization():
    source = (ROOT / "tools" / "deploy_cluster.py").read_text()
    assert 'AUTHORIZATION = "COM4,COM7,COM8,COM9,COM11,COM22"' in source
    assert "exact six-port authorization string required" in source


def test_six_board_topology_is_five_compute_plus_one_relay():
    topology = json.loads((ROOT / "config" / "six_board_topology.json").read_text())
    boards = topology["tested_nodes"]
    assert len(boards) == 6
    assert sum(item["role"].startswith("compute") for item in boards) == 5
    assert sum(item["role"] == "transport-relay" for item in boards) == 1
    assert boards[-1]["tested_port"] == "COM22"
    assert all(item["tested_port"] != "COM3" for item in boards)


def test_master_activation_buffer_is_not_truncated_or_on_loop_stack():
    source = (ROOT / "firmware" / "paretoq_node" / "paretoq_node.ino").read_text()
    assert "uint16_t* hidden_bf16 = g_transfer_hidden_bf16;" in source
    assert "uint16_t final_hidden[kHiddenSize]" not in source
    assert "memcpy(hidden_bf16, response.payload, sizeof(hidden_bf16))" not in source
    assert ("memcpy(hidden_bf16, response.payload, "
            "kHiddenSize * sizeof(uint16_t));") in source


def test_logit_broadcast_keeps_ring_service_live_during_second_core_scan():
    source = (ROOT / "firmware" / "paretoq_node" / "paretoq_node.ino").read_text()
    worker_begin = source.index("void worker_service(void*)")
    worker_end = source.index("uint8_t token_owner", worker_begin)
    worker = source[worker_begin:worker_end]
    assert "local_argmax" not in worker
    assert "void logits_service(void*)" in source
    assert 'xTaskCreatePinnedToCore(logits_service, "pq-logits"' in source
    assert 'xTaskCreatePinnedToCore(worker_service, "pq-spi-worker"' in source
    start = source.index("request.kind == kClusterStartLogits")
    collect = source.index("request.kind == kClusterCollectLogits", start)
    branch = source[start:collect]
    assert "xTaskNotifyGive(g_logits_task)" in branch
