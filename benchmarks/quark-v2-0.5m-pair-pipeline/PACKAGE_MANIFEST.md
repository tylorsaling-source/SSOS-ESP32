# SSOS ESP32 V3.0.1 publication manifest

Authoritative repository destination:
`benchmarks/quark-v2-0.5m-pair-pipeline/`

## Included

| Path | Purpose |
|---|---|
| `VERSION` | Official package version (`3.0.1`) |
| `firmware/quark_pair_pipeline/` | Two-context SPI pipeline and role entrypoint |
| `firmware/quark_trio_pipeline/` | Two independent lanes running four interleaved contexts |
| `firmware/quark_esp32/` | Q8 runtime and embedded accepted model |
| `model/quark-q8-g8.bin` | Accepted premade Q8_0 model artifact |
| `prebuilt/common/` | Exact bootloader, partition and boot-app images |
| `prebuilt/master/app.bin` | Exact tested `-O2` master application |
| `prebuilt/worker/app.bin` | Exact tested `-O2` worker application |
| `prebuilt/trio-master/app.bin` | Exact accepted four-context master application |
| `prebuilt/trio-worker1/app.bin` | Exact accepted lane-1 worker application |
| `prebuilt/trio-worker2/app.bin` | Exact accepted lane-2 worker application |
| `scripts/` | Windows and POSIX build/flash commands |
| `tools/` | Five-run serial capture and fail-closed verification |
| `results/` | Accepted physical result and claim boundaries |
| `BASELINES.md` | Original standalone, sequential pair and recheck metrics |
| `upstream/` | Pinned Quark model card |
| `licenses/` | Explicit Apache-2.0 and MIT dependency licenses |

## Deliberately excluded

- Device recovery images and NVS captures
- COM-port assignments as hard requirements
- Rejected Q8 group-16/group-32 artifacts
- The FP32 conversion artifact and original safetensors checkpoint
- Arduino build objects, ELF files, maps and compiler caches
- Downloaded Zig or other toolchains
- Rejected three-board timing experiments and compiler/build caches
- Private filesystem paths, Tailscale addresses and machine names

## Public claim

On the named ESP32-S3 N16R8 hardware, model, firmware and two-prompt corpus,
the two-context pipeline passed 240/240 expected tokens over five runs at a
median 44.730763 aggregate tokens/second. This is 2.421880x the one-board
18.469438 tok/s baseline and 2.438279x the accepted 18.345216 tok/s original
sequential-pair median.

The throughput measurement aggregates two independent interleaved contexts on
the named model, firmware, ESP32-S3 target and deterministic corpus.

The V3 package also includes an accepted three-board extension: one master and
two workers produced 96/96 expected tokens at 87.927387 aggregate tok/s across
four independent contexts. V3.0.1 adds two independent SPI lanes, per-lane
request integrity and recovery, separate KV-cache state, role-specific source
and prebuilt applications, and cross-platform build/flash tooling.
