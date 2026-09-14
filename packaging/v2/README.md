# SSOS ESP32 V2.0.1

One ESP32-S3 packet controller with a replaceable **9-input / 8-output Q10
scoring head**. This package contains only V2 and its worked basic_surv adapter.

## Install and prove it on Windows

Use an ESP32-S3 N16R8-class board with 16 MB flash and native USB Serial/JTAG.
The images disable PSRAM. Install Python 3.10 or later, then:

```powershell
python -m pip install "esptool>=5.1" pyserial
.\scripts\validate-v2-windows.cmd
```

Select the board if needed with `-Port COM20`. The workflow shows the target
and requests confirmation. It flashes and verifies the images, **initializes
leftover settings** by erasing only the 20 KiB NVS partition, installs 72
weights, checks three vectors, saves, hard-resets, and checks them again.
Saved settings and old model rows on that board are discarded; the whole chip
is never erased. COM3 is refused. No backup or dump is made.

A complete success reports **48/48 matching scores and reset persistence
passed**. The JSON, serial transcript, and flash/initialization log are saved
under `validation/v2-hardware/results/`.

Inspect the plan without opening a board:

```powershell
.\scripts\validate-v2-windows.cmd -ValidateOnly
```

`-KeepSettings` explicitly opts out of initialization and may reproduce a
save failure on reused storage. `-SkipFlash` skips flashing but still
initializes settings unless combined with `-KeepSettings`. `-Yes` accepts the
displayed flash/initialization action for automation.

## Other install paths

```powershell
.\scripts\flash-windows.cmd -Port COM20 -InitializeSettings
```

```sh
sh scripts/flash-posix.sh /dev/ttyACM0 --initialize-settings
sh scripts/flash-termux.sh /dev/bus/usb/001/002 --initialize-settings
```

Flash-only installers preserve settings unless the explicit option is used.
The physical proof in this release uses Windows/native USB; POSIX/Termux
initialization is host/dry-run checked, not physically tested on those hosts.
See [flashing](docs/FLASHING.md) and the [proof guide](validation/v2-hardware/README.md).

## Use the head

`MLOAD` reconstructs eight Q10 rows from ordinary packets; `MINFER x=` computes
eight raw dot products. Model rows can be replaced without reflashing; `SAVE`
persists them. The [input contract](models/basic_surv_esp4/OBSERVATION_CONTRACT.md)
documents the external 48-field observation and host projection to nine inputs.

See [release notes](RELEASE_NOTES.md) and the included physical run reports.
This is not on-device training, a language model, or a power-unplug endurance
claim. The repository's other payloads have separate releases.

`PACKAGE.json` identifies the exact source commit. Root `SHA256SUMS` covers
every packaged file except itself; `images/flash/SHA256SUMS` covers the flash
images. Package `VERSION` is 2.0.1; the repository-wide VERSION has a separate
meaning and is not changed by this payload release.
