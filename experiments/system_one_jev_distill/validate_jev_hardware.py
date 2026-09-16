"""Check a distilled candidate on existing V2 firmware; no firmware flashing.

This proves numerical execution and persistence, not teacher agreement. The
candidate may have failed its accuracy gate. Original packets are backed up.
This experiment explicitly uses a watchdog reset: the tested Gamer board
stayed silent with the existing RTS hard-reset sequence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "v2_proof", ROOT / "validation/v2-hardware/validate_v2_hardware.py"
)
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)


class Device(proof.Device):
    def open(self):
        # Set inactive control lines before opening to avoid an opening pulse.
        self.device = self.serial_module.Serial(port=None, baudrate=115200,
                                               timeout=.25, write_timeout=3)
        self.device.port = self.port
        self.device.dtr = False
        self.device.rts = False
        self.device.open()
        time.sleep(.7)
        self.drain()

    def command(self, command, accept, timeout=None):
        for attempt in range(3 if command.startswith("MINFER ") else 1):
            try:
                return self._command_once(command, accept, timeout)
            except TimeoutError:
                if not command.startswith("MINFER ") or attempt == 2:
                    raise
                self.retry_count = getattr(self, "retry_count", 0) + 1
                self.transcript.write("RETRY", f"read-only MINFER attempt {attempt + 2}")
                self.device.reset_input_buffer()
                self.device.write(b"\n")
                time.sleep(.05)

    def _command_once(self, command, accept, timeout=None):
        time.sleep(.02)
        self.transcript.write("TX", command)
        self.device.write((command + "\n").encode("ascii"))
        self.device.flush()
        deadline = time.monotonic() + (timeout or self.timeout)
        pending = bytearray()
        while time.monotonic() < deadline:
            # PySerial readline may return a partial line when its short read
            # timeout elapses. Accumulate until LF before accepting a response.
            pending.extend(self.device.readline())
            if not pending.endswith(b"\n"):
                continue
            line = pending.decode("ascii", errors="replace").strip()
            pending.clear()
            if not line:
                continue
            self.transcript.write("RX", line)
            if line.startswith("ERR "):
                raise RuntimeError(f"Board rejected {command!r}: {line}")
            if accept(line):
                return line
        if pending:
            self.transcript.write("RX-PARTIAL", pending.decode("ascii", errors="replace"))
        raise TimeoutError(f"No complete expected response for {command!r}.")


def make_fixture(run: Path, seed: int):
    model = json.loads((run / "distilled/ssos_head_rows.json").read_text())
    rows = [[round(float(value) * 1024) for value in row] for row in model["rows"]]
    records = [json.loads(line) for line in (run / "jev_teacher.jsonl").read_text().splitlines()]
    order = np.random.default_rng(seed).permutation(len(records))
    heldout = order[int(len(records) * .8):]
    vectors = []
    # Nine basis vectors exercise each of the 72 coefficients independently.
    for axis in range(9):
        vectors.append((f"basis-{axis}", [float(i == axis) for i in range(9)]))
    for index in heldout:
        vectors.append((f"heldout-{int(index)}", records[index]["x8"] + [1.0]))
    result = {"schema": "ssos.v2.hardware-fixture.v1", "rows_q10": rows, "vectors": []}
    for name, values in vectors:
        expected = [sum(row[i] / 1024 * values[i] for i in range(9)) for row in rows]
        result["vectors"].append({"name": name, "input9": values, "expected_y8": expected,
                                  "expected_argmax": max(range(8), key=expected.__getitem__)})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--port", required=True)
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args()
    if not proof.re.fullmatch(r"COM\d+", args.port.upper()) or args.port.upper() == "COM3":
        raise SystemExit("Select a valid, non-protected Windows serial port.")
    output = args.run / ("hardware-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir()
    fixture_path = output / "fixture.json"
    fixture_path.write_text(json.dumps(make_fixture(args.run, args.seed), indent=2))
    fixture = proof.load_fixture(fixture_path)
    transcript = proof.Transcript(output / "serial.txt")
    device = Device(args.port, transcript)
    evidence = {"status": "FAIL", "firmware_written": False, "settings_erased": False,
                "reset_method": "esptool watchdog-reset", "port": args.port,
                "fixture_sha256": proof.sha256(fixture_path),
                "model_sha256": proof.sha256(args.run / "distilled/ssos_head_rows.json"),
                "checks": [], "teacher_accuracy_gate": "separate; see distilled/report.json"}
    try:
        device.open()
        before = proof.identify(device)
        if "release=2.0.1" not in before:
            raise RuntimeError("This experiment expects existing V2.0.1 firmware.")
        evidence["identity_before"] = before
        device.command("DUMP", proof.exact("OK end"))
        packets = [line.split(" RX ", 1)[1] for line in transcript.path.read_text().splitlines()
                   if " RX PKT " in line]
        if not packets:
            raise RuntimeError("No original packet backup captured; refusing model replacement.")
        (output / "original-packets.txt").write_text("\n".join(packets) + "\n")
        proof.install_rows(device, fixture)
        evidence["checks"].extend(proof.run_vectors(device, fixture, .00002, "before-reset"))
        evidence["save_response"] = device.command("SAVE", proof.exact("OK saved"))
        device.close()
        result = subprocess.run([
            sys.executable, "-m", "esptool", "--chip", "esp32s3", "--port", args.port,
            "--before", "default-reset", "--after", "watchdog-reset", "read-mac"
        ], capture_output=True, text=True, timeout=45)
        for line in (result.stdout + result.stderr).splitlines():
            transcript.write("ESPTOOL", line)
        if result.returncode:
            raise RuntimeError("Watchdog reset failed.")
        time.sleep(2)
        device.open()
        after = proof.identify(device)
        evidence["identity_after"] = after
        def fields(line):
            return dict(part.split("=", 1) for part in line.split() if "=" in part)
        first, second = fields(before), fields(after)
        if first["mac"] != second["mac"] or first["release"] != second["release"]:
            raise RuntimeError("Device identity changed after reset.")
        if int(second["boots"]) <= int(first["boots"]):
            raise RuntimeError("Boot count did not advance.")
        proof.require_model(device)
        evidence["checks"].extend(proof.run_vectors(device, fixture, .00002, "after-reset"))
        evidence["status"] = "PASS"
        evidence["values_compared"] = len(evidence["checks"]) * 8
        evidence["max_abs_error"] = max(item["max_abs_error"] for item in evidence["checks"])
        print(f"PASS: {evidence['values_compared']} numerical outputs and reset persistence; firmware unchanged.")
    except Exception as exc:
        evidence["error"] = str(exc)
        print(f"FAIL: {exc}")
    finally:
        evidence["readonly_inference_retries"] = getattr(device, "retry_count", 0)
        device.close()
        transcript.close()
        (output / "evidence.json").write_text(json.dumps(evidence, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
