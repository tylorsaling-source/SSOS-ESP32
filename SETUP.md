# Setup and first verification

## 1. Confirm the target

Prebuilt images are only for ESP32-S3-WROOM-1U N16R8 with 16 MB QIO flash and
native USB Serial/JTAG. V1/V2 disable PSRAM; V3.0.1 requires 8 MB OPI PSRAM.
Other boards require a source build and validation.

## 2. Choose a release

- V1 is the hardware-tested packet-controller baseline.
- V2 adds a fixed packet-backed 9-input/8-output linear head but has not been
  physically flashed in the published validation record.
- V3.0.1 is the physically tested Quark language pipeline. It supports the
  accepted two-board pair and an optional one-master/two-worker topology. It
  does not expose the V1/V2 packet console while running.

Download and extract the matching ZIP from
[GitHub Releases](https://github.com/tylorsaling-source/SSOS-ESP32/releases).

## 3. Install firmware

For V1 or V2, follow [docs/FLASHING.md](docs/FLASHING.md). The guided Windows
path validates the target and requires an explicit `FLASH <port>` confirmation.

For V3, follow the package's [wiring and flashing
guide](benchmarks/quark-v2-0.5m-pair-pipeline/README.md). V3 requires two boards
for the pair or three for the optional extension, with one distinct image per
documented role.

Flashing any release replaces the selected board's current application.

## 4. Verify V1 or V2

Open the board's serial port at 115200 baud and send:

```text
ID
STATS
HELP
```

The identity response should include `chip=esp32s3`,
`proto=ssos.packet.v1`, and `fuse=9to8`.

## 5. Verify packet state

```text
PKT id=demo:mode d=1,0,0,0,0,0,0,0,0 role=document body=night
GET id=demo:mode
SAVE
DUMP
```

`SAVE` forces immediate persistence. The runtime can also auto-save after an
adaptive packet threshold, but recent changes may be lost before it does. Use
and confirm `SAVE` before removing power. `DUMP` exports packet state only; it
does not back up firmware.

Read [docs/PROTOCOL.md](docs/PROTOCOL.md) before writing an application and
[docs/USE_CASES.md](docs/USE_CASES.md) for supported uses and current limits.

For V3, use the package's `tools/capture-pair.py` and
`tools/verify-result.py`; the V1/V2 packet commands above do not apply.
