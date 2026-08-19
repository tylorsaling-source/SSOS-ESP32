from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from tokenizers import ByteLevelBPETokenizer


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def fetch_rows(dataset: str, config: str, count: int):
    base = "https://datasets-server.huggingface.co/rows"
    for offset in range(0, count, 100):
        query = urllib.parse.urlencode({
            "dataset": dataset,
            "config": config,
            "split": "train",
            "offset": offset,
            "length": min(100, count - offset),
        })
        with urllib.request.urlopen(f"{base}?{query}", timeout=90) as response:
            payload = json.load(response)
        for wrapped in payload.get("rows", []):
            row = wrapped.get("row", {})
            text = row.get("text") or row.get("content") or ""
            if text:
                yield text


def clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def acceptable(text: str) -> bool:
    lower = text.lower()
    blocked = ("once upon a time", "little fairy", "magical kingdom")
    return len(text) >= 500 and not any(term in lower for term in blocked)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fineweb-rows", type=int, default=300)
    parser.add_argument("--wikipedia-rows", type=int, default=100)
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    local_dir = DATA / "local"
    local_dir.mkdir(exist_ok=True)
    corpus = DATA / "corpus.txt"

    documents: list[str] = []
    documents.extend(fetch_rows("HuggingFaceFW/fineweb-edu", "sample-10BT", args.fineweb_rows))
    documents.extend(fetch_rows("wikimedia/wikipedia", "20231101.en", args.wikipedia_rows))
    domain_dir = ROOT / "domain"
    domain_documents = [path.read_text(encoding="utf-8", errors="ignore") for path in sorted(domain_dir.glob("*.txt"))]
    local_documents = [path.read_text(encoding="utf-8", errors="ignore") for path in sorted(local_dir.glob("*.txt"))]
    # Domain documents receive 4x sampling weight without modifying their text.
    documents.extend((domain_documents + local_documents) * 4)
    filtered = [clean(text) for text in documents if acceptable(clean(text))]
    corpus.write_text("\n\n<eos>\n\n".join(filtered), encoding="utf-8")

    tokenizer = ByteLevelBPETokenizer()
    tokenizer.train(
        files=[str(corpus)],
        vocab_size=940,
        min_frequency=2,
        special_tokens=["<bos>", "<pad>", "<eos>", "<unk>"],
    )
    tokenizer.save_model(str(DATA), "ssos-550k")
    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    manifest = {
        "format": "ssos.language.corpus.v1",
        "fineweb_rows_requested": args.fineweb_rows,
        "wikipedia_rows_requested": args.wikipedia_rows,
        "bundled_domain_documents": len(domain_documents),
        "local_documents": len(local_documents),
        "documents_kept": len(filtered),
        "characters": sum(len(text) for text in filtered),
        "vocab_size": tokenizer.get_vocab_size(),
        "child_story_openings_blocked": True,
        "corpus_sha256": sha256(corpus),
        "vocab_sha256": sha256(DATA / "ssos-550k-vocab.json"),
        "merges_sha256": sha256(DATA / "ssos-550k-merges.txt"),
    }
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
