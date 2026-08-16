# SSOS ESP32-S3

**Persistent packet state and replaceable tiny inference heads on ESP32-S3.**

[![Release](https://img.shields.io/github/v/release/tylorsaling-source/SSOS-ESP32)](https://github.com/tylorsaling-source/SSOS-ESP32/releases)
[![Integrity](https://github.com/tylorsaling-source/SSOS-ESP32/actions/workflows/release-integrity.yml/badge.svg)](https://github.com/tylorsaling-source/SSOS-ESP32/actions/workflows/release-integrity.yml)
[![License](https://img.shields.io/github/license/tylorsaling-source/SSOS-ESP32)](LICENSE)

## What SSOS is for

SSOS turns a supported ESP32-S3 into a small, host-controlled edge state and
inference node. A computer or Android phone sends text commands over native USB
serial. The board can:

- hold up to 32 compact records and find them by ID or nine-number coordinate;
- save those records to flash immediately on command or through the runtime's
  adaptive background flush, then load them after a restart;
- export the packet bank as replayable text for backup, migration, or versioning;
- run an experimental internal 9-D heuristic whose adaptive flush threshold
  controls background persistence while its other outputs remain internal; and
- in V2, rebuild and execute one fixed 9-input/8-output linear model head whose
  72 weights are stored as ordinary packets.

The practical idea is simple: flash the compatible firmware once, then change
small controller state or a tiny decision head as data instead of rebuilding
and reflashing the application for every update.

## What you can use it for now

| Use | What SSOS provides | Current status |
| --- | --- | --- |
| Portable device configuration | Small named records with role metadata, 9-number coordinates, NVS persistence, and text export/replay | V1 hardware-tested on the stated board |
| Replaceable edge scoring or action head | A host supplies 9 floats; V2 returns 8 linear scores using packet-stored Q10 weights | V2 compiled and artifact-validated; not physically flashed |
| Split host/MCU inference experiments | A laptop, Pi, or phone computes a feature vector while the ESP32 owns and runs the final 9-to-8 head | Interface and example artifacts are included |
| Tiny-kernel research | Device benchmarks and raw traces for the custom 9-to-1 and fused 9-to-8 kernels, with equal-work comparisons labeled | V1 device traces included |
| Controller-state backup or migration | `DUMP` emits packet records that can be replayed as `PKT` commands on compatible SSOS firmware | Packet state only; it does not copy firmware |

Examples include a small device-mode registry, replaceable thresholds or action
scores, a portable controller manifest, and experiments where a larger host
model delegates its last tiny linear decision layer to an ESP32-S3. See
[What you can build](docs/USE_CASES.md) for concrete boundaries and examples.

> [!IMPORTANT]
> SSOS is not a general-purpose operating system, database, secure store,
> filesystem, LLM runtime, on-device training framework, sensor platform,
> Wi-Fi/BLE mesh, MCP server, or autonomous safety controller. The current
> public firmware is controlled through USB serial.

## First useful session

After installing a compatible release, open a serial terminal at 115200 baud
and send:

```text
ID
STATS
PKT id=demo:mode d=1,0,0,0,0,0,0,0,0 role=document body=night
GET id=demo:mode
SAVE
DUMP
```

This creates one compact record, reads it, forces immediate persistence of the
current bank, and exports the bank as text. `PKT` changes RAM first. The runtime
also auto-saves after an adaptive threshold of received packets, but power loss
before that flush can lose recent changes. Send `SAVE` and require `OK saved`
whenever durability matters. Sending another packet with the same ID or the
same 9-D coordinate replaces the existing record.

Packet bodies are short opaque strings, not files. The current limits are 32
records, 39 stored ID characters, 63 body characters, and nine signed 16-bit
coordinate values. Read the [packet protocol](docs/PROTOCOL.md) before building
an integration.

## Three different things are called 9-D

They are independent and are not copied into one another automatically:

| Name | Type and owner | Purpose |
| --- | --- | --- |
| Packet coordinate `d=` | Nine signed 16-bit integers supplied by the host | Address/replace packet records by a compact semantic coordinate |
| Internal runtime vector `x[9]` | Nine floats derived on the board from fullness, timing, GET results, faults, and controller state | Drive the firmware's adaptive packet-handling heuristic |
| V2 inference input `MINFER x=` | Nine floats supplied by the caller | Input to the separate packet-backed 9-to-8 linear model head |

```text
host PKT commands ──> 32-slot packet bank ──> SAVE / background flush / DUMP
                              |
                              └─ model:w:0..7 ─MLOAD─> volatile 8x9 cache

board events ──> internal runtime x[9] ──> adaptive controller/flush behavior

host MINFER x[9] ─────────────────────────> volatile 8x9 cache ──> 8 raw scores
```

The internal runtime calculates parameters such as burst size, rest time, flush
interval, and scale; the current firmware directly uses its adaptive flush
threshold for background persistence and uses other values within the runtime.
Its small update is not general neural-network training. The V2 application
model is trained externally.

## V1 or V2?

| Release | Choose it when | Validation status |
| --- | --- | --- |
| [V1.0.0](https://github.com/tylorsaling-source/SSOS-ESP32/releases/tag/v1.0.0) | You want the frozen model-agnostic packet bank, persistence, replay, internal runtime, and benchmark baseline | Hardware-tested on ESP32-S3-WROOM-1U N16R8 |
| [V2.0.0](https://github.com/tylorsaling-source/SSOS-ESP32/releases/tag/v2.0.0) | You also need the packet-backed fixed 9-to-8 linear execution head | Compiled and host/artifact-validated; not physically flashed |

V2 preserves the V1 `ssos.packet.v1` bank. Eight records named `model:w:0`
through `model:w:7` hold signed-Q10 rows. `MLOAD` validates the rows and builds
a volatile 72-float cache; `MINFER` computes eight dot-product scores. The board
does not apply softmax, activation, or argmax, and it has no separate bias term
unless the caller reserves an input—commonly the ninth value—as a constant.

After compatible V2 firmware is installed, replacing those eight model packets
does not require another firmware flash. Use `SAVE` to force immediate
persistence instead of waiting for the background flush threshold.

## Supported release hardware

The supplied binary images target exactly:

- ESP32-S3-WROOM-1U N16R8;
- 16 MB flash in QIO mode;
- native USB Serial/JTAG (`303A:1001`); and
- PSRAM disabled.

Do not flash the supplied images onto another ESP32 family or flash layout.
Other ESP32-S3 boards require a source build with the correct board settings.

## Install

Download and extract a ZIP from [Releases](https://github.com/tylorsaling-source/SSOS-ESP32/releases).
Do not run scripts from inside the ZIP.

### Windows 10 or 11

```powershell
py -3 -m pip install --upgrade esptool
.\scripts\flash-windows.cmd
```

With more than one compatible board attached:

```powershell
.\scripts\flash-windows.cmd -Port COM8
```

The Windows path validates images and board identity, shows the flash map, and
requires `FLASH <port>` before writing.

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

Scripts are supplied for all four host paths. Hardware-validation status is
release-specific; the presence of a script is not a claim that every platform
and board combination was physically tested. Follow the full
[flashing and recovery guide](docs/FLASHING.md).

## Use V2's model head

The console commands are:

```text
MODEL MLOAD MINFER MCLEAR
```

On Windows, the included example rows can be installed after compatible V2
firmware is already present:

```powershell
.\scripts\install-model-windows.ps1 -Port COM4
```

That script writes eight model packets, calls `MLOAD`, calls `SAVE`, and checks
one known inference vector. It does not run `esptool` and does not flash.

The bundled [`basic_surv` adapter](models/basic_surv_esp4/README.md) demonstrates
the host-projection/ESP-head split and preserves its simulation reports. It is
not a complete survival system, a physical-world validation, or a currently
reproducible end-user model pipeline because the ordered 48-field observation
contract used by the external project is not yet included here.

## Console and protocol

The 115200-baud console supports:

```text
ID DUMP PKT GET DEL STATS SAVE LOAD CLEAR TENSOR TSET TRESET MODEL MLOAD MINFER MCLEAR BENCH HELP
```

`hash` is display metadata and defaults to non-cryptographic 32-bit FNV-1a.
`perm` is unenforced metadata; it is not access control. Do not store secrets in
the packet bank or treat either field as a security feature.

See [Protocol and limits](docs/PROTOCOL.md) for grammar, replacement behavior,
persistence, response formats, and replay guidance. The [host-tool guide](host/README.md)
separates current release tooling from older research prototypes.

## Build from source

The reference build uses Arduino-ESP32 3.3.5 and:

```text
esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,UploadMode=default,FlashMode=qio,FlashSize=16M,PSRAM=disabled,PartitionScheme=app3M_fat9M_16MB
```

Install `arduino-cli`, install the pinned ESP32 core, then run `./build.sh`.
Release images under `images/flash` remain separate from local build output.

## Benchmark claims

Raw device traces are under `traces/`, with the unique hardware address
redacted. Speed ratios apply only to the exact equal-input, equal-weight,
equal-MAC kernels named in those traces. They are not overall AI, model, or
application speedups. The `hello_world` comparison is unequal and must not be
quoted as an SSOS speedup. The fused 9-to-8 kernel is measured directly rather
than estimated as eight 9-to-1 calls.

## Collaborate

Collaboration is the preferred development model:

1. Start a [change request](https://github.com/tylorsaling-source/SSOS-ESP32/issues/new?template=change-request.yml).
2. Fork the repository and create a focused branch.
3. Follow [CONTRIBUTING.md](CONTRIBUTING.md), including evidence and claim rules.
4. Open a pull request using the supplied template.
5. The automated moderator labels and checks the request; a human maintainer
   makes the final decision.

Protocol documentation, alternate-board source-build support, host transports,
model-head tooling, and independently reproduced benchmarks are welcome. See
[GOVERNANCE.md](GOVERNANCE.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Safety and license

SSOS is experimental firmware, not a safety-certified controller, security
boundary, alarm, medical device, or life-support component. Never guess a port,
and export anything needed before flashing. Report vulnerabilities privately as
described in [SECURITY.md](SECURITY.md).

Licensed under Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
