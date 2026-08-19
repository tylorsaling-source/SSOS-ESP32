# SSOS Quark two-board pipeline

Run one pretrained 465,504-parameter causal-language model as a two-context
pipeline across two ESP32-S3 boards connected by 40 MHz SPI.

This package is a reproducible benchmark and working reference implementation.
It demonstrates higher aggregate decode throughput by interleaving two
independent autoregressive contexts. It does **not** claim that a single
dependent token stream has half the latency.

## Start here

This project is for someone who wants to see two small physical boards
cooperate on real pretrained language-model inference.

- The **master** runs model layers 0-1 and sends a 96-number intermediate
  representation over SPI.
- The **worker** runs layers 2-3 and chooses the next token.
- Two separate text contexts alternate, so neither board waits idle for the
  other on every step.
- A computer sends token IDs and receives token IDs over the master's USB
  serial port. Text tokenization and rendering stay on the computer.

Choose a path:

| You want to... | Start with... |
|---|---|
| Use the exact tested firmware | [Wiring](WIRING.md), then **Quick start with prebuilt firmware** below |
| Inspect or modify the implementation | **Build from source** below |
| Check the speed claim | [Original baselines](BASELINES.md), then **Run the acceptance test** |
| Audit every included file | [Publication manifest](PACKAGE_MANIFEST.md) and `SHA256SUMS` |

You need two supported ESP32-S3 boards, two USB connections, and six jumper
connections between the boards: five signals plus one common ground. No Wi-Fi,
cloud service, Pi, Uno, sensor, or training step is required.

## Verified physical result

Tested on two ESP32-S3-WROOM-1U N16R8 boards at 240 MHz:

| Gate | Result |
|---|---:|
| Model | LH-Tech-AI/Quark-v2-0.5M |
| Parameters | 465,504 |
| Quantization | Q8_0, group size 8 |
| SPI | 40 MHz |
| Five-run oracle agreement | 240/240 tokens |
| Aggregate decode throughput | 44.729-44.735 tok/s |
| Median | 44.731 tok/s |
| Original standalone baseline | 18.469438 tok/s, 24/24 |
| Original sequential-pair baseline | 18.345216 tok/s median, 120/120 |
| Original pair/standalone | 0.993274x |
| New median/standalone | 2.421880x |
| New median/original pair | 2.438279x |
| Worker reset/rejoin | PASS, 48/48 tokens |

The exact result is in
[`results/physical-20260818-pair-pipeline/result.json`](results/physical-20260818-pair-pipeline/result.json).
The complete original comparison, including prefill/decode/transport timing and
the pre-change pair health recheck, is in [`BASELINES.md`](BASELINES.md).

## What runs where

```text
context 0: master layers 0-1 -> SPI -> worker layers 2-3 + classifier
context 1: master layers 0-1 -> SPI -> worker layers 2-3 + classifier

schedule: worker(context 0) overlaps master(context 1), then alternates
```

Each board owns two independent Transformer instances and two independent KV
caches. Every SPI frame carries a stream ID and per-stream sequence number.
Responses with the wrong stream or sequence are rejected.

## Hardware scope

The supplied binaries target exactly:

- ESP32-S3-WROOM-1U N16R8
- 16 MB QIO flash
- 8 MB OPI PSRAM
- Arduino-ESP32 3.3.11
- native USB Serial/JTAG

Other ESP32 variants must be built and validated separately. Do not flash the
prebuilt images onto an unmatched board.

## Wiring

Connect the two boards signal-for-signal and share ground. Do not connect their
power rails together.

| Function | Master | Worker |
|---|---:|---:|
| SCK | GPIO12 | GPIO12 |
| MOSI | GPIO11 | GPIO11 |
| MISO | GPIO13 | GPIO13 |
| CS | GPIO10 | GPIO10 |
| READY | GPIO9 | GPIO9 |
| Ground | GND | GND |

See [`WIRING.md`](WIRING.md) before powering the pair.

## Quick start with prebuilt firmware

Back up any firmware or device state that matters first. Flashing replaces the
bootloader, partition table and application regions named by the script.

Windows PowerShell:

```powershell
python -m pip install esptool pyserial
.\scripts\flash-prebuilt-windows.ps1 -Role worker -Port COM5
.\scripts\flash-prebuilt-windows.ps1 -Role master -Port COM6
```

Linux or macOS:

```sh
python3 -m pip install esptool pyserial
./scripts/flash-prebuilt-posix.sh worker /dev/ttyACM0
./scripts/flash-prebuilt-posix.sh master /dev/ttyACM1
```

Flash the worker first. When idle, the worker LED is green and the master LED
is violet.

## Build from source

Install Arduino CLI and the Espressif `esp32` core version 3.3.11. The scripts
set the required `-O2` optimization property; using Arduino's default `-Os`
reduced the measured pipeline to about 33.09 tok/s in the physical test.

Windows:

```powershell
.\scripts\build-windows.ps1
```

Linux or macOS:

```sh
./scripts/build-posix.sh
```

Outputs are written under `build/master` and `build/worker`.

## Run the acceptance test

The worker only needs power and the SPI connection. Open the master's USB
serial port:

```powershell
python .\tools\capture-pair.py --master COM6 --trials 5 --output capture.json
python .\tools\verify-result.py capture.json
```

The verifier fails unless all five runs are present, both streams match all
expected tokens, the aggregate result is 48/48 per run, no protocol error is
reported, and every run reaches 36.938876 tok/s.

## Included model

`firmware/quark_esp32/quark_model_data.h` embeds the accepted 700,672-byte
Q8_0 group-8 checkpoint. The converted binary is also supplied in
`model/quark-q8-g8.bin` for inspection and reproducibility work.

The upstream model is pinned to commit
`7a30cd277348416659e94d5937d699d72e34afac`. Its original
`model.safetensors` SHA-256 is
`3fce3f379b5c485d25f72364d10fd8d9fe22a1f38e244531391e77272cb79404`.
The upstream model card declares Apache License 2.0. See
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Claim boundaries

- This is aggregate throughput from two interleaved contexts, not 2x lower
  causal latency for one stream.
- Tokenization and text rendering remain host-side; the benchmark sends and
  receives token IDs.
- The bundled prompts are deterministic correctness tests, not a broad model
  quality evaluation.
- `transport_us` in this firmware includes time waiting for worker computation;
  it is not pure SPI serialization latency.
- The result applies to the named model, firmware, boards and test corpus. It
  does not establish arbitrary-model or arbitrary-board speedup.

## Package contents

- `firmware/` - master/worker source and embedded pretrained model
- `prebuilt/` - exact tested boot, partition and application images
- `model/` - accepted Q8_0 group-8 checkpoint artifact
- `scripts/` - Windows and POSIX build/flash helpers
- `tools/` - serial capture and fail-closed verifier
- `results/` - accepted physical evidence
- `BASELINES.md` - original standalone and sequential-pair comparison metrics
- `upstream/` - pinned upstream model card

Nothing in this package contains device recovery dumps, NVS captures, COM-port
assignments as requirements, rejected quantizations, compiler caches or bundled
toolchains.
