# SSOS ESP32-S3

[![Release](https://img.shields.io/github/v/release/tylorsaling-source/SSOS-ESP32)](https://github.com/tylorsaling-source/SSOS-ESP32/releases)
[![Integrity](https://github.com/tylorsaling-source/SSOS-ESP32/actions/workflows/release-integrity.yml/badge.svg)](https://github.com/tylorsaling-source/SSOS-ESP32/actions/workflows/release-integrity.yml)
[![License](https://img.shields.io/github/license/tylorsaling-source/SSOS-ESP32)](LICENSE)

SSOS is an experimental packet controller and live 9-dimensional tensor runtime
for the ESP32-S3. The chip owns a replaceable 32-slot `ssos.packet.v1` bank,
persistent packet state, and a fused 9-to-8 matcher. A phone or computer is a
terminal and transport; it is not the operating system.

This public project includes firmware source, reproducible traces, prebuilt
images for the tested board, and guided flashing paths for Windows, Android
with Termux, Linux, and macOS.

## Pick the correct release

| Release | Purpose | Hardware status |
| --- | --- | --- |
| [V1.0.0](https://github.com/tylorsaling-source/SSOS-ESP32/releases/tag/v1.0.0) | Frozen, model-agnostic packet controller and 9-D runtime | Tested on the stated ESP32-S3 board |
| [V2.0.0](https://github.com/tylorsaling-source/SSOS-ESP32/releases/tag/v2.0.0) | V1 plus a packet-backed 9-to-8 model execution bridge and an example `basic_surv` head | Compiled and artifact-validated; not physically flashed |

V2 does not replace the V1 packet format. Its model rows are ordinary packets
named `model:w:0` through `model:w:7`; `MLOAD` reconstructs a volatile execution
cache from those authoritative packets.

## Supported release hardware

The supplied binaries target exactly:

- ESP32-S3-WROOM-1U N16R8
- 16 MB flash, QIO mode
- native USB Serial/JTAG (`303A:1001`)
- PSRAM disabled

Do not flash the supplied images onto another ESP32 family or flash layout.
Owners of other ESP32-S3 boards should build from source with their board's
correct settings.

## Install from a release

Download and extract a ZIP from [Releases](https://github.com/tylorsaling-source/SSOS-ESP32/releases).
Do not run scripts from inside the ZIP.

### Windows 10 or 11

Install current Python 3, enable **Add Python to PATH**, then open PowerShell in
the extracted release folder:

```powershell
py -3 -m pip install --upgrade esptool
.\scripts\flash-windows.cmd
```

If several compatible boards are connected:

```powershell
.\scripts\flash-windows.cmd -Port COM8
```

The script verifies image hashes, identifies the board, displays the flash map,
requires `FLASH <port>` confirmation, verifies the write, resets the board, and
releases DTR/RTS low.

### Android with Termux

```sh
pkg install python clang libusb termux-api
python -m pip install --upgrade esptool
./scripts/build-host-termux.sh
./scripts/flash-termux.sh /dev/bus/usb/001/00X
```

### Linux or macOS

```sh
python3 -m pip install --upgrade esptool
./scripts/flash-posix.sh /dev/ttyACM0
```

On macOS, the port normally resembles `/dev/cu.usbmodem*`. See
[the flashing guide](docs/FLASHING.md) for recovery, manual commands, and safety
behavior.

## Use the controller

The 115200-baud console supports:

```text
ID DUMP PKT GET DEL STATS SAVE LOAD CLEAR TENSOR TSET TRESET MODEL MLOAD MINFER MCLEAR BENCH HELP
```

Begin with `ID`, `STATS`, `TENSOR`, and `HELP`. Commands such as `PKT`, `DEL`,
`CLEAR`, `SAVE`, `LOAD`, `TSET`, and `TRESET` mutate state.

In V2, `MODEL`, `MLOAD`, `MINFER`, and `MCLEAR` operate on the packet-backed
execution head without altering the OS scheduling tensor. A Windows model
update after the initial firmware installation does not require another flash:

```powershell
.\scripts\install-model-windows.ps1 -Port COM4
```

The included `models/basic_surv_esp4` directory is a worked 72-weight example,
not a claim that SSOS is limited to that model.

## Architecture

```text
host / terminal
      |
      | ssos.packet.v1 commands
      v
32-slot persistent packet bank ----> DUMP / SAVE / LOAD
      |
      +----> live 9-D scheduling tensor ----> fused 9-to-8 matcher
      |
      +----> model:w:0..7 packets --MLOAD--> volatile 72-weight cache --MINFER--> 8 outputs
```

The packet bank remains authoritative. The V2 cache is reconstructed after
`LOAD` or reboot and is never persisted as a separate hidden model store.

## Build from source

The reference build uses Arduino-ESP32 3.3.5 and:

```text
esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,UploadMode=default,FlashMode=qio,FlashSize=16M,PSRAM=disabled,PartitionScheme=app3M_fat9M_16MB
```

Install `arduino-cli`, install the pinned ESP32 core, then run `./build.sh`.
Release binaries under `images/flash` are separate from local build output.

## Reproduce and interpret benchmarks

Device-produced traces are under `traces/`, with the unique hardware address
redacted. Report speed ratios only for equal input, weights, math, and MAC count.
The `hello_world` comparison is explicitly unequal and must not be quoted as an
SSOS speedup. The fused 9-to-8 kernel is measured directly; do not estimate it
as eight 9-to-1 calls.

## Collaborate

Collaboration is the preferred development model:

1. Start a [change request](https://github.com/tylorsaling-source/SSOS-ESP32/issues/new?template=change-request.yml) for a feature or protocol change.
2. Fork the repository and create a focused branch.
3. Follow [CONTRIBUTING.md](CONTRIBUTING.md), including hardware and benchmark evidence rules.
4. Open a pull request using the supplied template.
5. The community moderator labels and checks the request; a human maintainer makes the final decision.

Bug reports, board-port requests, documentation corrections, and independently
reproduced benchmark results are welcome. Please read [GOVERNANCE.md](GOVERNANCE.md)
and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Safety and project status

- Never leave DTR asserted; DTR controls GPIO0/BOOT on the tested board.
- Do not hold BOOT while using the guided scripts.
- Do not enable OPI PSRAM for the supplied build.
- Never guess a port when multiple boards are attached.
- Flashing replaces the current application; export anything needed first.
- Hash validation proves file integrity, not board compatibility.

SSOS is experimental firmware, not a safety-certified controller, security
boundary, alarm, medical device, or life-support component. Security reports
belong in GitHub's private vulnerability-reporting channel described in
[SECURITY.md](SECURITY.md), never in a public issue.

Licensed under Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
