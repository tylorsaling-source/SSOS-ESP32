# V2 physical proof — one-board Windows path

This is the user-facing path for proving SSOS-ESP32 V2 on one compatible,
fresh board. You do not need to enter packet commands, edit JSON, calculate
expected values, or manually reconnect the serial port.

## Verified run

[2026-09-14: physical PASS](RUN-20260914.md) records 72 loaded coefficients,
48/48 matching scores, `OK saved`, and the same head after a hardware reset.
It includes the original `SAVE` failure on a reused board and the NVS recovery
needed before the passing run. Firmware images are unchanged from V2.0.0.

## What one command does

1. Finds exactly one compatible ESP32-S3 USB Serial/JTAG board.
2. Refuses to continue if the selected port is `COM3`.
3. Checks every release image against its published SHA-256 checksum.
4. Shows the target and asks for one explicit confirmation before flashing.
5. Flashes and read-back verifies the V2 release image.
6. Installs all eight model rows (72 signed-Q10 weights).
7. Compares all eight board outputs for three deterministic inputs.
8. Sends `SAVE`, performs a real non-writing hard reset, reconnects, and runs
   the same comparisons again.
9. Prints a plain-language `PASS` or `FAIL` and saves both machine-readable
   evidence and the complete timestamped serial transcript.

The command never opens or flashes `COM3`.

## Run it

Use Windows 10 or 11, connect one ESP32-S3-WROOM-1U N16R8 by its native USB
Serial/JTAG port, extract the repository ZIP, open PowerShell in its root, and
run:

```powershell
.\scripts\validate-v2-windows.cmd
```

If more than one compatible board is connected, select the intended board:

```powershell
.\scripts\validate-v2-windows.cmd -Port COM17
```

The script checks for Python, Esptool, and PySerial before writing. If a package
is missing it prints the one installation command to run. It does not silently
install software.

## Read the result

A complete success ends with:

```text
PASS: V2 is physically reproducible on this board.
72/72 weights loaded; 48/48 output values matched; reset persistence passed.
```

Proof is written under `validation/v2-hardware/results/`:

- `v2-physical-<time>.json` contains board identity, release and flash settings,
  firmware and fixture hashes, expected and observed values, errors, and each
  gate result.
- `v2-physical-<time>.txt` contains the raw timestamped host, Esptool, and
  serial transcript.

A failed run also writes both files. Do not describe V2 as physically validated
unless the JSON status is `PASS` and the after-reset checks all pass.

## If a reused board reports `ERR save failed`

The flash script replaces its four image regions but preserves NVS. An old
application's NVS state may therefore affect a new installation. In the
[recorded run](RUN-20260914.md), inference passed but `SAVE` failed; clearing
only the release's NVS region resolved it with the same firmware. The exact
old storage condition was not inspected.

Only when discarding the selected board's saved state is intended, initialize
NVS with the following commands, replacing `COM20` with the verified target:

```powershell
python -m esptool --chip esp32s3 --port COM20 --after hard-reset erase-region 0x9000 0x5000
.\scripts\validate-v2-windows.cmd -Port COM20 -SkipFlash
```

This permanently erases the 20 KiB NVS partition. These offsets apply only to
the supplied V2 partition table; do not reuse them with another layout or use
`COM3`. This is an explicit recovery step, never an automatic fallback after
a failed save. The second command verifies the already flashed image's model
behavior; retain the preceding flash log to establish firmware identity.

## Safety and scope

Flashing replaces the application currently installed on the selected board.
This path is intended for the exact 16 MB target named above. It does not back
up existing firmware. Disconnect boards you do not intend to use, and never
substitute another ESP32 family or flash layout.

The proof covers the fixed V2 9-input/8-output packet-backed linear head and its
NVS persistence. It is not on-device training, language-model inference, a
complete survival controller, or a safety certification.
