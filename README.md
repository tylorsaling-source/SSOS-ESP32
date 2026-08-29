# SSOS ESP32-S3

**Packet-state firmware, replaceable 9-D heads, physically tested multi-board
language inference, and reproducible split-language training for ESP32-S3.**

[![Release](https://img.shields.io/github/v/release/tylorsaling-source/SSOS-ESP32)](https://github.com/tylorsaling-source/SSOS-ESP32/releases)
[![Integrity](https://github.com/tylorsaling-source/SSOS-ESP32/actions/workflows/release-integrity.yml/badge.svg)](https://github.com/tylorsaling-source/SSOS-ESP32/actions/workflows/release-integrity.yml)
[![License](https://img.shields.io/github/license/tylorsaling-source/SSOS-ESP32)](LICENSE)

**Platform:** Espressif ESP32-S3, built with the Espressif Arduino-ESP32 core.
SSOS is an independent community project and is not affiliated with or endorsed
by Espressif Systems or Arduino.

## Start here: choose the system you want

SSOS publishes separately downloadable systems. Choose by function, not
merely by version number:

| Release | System payload | Choose it when | Validation |
| --- | --- | --- | --- |
| [V1.0.0](https://github.com/tylorsaling-source/SSOS-ESP32/releases/tag/v1.0.0) | One-board packet controller with persistent compact state and an internal 9-D runtime | You need device-owned records, replay, migration, or the original kernel experiments | Hardware-tested on ESP32-S3-WROOM-1U N16R8 |
| [V2.0.0](https://github.com/tylorsaling-source/SSOS-ESP32/releases/tag/v2.0.0) | V1 plus one packet-backed fixed 9-input/8-output linear head | You need a replaceable tiny scoring/action head | Compiled and host/artifact-validated; not physically flashed |
| [V3.0.1](https://github.com/tylorsaling-source/SSOS-ESP32/releases/tag/v3.0.1) | Quark-v2-0.5M split across a pair, with an optional two-lane three-board extension | You want physical boards cooperating on pretrained text inference | Pair: 240/240 at 44.731 tok/s median; trio gate: 96/96 at 87.927 tok/s |
| [V4.0.0](https://github.com/tylorsaling-source/SSOS-ESP32/releases/tag/v4.0.0) | Original custom 549,984-parameter split-training lineage and its first checkpoint | You want the original custom model, split-gradient gate, or its continuation point | 100.00023 tokens/parameter; best held-out loss 2.991671; exact one-step split-equivalence gate |
| [V4.0.1](https://github.com/tylorsaling-source/SSOS-ESP32/releases/tag/v4.0.1) | Separate fresh cluster 3–4–5 lineage and its own first checkpoint | You want an independently initialized model without V4.0.0 learned state | 5.12M presented tokens; held-out loss 3.488711; no parent checkpoint |

## V2: user-facing physical proof

V2 now includes a single Windows workflow that flashes one compatible board,
installs all 72 head weights, checks 8 outputs for 3 deterministic inputs,
performs a real hard reset, repeats the checks, and saves both readable and raw
proof. It automatically finds one compatible board and refuses to open or flash
`COM3`.

From the extracted repository root:

```powershell
.\scripts\validate-v2-windows.cmd
```

The last line is a plain-language `PASS` or `FAIL`; detailed JSON evidence and
the timestamped serial transcript are saved automatically. Read the
[one-board V2 proof guide](validation/v2-hardware/README.md) before connecting a
board. Until a real run produces a passing evidence file and that trace is
committed, the published V2 status remains **not physically validated**.

V3 is a dedicated multi-board application with distinct master and worker
roles. Installing it writes the selected boards' application regions, so
preserve any existing firmware or learned state first.

## V4: train a custom split language model

V4.0.0 packages the original model, tokenizer, deterministic curriculum builders,
master/worker split, optimizer state, 9-D transaction identity, first
checkpoint, and numerical equivalence gate for a custom 549,984-parameter
causal-language model. Master owns 274,944 parameters and worker owns 275,040;
the detached 96-value split boundary returns an exact activation gradient for
the master-side backward pass.

The first checkpoint represents 54,998,528 presented tokens, or 100.00023
tokens per parameter. It is resumable and retains both stages, AdamW, RNG,
tokenizer/corpus identity, and schedule. Start with the complete
[V4 training package](benchmarks/ssos-550k-language-training/README.md).

V4.0.1 is a separate package named
[`ssos-550k-language-cluster-345`](benchmarks/ssos-550k-language-cluster-345/README.md).
It starts from fresh weights with its own RNG and optimizer while preserving
the same architecture, tokenizer and corpus identity. Its step-5,000 checkpoint
contains 5,120,000 presented tokens and no V4.0.0 learned state.

## V3: two boards run one language model

V3 divides a real pretrained 465,504-parameter causal-language model across two
ESP32-S3 boards connected by 40 MHz SPI:

```text
computer ─USB─> master: layers 0-1 ─SPI─> worker: layers 2-3 + next token
                 context B starts       while context A finishes
```

The master and worker each keep two independent Transformer/KV-cache contexts.
While the worker completes one context, the master begins the other. Stream IDs
and per-stream sequence numbers reject crossed or stale responses.

The complete [V3 package](benchmarks/quark-v2-0.5m-pair-pipeline/README.md)
contains:

- the premade Q8 group-8 Quark-v2-0.5M model;
- exact physically tested master and worker firmware plus source;
- a six-wire table covering five signals and the required shared ground;
- Windows, Linux, and macOS build and flashing commands;
- original one-board and sequential-pair comparison measurements;
- result capture and a fail-closed five-run verifier; and
- checksums, licenses, notices, and a publication manifest.

### Accepted physical result

| Measurement | Result |
| --- | ---: |
| Five-run oracle agreement | 240/240 tokens |
| V3 two-context interleaved pair | 44.730763 tok/s median |
| **Paired Two-Board Non-Interleaved Baseline** | **18.345216 tok/s median** |
| **Interleaving gain over the paired baseline** | **2.438279x (2.44x)** |
| Standalone one-board reference | 18.469438 tok/s |
| Worker reset and rejoin | PASS, 48/48 tokens |

The headline **2.44x speedup** is specifically the gain from adding two-context
interleaving to the same two-board arrangement. Interleaving overlaps worker
compute for one context with the next context's master-side work and SPI
handoff. It is measured against the **Paired Two-Board Non-Interleaved
Baseline** at 18.345216 tok/s. The reported metric is aggregate throughput
across the two independent contexts. `transport_us` records the complete
request/response interval, including worker-compute wait time.

### Optional three-board extension

V3 also includes a one-master/two-worker topology. It runs two independent
copies of the proven two-context interleaving schedule on separate 40 MHz SPI
lanes, producing four concurrent contexts with independent model and KV-cache
state. Stream IDs, sequence validation, per-lane retry buffers, and checksum
recovery protect each in-flight request. The accepted physical run produced
96/96 exact tokens at 87.927387 aggregate tok/s. V3.0.1 includes role-specific
firmware, prebuilt images, exact wiring, Windows/POSIX build and flash scripts,
and machine-readable evidence in the same
[V3 package](benchmarks/quark-v2-0.5m-pair-pipeline/README.md#three-board-extension).

## What V1 and V2 provide

The one-board packet firmware accepts text commands over native USB serial. It
can hold up to 32 compact records, find them by ID or nine-number coordinate,
save/load them through NVS, export them as replayable text, and run an internal
9-D adaptive heuristic. V2 additionally reconstructs a fixed 9-input/8-output
linear head from eight packet-stored Q10 rows.

That makes V1/V2 useful for compact device-owned configuration, tiny scoring
heads, controller-state backup/migration, and equal-work kernel experiments.
See [What you can build](docs/USE_CASES.md) for the exact boundaries.

> [!IMPORTANT]
> SSOS is not a general-purpose operating system, database, secure store,
> filesystem, sensor platform, Wi-Fi/BLE mesh, MCP server, or autonomous safety
> controller. V3 executes only its packaged model shape and firmware. V4.0.0
> publishes the executable split-training reference and first checkpoint for
> its documented 549,984-parameter shape.

## First useful V1/V2 session

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

## Three V1/V2 concepts are called 9-D

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

## V1/V2 packet-model details

V2 preserves the V1 `ssos.packet.v1` bank. Eight records named `model:w:0`
through `model:w:7` hold signed-Q10 rows. `MLOAD` validates the rows and builds
a volatile 72-float cache; `MINFER` computes eight dot-product scores. The board
does not apply softmax, activation, or argmax, and it has no separate bias term
unless the caller reserves an input—commonly the ninth value—as a constant.

After compatible V2 firmware is installed, replacing those eight model packets
does not require another firmware flash. Use `SAVE` to force immediate
persistence instead of waiting for the background flush threshold.

## Supported hardware

The V1/V2 prebuilt images target exactly:

- ESP32-S3-WROOM-1U N16R8;
- 16 MB flash in QIO mode;
- native USB Serial/JTAG (`303A:1001`); and
- PSRAM disabled.

The V3.0.1 Quark images instead require the documented N16R8 target with
8 MB OPI PSRAM enabled. Use only the V3 package's own build and flash scripts;
do not mix V1/V2 and V3 images or board settings.

Do not flash the supplied images onto another ESP32 family or flash layout.
Other ESP32-S3 boards require a source build with the correct board settings.

V1 and V2 run on one board. The base V3 topology requires two supported boards;
the optional extension requires three. Use the documented five signals per SPI
lane and a common ground.

## Install

Download and extract a ZIP from [Releases](https://github.com/tylorsaling-source/SSOS-ESP32/releases).
Do not run scripts from inside the ZIP.

### V3 master/worker installation

Start with the V3 [wiring guide](benchmarks/quark-v2-0.5m-pair-pipeline/WIRING.md),
then use its [prebuilt flashing instructions](benchmarks/quark-v2-0.5m-pair-pipeline/README.md#quick-start-with-prebuilt-firmware).
Select each port explicitly: one board receives the worker application and the
other receives the master application. Do not guess ports.

### V1/V2 packet-firmware installation

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

V1/V2 scripts are supplied for all four host paths. Hardware-validation status is
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
the host-projection/ESP-head split and preserves its simulation reports. Its
[48-field input contract](models/basic_surv_esp4/OBSERVATION_CONTRACT.md) now
defines every name, position, normalization formula, proposal bit, projection,
and output. It remains an adapter—not a complete survival system or a
physical-world validation.

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

## Build V1/V2 from source

The reference build uses Arduino-ESP32 3.3.5 and:

```text
esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,UploadMode=default,FlashMode=qio,FlashSize=16M,PSRAM=disabled,PartitionScheme=app3M_fat9M_16MB
```

Install `arduino-cli`, install the pinned ESP32 core, then run `./build.sh`.
Release images under `images/flash` remain separate from local build output.

For V3 source builds, use the pinned Arduino-ESP32 3.3.11 commands in the
[V3 package](benchmarks/quark-v2-0.5m-pair-pipeline/README.md#build-from-source).

## Benchmark claims

Raw device traces are under `traces/`, with the unique hardware address
redacted. Speed ratios apply only to the exact equal-input, equal-weight,
equal-MAC kernels named in those traces. They are not overall AI, model, or
application speedups. The `hello_world` comparison is unequal and must not be
quoted as an SSOS speedup. The fused 9-to-8 kernel is measured directly rather
than estimated as eight 9-to-1 calls.

V3 has a separate evidence set under
`benchmarks/quark-v2-0.5m-pair-pipeline/results/`. Its headline 2.438279x
(2.44x) figure is the gain from two-context interleaving over the **Paired
Two-Board Non-Interleaved Baseline** on the named model and hardware. The
18.469438 tok/s standalone result is retained as a secondary one-board
reference, not the headline baseline. This is not a general 2x inference or
accuracy claim.

### For Espressif reviewers

The [V3 physical package](benchmarks/quark-v2-0.5m-pair-pipeline/README.md) is
the shortest reproducible path for evaluating the multi-board work on
Espressif hardware. It pins the ESP32-S3-WROOM-1U N16R8 target,
Arduino-ESP32 version, role-specific source and binaries, SPI wiring, model
artifact, checksums, raw measurements and fail-closed oracle verifier. The
original sequential two-board result and interleaved result remain side by
side so scheduling gains are distinguishable from standalone-board or generic
model claims.

Espressif engineers and Arduino-ESP32 maintainers are invited to reproduce the
measurements, review the SPI/DMA and PSRAM integration, or propose changes
through the repository's issue and pull-request workflow.

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
