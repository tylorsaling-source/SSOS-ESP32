#!/usr/bin/env python3
"""Fail-closed verification for the clean six-board proof package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROMPTS = [f"p{number:02d}" for number in range(1, 6)]
MODES = ("fast", "regular")


def sha256(path: Path) -> str:
    if path.suffix.lower() != ".bin":
        return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksums(package: Path) -> int:
    entries = (package / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    for entry in entries:
        expected, relative = entry.split("  ", 1)
        path = package / Path(relative)
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"checksum mismatch: {relative}")
    actual = {
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file()
        and path.name != "SHA256SUMS"
        and not {"__pycache__", ".pytest_cache"}.intersection(path.parts)
    }
    listed = {entry.split("  ", 1)[1] for entry in entries}
    if actual != listed:
        raise ValueError(f"checksum inventory mismatch: missing={sorted(actual-listed)}, stale={sorted(listed-actual)}")
    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    package = args.package.resolve()
    checksum_count = verify_checksums(package)

    topology = json.loads((package / "config" / "six_board_topology.json").read_text())
    boards = topology["tested_nodes"]
    if len(boards) != 6 or sum(b["role"].startswith("compute") for b in boards) != 5:
        raise ValueError("topology is not six boards with five compute stages")
    relays = [b for b in boards if b["role"] == "transport-relay"]
    if len(relays) != 1 or relays[0]["tested_port"] != "COM22":
        raise ValueError("COM22 transport relay is absent")
    if any(b["tested_port"] == "COM3" for b in boards):
        raise ValueError("COM3 must not appear in the topology")

    oracle = json.loads((package / "results" / "host" / "oracle.json").read_text())
    proof_path = package / "results" / "physical" / "ab_proof.json"
    proof = json.loads(proof_path.read_text())
    summary = json.loads((package / "results" / "physical" / "ab_proof_summary.json").read_text())
    oracle_by_id = {item["id"]: item for item in oracle["results"]}
    records = proof["records"]
    if len(records) != 10:
        raise ValueError("physical proof must contain ten records")
    exact_tokens = 0
    for mode in MODES:
        selected = [item for item in records if item["mode"] == mode]
        if [item["prompt"] for item in selected] != PROMPTS:
            raise ValueError(f"{mode}: missing or reordered prompt records")
        if f"BENCH_DONE mode={mode} prompts=5 all_exact=1" not in proof["raw"]:
            raise ValueError(f"{mode}: terminal correctness gate absent")
        for item in selected:
            expected = oracle_by_id[item["prompt"]]["output_ids"]
            if item["output_ids"] != expected or item["tokens"] != 24 or not item["exact"]:
                raise ValueError(f"{mode}/{item['prompt']}: output mismatch")
            if item["spi_errors"] != 0:
                raise ValueError(f"{mode}/{item['prompt']}: SPI error gate failed")
            exact_tokens += item["tokens"]
    if exact_tokens != 240 or summary["all_exact"] is not True:
        raise ValueError("combined exact-token gate failed")
    if summary["physical_proof_sha256"] != sha256(proof_path):
        raise ValueError("summary does not identify the packaged physical capture")
    if summary["app_sha256"] != sha256(package / "prebuilt" / "compute" / "application.bin"):
        raise ValueError("summary does not identify the packaged compute firmware")

    print(json.dumps({
        "ok": True,
        "package_version": (package / "VERSION").read_text().strip(),
        "physical_boards": len(boards),
        "compute_stages": 5,
        "transport_relays": 1,
        "prompt_runs": len(records),
        "exact_tokens": exact_tokens,
        "spi_errors": 0,
        "checksummed_files": checksum_count,
    }, indent=2))


if __name__ == "__main__":
    main()
