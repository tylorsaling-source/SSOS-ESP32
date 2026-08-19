# Publication manifest

Proposed SSOS-ESP32 destination:
`benchmarks/quark-v2-0.5m-pair-pipeline/`

## Included

| Path | Purpose |
|---|---|
| `firmware/quark_pair_pipeline/` | Two-context SPI pipeline and role entrypoint |
| `firmware/quark_esp32/` | Q8 runtime and embedded accepted model |
| `model/quark-q8-g8.bin` | Accepted premade Q8_0 model artifact |
| `prebuilt/common/` | Exact bootloader, partition and boot-app images |
| `prebuilt/master/app.bin` | Exact tested `-O2` master application |
| `prebuilt/worker/app.bin` | Exact tested `-O2` worker application |
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
- Experimental three-board firmware that did not pass its response gate
- Private filesystem paths, Tailscale addresses and machine names

## Public claim

On the named ESP32-S3 N16R8 hardware, model, firmware and two-prompt corpus,
the two-context pipeline passed 240/240 expected tokens over five runs at a
median 44.730763 aggregate tokens/second. This is 2.421880x the one-board
18.469438 tok/s baseline and 2.438279x the accepted 18.345216 tok/s original
sequential-pair median.

The claim is aggregate throughput only. It is not a 2x single-stream latency,
general model quality, arbitrary-model, or arbitrary-board claim.
