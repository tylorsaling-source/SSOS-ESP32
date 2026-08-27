#!/usr/bin/env python3
"""Plan or perform the six-board ParetoQ deployment."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path


EXPECTED = {
    "COM4": "e8:f6:0a:a3:6e:98",
    "COM7": "14:c1:9f:da:49:c8",
    "COM8": "14:c1:9f:da:31:2c",
    "COM9": "14:c1:9f:d9:f7:a8",
    "COM11": "14:c1:9f:db:18:54",
    "COM22": "90:70:69:19:bd:cc",
}
AUTHORIZATION = "COM4,COM7,COM8,COM9,COM11,COM22"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str]) -> str:
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return completed.stdout + completed.stderr


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--authorization", default="")
    args = parser.parse_args()
    if args.execute and args.authorization != AUTHORIZATION:
        raise SystemExit("exact six-port authorization string required")
    compute_build = args.package / "prebuilt" / "compute"
    relay_build = args.package / "prebuilt" / "relay"
    shards = args.package / "build" / "shards"
    common = [
        (0x0, compute_build / "bootloader.bin"),
        (0x8000, compute_build / "partitions.bin"),
        (0xE000, compute_build / "boot_app0.bin"),
        (0x10000, compute_build / "application.bin"),
    ]
    layout = json.loads((args.package / "config" / "five_compute_layout.json").read_text())
    plan = []
    for node in layout["nodes"]:
        port = node["port"]
        stage_dir = next(shards.glob(f"stage{node['stage']}-com*"))
        manifest = json.loads((stage_dir / "manifest.json").read_text())
        model_offset = 0x1A0000
        vocab_flash_offset = int(manifest["flash"]["vocab_flash_offset"])
        files = common + [
            (model_offset, stage_dir / "layers.bin"),
            (model_offset + vocab_flash_offset,
             stage_dir / "vocab_flash.bin"),
        ]
        plan.append({
            "stage": node["stage"], "role": "compute", "port": port,
            "expected_mac": EXPECTED[port],
            "files": [{"offset": offset, "path": str(path), "bytes": path.stat().st_size,
                       "sha256": sha256(path)} for offset, path in files],
        })
    relay_files = [
        (0x0, relay_build / "bootloader.bin"),
        (0x8000, relay_build / "partitions.bin"),
        (0xE000, relay_build / "boot_app0.bin"),
        (0x10000, relay_build / "application.bin"),
    ]
    plan.append({
        "stage": 5, "role": "transport-relay", "port": "COM22",
        "expected_mac": EXPECTED["COM22"],
        "files": [{"offset": offset, "path": str(path), "bytes": path.stat().st_size,
                   "sha256": sha256(path)} for offset, path in relay_files],
    })
    print(json.dumps({"execute": args.execute, "authorization": AUTHORIZATION, "plan": plan}, indent=2))
    if not args.execute:
        return
    receipts = []
    esptool = [str(args.python), "-m", "esptool"]
    for item in plan:
        port = item["port"]
        identity = run([*esptool, "--chip", "esp32s3", "--port", port, "flash-id"])
        if f"MAC:                {item['expected_mac']}".lower() not in identity.lower():
            raise RuntimeError(f"{port} MAC mismatch")
        pairs = []
        for file_item in item["files"]:
            pairs.extend([hex(file_item["offset"]), file_item["path"]])
        write_output = run([*esptool, "--chip", "esp32s3", "--port", port,
            "--baud", "921600", "write-flash", "--flash-mode", "dio",
            "--flash-freq", "80m", "--flash-size", "16MB", *pairs])
        verify_output = run([*esptool, "--chip", "esp32s3", "--port", port,
            "verify-flash", *pairs])
        receipts.append({"port": port, "stage": item["stage"], "files": item["files"],
                         "write_tail": write_output[-1200:], "verify_tail": verify_output[-1200:]})
    output = args.package / "results" / "physical" / "deployment_receipts.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"created_unix": time.time(), "receipts": receipts}, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
