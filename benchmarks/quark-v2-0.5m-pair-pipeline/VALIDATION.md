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
