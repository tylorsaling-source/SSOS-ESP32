from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import urllib.parse
import urllib.request
from pathlib import Path

from tokenizers import ByteLevelBPETokenizer


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOMAIN = ROOT / "domain"
SPECIAL = ["<bos>", "<pad>", "<eos>", "<unk>"]
BLOCKED = ("once upon a time", "magical kingdom", "little fairy")
DOMAIN_PHRASES = (
    "first aid", "wound", "bleeding", "infection", "hypothermia", "heat exhaustion",
    "shelter", "insulation", "foundation", "roof", "structural", "load bearing",
    "potable water", "water treatment", "purification", "filter", "boil", "contamination",
    "navigation", "compass", "bearing", "landmark", "route", "map", "coordinate",
    "construct", "repair", "fastener", "joint", "brace", "beam", "tool", "material",
    "fire safety", "fuel", "ventilation", "combustion", "extinguish",
    "food storage", "agriculture", "forage", "ration", "supply",
    "emergency", "hazard", "risk", "evacuate", "rescue", "warning",
    "cooperation", "negotiate", "conflict", "signal", "communication", "coordinate",
    "weather", "storm", "flood", "drought", "animal", "ecosystem",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def sentences(text: str) -> list[str]:
    return [clean(x) for x in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", clean(text)) if len(clean(x).split()) >= 5]


def windows(text: str, domain_only: bool) -> list[str]:
    parts = sentences(text)
    found: list[str] = []
    for i in range(len(parts)):
        window = " ".join(parts[i : i + 3])
        words = window.split()
        lower = window.lower()
        if not 35 <= len(words) <= 190 or any(term in lower for term in BLOCKED):
            continue
        if domain_only and not any(term in lower for term in DOMAIN_PHRASES):
            continue
        found.append(window)
    return found


def fetch_rows(dataset: str, config: str, count: int):
    base = "https://datasets-server.huggingface.co/rows"
    for offset in range(0, count, 100):
        query = urllib.parse.urlencode({"dataset": dataset, "config": config, "split": "train", "offset": offset, "length": min(100, count - offset)})
        with urllib.request.urlopen(f"{base}?{query}", timeout=90) as response:
            payload = json.load(response)
        for wrapped in payload.get("rows", []):
            row = wrapped.get("row", {})
            text = row.get("text") or row.get("content") or ""
            if text:
                yield text


def unique(rows: list[str]) -> list[str]:
    seen = set()
    output = []
    for row in rows:
        key = hashlib.blake2s(row.lower().encode(), digest_size=12).digest()
        if key not in seen:
            seen.add(key)
            output.append(row)
    return output


def take_chars(rows: list[str], limit: int) -> list[str]:
    output, total = [], 0
    for row in rows:
        if total >= limit:
            break
        output.append(row)
        total += len(row)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DATA / "source-broad-corpus.txt")
    parser.add_argument("--simple-wikipedia-rows", type=int, default=1500)
    parser.add_argument("--chars-per-stream", type=int, default=4_000_000)
    parser.add_argument("--seed", type=int, default=550984)
    args = parser.parse_args()
    if not args.source.exists():
        raise SystemExit(f"missing broad source corpus: {args.source}")
    random.seed(args.seed)

    domain_rows: list[str] = []
    for document in args.source.read_text(encoding="utf-8", errors="ignore").split("\n\n<eos>\n\n"):
        domain_rows.extend(windows(document, domain_only=True))
    for path in sorted(DOMAIN.glob("*.txt")):
        authored = windows(path.read_text(encoding="utf-8", errors="ignore"), domain_only=False)
        domain_rows.extend(authored * 12)
    domain_rows = unique(domain_rows)

    general_rows: list[str] = []
    for document in fetch_rows("wikimedia/wikipedia", "20231101.simple", args.simple_wikipedia_rows):
        general_rows.extend(windows(document, domain_only=False))
    general_rows = unique(general_rows)
    random.shuffle(domain_rows)
    random.shuffle(general_rows)
    domain_rows = take_chars(domain_rows, args.chars_per_stream)
    general_rows = take_chars(general_rows, args.chars_per_stream)
    balance = min(sum(map(len, domain_rows)), sum(map(len, general_rows)))
    domain_rows = take_chars(domain_rows, balance)
    general_rows = take_chars(general_rows, balance)
    mixed = []
    for i in range(max(len(domain_rows), len(general_rows))):
        if i < len(domain_rows): mixed.append(domain_rows[i])
        if i < len(general_rows): mixed.append(general_rows[i])
    corpus = DATA / "corpus.txt"
    corpus.write_text("\n\n<eos>\n\n".join(mixed), encoding="utf-8")

    tokenizer = ByteLevelBPETokenizer()
    tokenizer.train(files=[str(corpus)], vocab_size=940, min_frequency=2, special_tokens=SPECIAL)
    tokenizer.save_model(str(DATA), "ssos-550k")
    domain_chars = sum(map(len, domain_rows))
    general_chars = sum(map(len, general_rows))
    manifest = {
        "format": "ssos.language.curriculum.v2",
        "design": "adult domain windows plus Simple English; no TinyStories",
        "domain_windows": len(domain_rows),
        "general_windows": len(general_rows),
        "domain_characters": domain_chars,
        "general_characters": general_chars,
        "domain_fraction_by_characters": domain_chars / max(1, domain_chars + general_chars),
        "characters": domain_chars + general_chars,
        "vocab_size": tokenizer.get_vocab_size(),
        "corpus_sha256": sha256(corpus),
        "vocab_sha256": sha256(DATA / "ssos-550k-vocab.json"),
        "merges_sha256": sha256(DATA / "ssos-550k-merges.txt"),
    }
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
