#!/usr/bin/env python3
"""Fail-closed physical validation for the SSOS-ESP32 V2 packet-backed head."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version as package_version
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Callable


MODEL_RE = re.compile(
    r"^OK model ready=1 source=packet-bank encoding=q10 rows=8 dims=9 outputs=8 weights=72$"
)
INFER_RE = re.compile(r"^OK model y8=([^ ]+) argmax=(\d+)$")
MAC_RE = re.compile(r"MAC:\s*([0-9A-Fa-f:]{17})")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_fixture(path: Path) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if fixture.get("schema") != "ssos.v2.hardware-fixture.v1":
        raise ValueError("unsupported fixture schema")
    rows = fixture.get("rows_q10")
    vectors = fixture.get("vectors")
    if not isinstance(rows, list) or len(rows) != 8 or any(len(row) != 9 for row in rows):
        raise ValueError("fixture must contain exactly 8 rows of 9 Q10 values")
    if any(not isinstance(value, int) or value < -8192 or value > 8192 for row in rows for value in row):
        raise ValueError("fixture contains an invalid signed-Q10 value")
    if not isinstance(vectors, list) or len(vectors) < 3:
        raise ValueError("fixture must contain at least three test vectors")
    for vector in vectors:
        if len(vector.get("input9", [])) != 9 or len(vector.get("expected_y8", [])) != 8:
            raise ValueError("every fixture vector must contain input9 and expected_y8")
        calculated = [sum((rows[r][c] / 1024.0) * vector["input9"][c] for c in range(9)) for r in range(8)]
        if any(abs(a - b) > 1e-12 for a, b in zip(calculated, vector["expected_y8"])):
            raise ValueError(f"fixture expected values are stale for {vector.get('name', 'unnamed')}")
        if max(range(8), key=calculated.__getitem__) != vector.get("expected_argmax"):
            raise ValueError(f"fixture argmax is stale for {vector.get('name', 'unnamed')}")
    return fixture


def parse_inference(line: str) -> tuple[list[float], int]:
    match = INFER_RE.match(line)
    if not match:
        raise ValueError(f"unexpected inference response: {line!r}")
    values = [float(value) for value in match.group(1).split(",")]
    if len(values) != 8:
        raise ValueError(f"device returned {len(values)} outputs instead of 8")
    return values, int(match.group(2))


class Transcript:
    def __init__(self, path: Path):
        self.path = path
        self._stream = path.open("w", encoding="utf-8", newline="\n")

    def write(self, direction: str, text: str) -> None:
        stamp = datetime.now(timezone.utc).isoformat()
        self._stream.write(f"{stamp} {direction} {text}\n")
        self._stream.flush()

    def close(self) -> None:
        self._stream.close()


class Device:
    def __init__(self, port: str, transcript: Transcript, timeout: float = 5.0):
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("PySerial is missing. Run: py -3 -m pip install pyserial") from exc
        self.serial_module = serial
        self.port = port
        self.transcript = transcript
        self.timeout = timeout
        self.device: Any = None

    def open(self) -> None:
        self.device = self.serial_module.Serial(
            self.port, 115200, timeout=0.25, write_timeout=3, dsrdtr=False, rtscts=False
        )
        self.device.dtr = False
        self.device.rts = False
        time.sleep(0.7)
        self.drain()

    def close(self) -> None:
        if self.device is not None:
            self.device.close()
            self.device = None

    def drain(self) -> None:
        if self.device is None:
            return
        while self.device.in_waiting:
            line = self.device.readline().decode("ascii", errors="replace").strip()
            if line:
                self.transcript.write("RX", line)

    def command(self, command: str, accept: Callable[[str], bool], timeout: float | None = None) -> str:
        if self.device is None:
            raise RuntimeError("serial device is not open")
        self.transcript.write("TX", command)
        self.device.write((command + "\n").encode("ascii"))
        self.device.flush()
        deadline = time.monotonic() + (timeout or self.timeout)
        while time.monotonic() < deadline:
            line = self.device.readline().decode("ascii", errors="replace").strip()
            if not line:
                continue
            self.transcript.write("RX", line)
            if line.startswith("ERR "):
                raise RuntimeError(f"board rejected {command!r}: {line}")
            if accept(line):
                return line
        raise TimeoutError(f"no expected response for {command!r}")


def exact(expected: str) -> Callable[[str], bool]:
    return lambda line: line == expected


def prefix(expected: str) -> Callable[[str], bool]:
    return lambda line: line.startswith(expected)


def identify(device: Device) -> str:
    line = device.command("ID", prefix("OK SSOS_ESP32 "))
    if "proto=ssos.packet.v1" not in line or "fuse=9to8" not in line or "chip=esp32s3" not in line:
        raise RuntimeError(f"wrong firmware or board identity: {line}")
    return line


def require_model(device: Device) -> str:
    return device.command("MODEL", lambda line: bool(MODEL_RE.match(line)))


def run_vectors(device: Device, fixture: dict[str, Any], tolerance: float, phase: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for vector in fixture["vectors"]:
        input_text = ",".join(format(float(value), ".12g") for value in vector["input9"])
        line = device.command(f"MINFER x={input_text}", prefix("OK model y8="))
        actual, actual_argmax = parse_inference(line)
        errors = [abs(a - e) for a, e in zip(actual, vector["expected_y8"])]
        maximum_error = max(errors)
        passed = maximum_error <= tolerance and actual_argmax == vector["expected_argmax"]
        result = {
            "phase": phase,
            "name": vector["name"],
            "input9": vector["input9"],
            "expected_y8": vector["expected_y8"],
            "observed_y8": actual,
            "expected_argmax": vector["expected_argmax"],
            "observed_argmax": actual_argmax,
            "max_abs_error": maximum_error,
            "pass": passed,
        }
        results.append(result)
        if not passed:
            raise RuntimeError(
                f"{phase}/{vector['name']} failed: max error {maximum_error:.9g}, "
                f"argmax expected {vector['expected_argmax']} observed {actual_argmax}"
            )
        print(f"      PASS {vector['name']}: 8/8 outputs, max error {maximum_error:.3g}", flush=True)
    return results


def install_rows(device: Device, fixture: dict[str, Any]) -> None:
    device.command("MCLEAR", prefix("OK model packets cleared"))
    for row_index, row in enumerate(fixture["rows_q10"]):
        body = ",".join(str(value) for value in row)
        command = (
            f"PKT id=model:w:{row_index} d=120,{row_index},0,0,0,0,0,0,0 "
            f"role=runtime perm=open body={body}"
        )
        device.command(command, prefix(f"OK recv PKT id=model:w:{row_index}"))
    device.command("MLOAD", exact("OK model loaded from packet bank"))
    require_model(device)


def hard_reset_with_esptool(port: str, transcript: Transcript) -> str:
    command = [
        sys.executable, "-m", "esptool", "--chip", "esp32s3", "--port", port,
        "--before", "default-reset", "--after", "hard-reset", "read-mac",
    ]
    transcript.write("HOST", " ".join(command))
    completed = subprocess.run(command, capture_output=True, text=True, timeout=45)
    output = (completed.stdout + "\n" + completed.stderr).strip()
    for line in output.splitlines():
        transcript.write("ESPTOOL", line)
    if completed.returncode != 0:
        raise RuntimeError(f"non-writing reset/read-mac failed with exit code {completed.returncode}")
    match = MAC_RE.search(output)
    if not match:
        raise RuntimeError("esptool did not report the board MAC")
    return match.group(1).upper()


def git_commit(repo_root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"], capture_output=True, text=True
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def installed_version(name: str) -> str | None:
    try:
        return package_version(name)
    except PackageNotFoundError:
        return None


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parents[1]
    parser = argparse.ArgumentParser(description="Validate V2 on one physical ESP32-S3")
    parser.add_argument("--port", required=True, help="Windows serial port, for example COM17")
    parser.add_argument("--fixture", type=Path, default=script_dir / "fixture.json")
    parser.add_argument("--output-dir", type=Path, default=script_dir / "results")
    parser.add_argument("--tolerance", type=float, default=0.00002)
    parser.add_argument(
        "--flash-status",
        choices=("performed-this-run", "preexisting"),
        default="preexisting",
        help="records whether the user-facing wrapper flashed this board before validation",
    )
    args = parser.parse_args()

    port = args.port.upper()
    if not re.fullmatch(r"COM\d+", port):
        print(f"FAIL: invalid Windows serial port: {port}", file=sys.stderr)
        return 2
    if port == "COM3":
        print("FAIL: COM3 is protected and this package will never open or flash it.", file=sys.stderr)
        return 2
    if args.tolerance <= 0:
        print("FAIL: tolerance must be positive", file=sys.stderr)
        return 2

    started = datetime.now(timezone.utc)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = args.output_dir / f"v2-physical-{stamp}.json"
    transcript_path = args.output_dir / f"v2-physical-{stamp}.txt"
    transcript = Transcript(transcript_path)
    evidence: dict[str, Any] = {
        "schema": "ssos.v2.physical-evidence.v1",
        "status": "FAIL",
        "started_utc": started.isoformat(),
        "port": port,
        "tolerance": args.tolerance,
        "release": "V2.0.0",
        "target": "ESP32-S3-WROOM-1U N16R8; native USB Serial/JTAG 303A:1001",
        "flash": {
            "status": args.flash_status,
            "mode": "dio",
            "frequency": "80m",
            "size": "16MB",
            "offsets": {
                "0x0000": "ssos_kernel.ino.bootloader.bin",
                "0x8000": "ssos_kernel.ino.partitions.bin",
                "0xe000": "boot_app0.bin",
                "0x10000": "ssos_kernel.ino.bin"
            },
            "read_back_verify": args.flash_status == "performed-this-run",
        },
        "tools": {
            "python": sys.version.split()[0],
            "esptool": installed_version("esptool"),
            "pyserial": installed_version("pyserial"),
        },
        "fixture": {"path": str(args.fixture), "sha256": sha256(args.fixture)},
        "firmware_image": {
            "path": "images/flash/ssos_kernel.ino.bin",
            "sha256": sha256(repo_root / "images" / "flash" / "ssos_kernel.ino.bin"),
        },
        "git_commit": git_commit(repo_root),
        "checks": [],
        "error": None,
    }
    device = Device(port, transcript)
    try:
        fixture = load_fixture(args.fixture)
        print("   1/5 Confirming the board and V2 firmware...", flush=True)
        device.open()
        evidence["identity_before"] = identify(device)

        print("   2/5 Installing all 8 rows (72 signed-Q10 weights)...", flush=True)
        install_rows(device, fixture)

        print("   3/5 Comparing all 8 outputs for three known inputs...", flush=True)
        evidence["checks"].extend(run_vectors(device, fixture, args.tolerance, "before-reset"))
        evidence["save_response"] = device.command("SAVE", exact("OK saved"))
        device.close()

        print("   4/5 Performing a real hard reset and reconnect...", flush=True)
        evidence["board_mac"] = hard_reset_with_esptool(port, transcript)
        time.sleep(2.0)
        last_error: Exception | None = None
        for _ in range(12):
            try:
                device.open()
                last_error = None
                break
            except Exception as exc:  # port can disappear briefly during reset
                last_error = exc
                device.close()
                time.sleep(0.5)
        if last_error is not None:
            raise RuntimeError(f"board did not reconnect after reset: {last_error}")
        evidence["identity_after"] = identify(device)
        require_model(device)

        print("   5/5 Proving saved rows and outputs survived reset...", flush=True)
        evidence["checks"].extend(run_vectors(device, fixture, args.tolerance, "after-reset"))
        evidence["status"] = "PASS"
        print("\nPASS: V2 is physically reproducible on this board.", flush=True)
        print("      72/72 weights loaded; 48/48 output values matched; reset persistence passed.", flush=True)
        print(f"      Evidence: {evidence_path}", flush=True)
        print(f"      Transcript: {transcript_path}", flush=True)
        return 0
    except Exception as exc:
        evidence["error"] = str(exc)
        print(f"\nFAIL: {exc}", file=sys.stderr, flush=True)
        print(f"      Evidence: {evidence_path}", file=sys.stderr, flush=True)
        print(f"      Transcript: {transcript_path}", file=sys.stderr, flush=True)
        return 1
    finally:
        device.close()
        evidence["finished_utc"] = datetime.now(timezone.utc).isoformat()
        evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        transcript.close()


if __name__ == "__main__":
    raise SystemExit(main())
