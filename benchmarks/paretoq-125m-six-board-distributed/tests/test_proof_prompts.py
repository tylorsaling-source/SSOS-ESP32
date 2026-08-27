import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_proof_prompt_contract():
    corpus = json.loads((ROOT / "config" / "proof_prompts.json").read_text())
    prompts = corpus["prompts"]
    assert len(prompts) == 5
    assert len({item["id"] for item in prompts}) == 5
    assert all(item["text"] and item["text"] == item["text"].strip() for item in prompts)
    assert corpus["decode"] == {
        "method": "greedy",
        "max_new_tokens": 24,
        "do_sample": False,
        "use_cache": True,
        "bos_token_id": 1,
        "eos_token_id": 2,
        "pad_token_id": 2,
    }
