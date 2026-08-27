#!/usr/bin/env python3
"""Prepare five ESP32 stages and capture the fixed physical A/B proof."""

from __future__ import annotations

import argparse
import base64
import json
import time
from pathlib import Path

import serial


COMPUTE_PORTS = ["COM4", "COM7", "COM8", "COM9", "COM11"]
PORTS = [*COMPUTE_PORTS, "COM22"]
PROMPT_IDS = ["p01", "p02", "p03", "p04", "p05"]
DEFAULT_MODE_TIMEOUT_SECONDS = 43200


def open_port(port: str) -> serial.Serial:
    connection = serial.Serial()
    connection.port = port
    connection.baudrate = 921600
    connection.timeout = 1
    connection.write_timeout = 30
    connection.dtr = False
    connection.rts = False
    connection.open()
    connection.dtr = False
    connection.rts = False
    return connection


def wait_line(connection: serial.Serial, prefix: str, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = connection.readline().decode("utf-8", errors="replace").strip()
        if line.startswith("ERR ") or line.startswith("FATAL "):
            raise RuntimeError(f"{connection.port}: {line}")
        if line and line.startswith(prefix):
            return line
    raise TimeoutError(f"{connection.port}: timeout waiting for {prefix}")


def preload(port: str, payload: Path) -> serial.Serial:
    connection = open_port(port)
    connection.reset_input_buffer()
    connection.write(b"INFO\n")
    wait_line(connection, "INFO ", 10)
    size = payload.stat().st_size
    connection.write(f"LOADBEGIN {size}\n".encode())
    wait_line(connection, "OK LOADBEGIN", 10)
    offset = 0
    with payload.open("rb") as stream:
        for chunk in iter(lambda: stream.read(3072), b""):
            encoded = base64.b64encode(chunk)
            connection.write(f"LOADB64 {offset} ".encode() + encoded + b"\n")
            connection.flush()
            receipt = wait_line(connection, "OK LOADB64", 20)
            offset += len(chunk)
            if f"received={offset}" not in receipt:
                raise RuntimeError(f"{port}: invalid chunk receipt: {receipt}")
    if offset != size:
        raise RuntimeError(f"{port}: payload changed while reading")
    connection.write(b"LOADEND\n")
    wait_line(connection, "OK LOAD", 10)
    return connection


def dump_ring_status(connections: dict[str, serial.Serial]) -> None:
    """Emit one firmware-backed hop receipt from every attached stage."""
    for port in PORTS:
        connection = connections[port]
        connection.reset_input_buffer()
        connection.write(b"INFO\n")
        try:
            line = wait_line(connection, "INFO ", 5)
        except Exception as error:
            line = f"INFO_UNAVAILABLE {type(error).__name__}: {error}"
        print(json.dumps({"port": port, "ring_status": line}), flush=True)


def validate_capture(records: list[dict], raw: list[str], modes: tuple[str, ...]) -> None:
    for requested in modes:
        mode = requested.lower()
        selected = [record for record in records if record.get("mode") == mode]
        ids = [record.get("prompt") for record in selected]
        if ids != PROMPT_IDS:
            raise RuntimeError(f"{mode}: expected prompts {PROMPT_IDS}, observed {ids}")
        for record in selected:
            if record.get("exact") is not True or record.get("tokens") != 24:
                raise RuntimeError(f"{mode}/{record.get('prompt')}: correctness gate failed")
            if record.get("spi_errors") != 0:
                raise RuntimeError(f"{mode}/{record.get('prompt')}: SPI errors present")
            for field in ("ttft_ms", "prompt_to_finish_ms", "decode_tps"):
                if not isinstance(record.get(field), (int, float)) or record[field] <= 0:
                    raise RuntimeError(f"{mode}/{record.get('prompt')}: invalid {field}")
        completion = f"BENCH_DONE mode={mode} prompts=5 all_exact=1"
        if completion not in raw:
            raise RuntimeError(f"{mode}: missing successful completion gate")


def completed_modes(raw: list[str]) -> set[str]:
    """Return modes carrying the firmware's full five-prompt success gate."""
    result = set()
    for mode in ("fast", "regular"):
        if f"BENCH_DONE mode={mode} prompts=5 all_exact=1" in raw:
            result.add(mode)
    return result


def write_capture(path: Path, records: list[dict], raw: list[str], *,
                  complete: bool, requested_modes: tuple[str, ...]) -> None:
    """Atomically persist proof progress without replacing the final proof."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "schema": "paretoq125m.physical-ab.v1",
        "complete": complete,
        "requested_modes": [mode.lower() for mode in requested_modes],
        "records": records,
        "raw": raw,
    }
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def load_capture(path: Path) -> tuple[list[dict], list[str]]:
    payload = json.loads(path.read_text())
    records = payload.get("records")
    raw = payload.get("raw")
    if not isinstance(records, list) or not isinstance(raw, list):
        raise ValueError(f"invalid capture file: {path}")
    return records, raw


def completed_only_capture(records: list[dict], raw: list[str]) -> tuple[list[dict], list[str]]:
    """Discard an interrupted mode so replay cannot create duplicate prompts."""
    complete = completed_modes(raw)
    kept_records = [record for record in records if record.get("mode") in complete]
    kept_raw = [
        f"BENCH_DONE mode={mode} prompts=5 all_exact=1"
        for mode in ("fast", "regular") if mode in complete
    ]
    return kept_records, kept_raw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--modes", nargs="+", choices=("FAST", "REGULAR"),
                        default=("FAST", "REGULAR"))
    parser.add_argument("--mode-timeout-seconds", type=float,
                        default=DEFAULT_MODE_TIMEOUT_SECONDS)
    parser.add_argument("--preflight", choices=("LINK", "BUS"), default="BUS",
                        help="LINK checks a complete zero-error ring lap; BUS also runs model kernels")
    parser.add_argument("--resume-from", type=Path)
    args = parser.parse_args()
    if args.mode_timeout_seconds <= 0:
        parser.error("--mode-timeout-seconds must be positive")
    requested_modes = tuple(args.modes)
    records: list[dict] = []
    raw: list[str] = []
    if args.resume_from:
        records, raw = load_capture(args.resume_from)
        records, raw = completed_only_capture(records, raw)
        for mode in completed_modes(raw):
            validate_capture(records, raw, (mode.upper(),))
    completed = completed_modes(raw)
    proof_dir = args.package / "results" / "physical"
    progress_output = proof_dir / "ab_proof.inprogress.json"
    final_output = proof_dir / "ab_proof.json"
    shards = args.package / "build" / "shards"
    payloads = {}
    for port in COMPUTE_PORTS:
        stage_dir = next(shards.glob(f"stage*-{port.lower()}"))
        payloads[port] = stage_dir / "vocab_psram.bin"
    connections = {}
    try:
        # Each receiver has a bounded firmware-side LOAD deadline.  Sending five
        # multi-megabyte payloads at once oversubscribes the shared USB host and
        # can make otherwise healthy boards time out.  Preload outside the
        # timed benchmark boundary, one acknowledged board at a time.
        for port in COMPUTE_PORTS:
            connections[port] = preload(port, payloads[port])
            print(json.dumps({"port": port, "preloaded": True}), flush=True)
        connections["COM22"] = open_port("COM22")
        connections["COM22"].reset_input_buffer()
        connections["COM22"].write(b"INFO\n")
        wait_line(connections["COM22"], "INFO ", 10)
        print(json.dumps({"port": "COM22", "transport_relay": True}), flush=True)
        for port in PORTS[1:]:
            command = b"STARTLINK\n" if port == "COM22" else b"STARTBUS\n"
            expected = "OK STARTLINK" if port == "COM22" else "OK STARTBUS"
            connections[port].write(command)
            wait_line(connections[port], expected, 10)
        master = connections["COM4"]
        master.write(b"STARTBUS\n")
        wait_line(master, "OK STARTBUS", 10)
        preflight_command = f"{args.preflight}TEST"
        master.write(f"{preflight_command}\n".encode())
        preflight_deadline = time.monotonic() + (60 if args.preflight == "LINK" else 900)
        while time.monotonic() < preflight_deadline:
            line = master.readline().decode("utf-8", errors="replace").strip()
            if not line:
                continue
            print(line, flush=True)
            link_failed = args.preflight == "LINK" and (
                not line.startswith("LINKTEST pass=1") or " spi_errors=0 " not in f" {line} "
            )
            bus_failed = args.preflight == "BUS" and any(marker in line for marker in
                (" reset=0", " collect=0", " embedding=0", " layers=0"))
            if line.startswith("ERR ") or link_failed or bus_failed:
                dump_ring_status(connections)
                raise RuntimeError(f"{args.preflight.lower()} preflight failed: {line}")
            if (args.preflight == "LINK" and line.startswith("LINKTEST pass=1")) or (
                    args.preflight == "BUS" and line == "BUSTEST done"):
                break
        else:
            raise TimeoutError(f"{args.preflight.lower()} preflight timeout")
        write_capture(progress_output, records, raw, complete=False,
                      requested_modes=requested_modes)
        for mode in requested_modes:
            if mode.lower() in completed:
                print(f"RESUME_SKIP mode={mode.lower()} complete=1", flush=True)
                continue
            master.write(f"BENCH {mode}\n".encode())
            deadline = time.monotonic() + args.mode_timeout_seconds
            while time.monotonic() < deadline:
                line = master.readline().decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                raw.append(line)
                print(line, flush=True)
                if line.startswith("{"):
                    records.append(json.loads(line))
                write_capture(progress_output, records, raw, complete=False,
                              requested_modes=requested_modes)
                if line.startswith("BENCH_DONE"):
                    break
            else:
                raise TimeoutError(f"benchmark timeout: {mode}")
        validate_capture(records, raw, requested_modes)
        write_capture(final_output, records, raw, complete=True,
                      requested_modes=requested_modes)
        print(final_output)
    finally:
        for connection in connections.values():
            connection.dtr = False
            connection.rts = False
            connection.close()


if __name__ == "__main__":
    main()
