# Package validation

Validation performed on 2026-08-19 before publication preview.

## Source build

Both roles compiled successfully from this standalone folder with Arduino-ESP32
3.3.11 and the included Windows build script.

| Role | Application bytes | Static RAM bytes | Optimization |
|---|---:|---:|---|
| Worker | 1,030,000 | 23,152 | `-O2` |
| Master | 1,042,304 | 23,336 | `-O2` |

Compile-command inspection confirmed `-O2` and no trailing `-Os` for the model
runtime translation unit.

Rebuilt binaries have the same sizes as the physically tested applications.
Their byte hashes are not expected to match because the ESP32 build embeds
build-path metadata. The `prebuilt/` applications retain the exact physically
tested hashes recorded below.

## Prebuilt images

| Role | SHA-256 |
|---|---|
| Master application | `c9301ff8f2ee4bac3d449ad896affa9bba9908d3bb28879d09f4db77393e9292` |
| Worker application | `2dee55d71e679f120bddef34550656a7cf0d79a6561f3403f11ced0930dd8e38` |

`esptool image-info` recognized both applications and the shared bootloader as
ESP32-S3 images targeting 16 MB flash.

## Verifier

The offline verifier passed a synthetic five-run 240/240-token capture and
correctly rejected a capture with one stream changed to 23/24.

## Safety and privacy

- Recovery/NVS dumps are absent.
- Device MAC addresses, machine names, Tailscale addresses and local user paths
  are absent.
- The only COM values in documentation are replaceable examples.
- No serial port was opened and no board was flashed during package validation.

## Three-board extension

The trio source compiled as three separate `-O2` roles. The exact accepted
application images bundled under `prebuilt/trio-*` have these SHA-256 values:

| Rebuilt role | Application bytes | Static RAM bytes |
|---|---:|---:|
| Trio master | 1,044,464 | 23,720 |
| Trio worker 1 | 1,030,336 | 23,152 |
| Trio worker 2 | 1,030,336 | 23,152 |

Rebuilt hashes vary with embedded build-path metadata; the sizes match the
accepted physical applications. The bundled prebuilt hashes are authoritative:

| Role | SHA-256 |
|---|---|
| Trio master | `31e70721b6f49656a540495bc8df90040bc59a4c09dc630d6a2fd34270da8743` |
| Trio worker 1 | `76d6d5a55add390593221f19b80af327ce6c8cfcb0a9c35f2d8edee8b7e6e9df` |
| Trio worker 2 | `446e44eca16cf48349119f686d2179a160c21c0fc4f88e7673b4ca2d054f9d9a` |

All three physical writes and subsequent application-region comparisons passed
esptool digest verification. The accepted run returned 96/96 oracle tokens at
87.927387 aggregate tok/s. It used two independent 40 MHz lanes and reported
retry counts `[0,1]`. This validates the accepted gate, not five-run stability.
