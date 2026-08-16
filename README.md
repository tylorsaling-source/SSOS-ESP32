# SSOS ESP32-S3

SSOS is a packet controller and live 9-D tensor runtime for the ESP32-S3. The
firmware keeps a replaceable 32-slot packet bank and evaluates a fused 9-to-8
matcher on the chip.

This repository contains the firmware source, host-tool source, reproducible
benchmark traces, and guided flashing paths for Windows, Termux, Linux, and
macOS.

## Supported hardware

The supplied binary release is tested on:

- ESP32-S3-WROOM-1U N16R8
- 16 MB flash
- Native USB Serial/JTAG (`303A:1001`)
- QIO-capable flash
- PSRAM disabled by the firmware build

Do not use the supplied binaries on a different flash size or ESP32 family.
Owners of other ESP32-S3 boards should build from source with the correct board
settings instead of flashing the release image.

## Easiest installation

Download a tagged release and extract the ZIP before flashing. Do not run the
scripts from inside the ZIP.

### Windows 10 or 11

1. Install current Python 3 from <https://www.python.org/downloads/windows/>.
   Enable **Add Python to PATH** in the installer.
2. Open PowerShell in the extracted release folder and run:

   ```powershell
   py -3 -m pip install --upgrade esptool
   .\scripts\flash-windows.cmd
   ```

   If more than one compatible board is connected, specify the port:

   ```powershell
   .\scripts\flash-windows.cmd -Port COM8
   ```

The script verifies every image hash, identifies the selected ESP32-S3, shows
the exact flash map, asks for `FLASH <port>` confirmation, writes the firmware,
verifies it, resets the board, and releases DTR/RTS low.

### Android with Termux

Install Termux:API, Python, clang, libusb, and esptool, then build the small USB
helpers once:

```sh
pkg install python clang libusb termux-api
python -m pip install --upgrade esptool
./scripts/build-host-termux.sh
./scripts/flash-termux.sh /dev/bus/usb/001/00X
```

The Android USB path changes when the board re-enumerates. The script detects
that change when only one USB device is present; otherwise it stops and asks
you to select the device explicitly.

### Linux or macOS

Install Python and esptool, then pass the serial port:

```sh
python3 -m pip install --upgrade esptool
./scripts/flash-posix.sh /dev/ttyACM0
```

On macOS the port normally looks like `/dev/cu.usbmodem*`.

See [docs/FLASHING.md](docs/FLASHING.md) for troubleshooting, recovery, manual
commands, and safety behavior.

## Talk to the controller

At 115200 baud the console accepts:

```text
ID DUMP PKT GET DEL STATS SAVE LOAD CLEAR TENSOR TSET TRESET MODEL MLOAD MINFER MCLEAR BENCH HELP
```

Start with `ID`, `STATS`, and `TENSOR`. `HELP` prints the packet syntax.
`CLEAR`, `DEL`, `SAVE`, `LOAD`, `PKT`, `TSET`, and `TRESET` change controller
state; inspect the command before sending it.

`MODEL`, `MLOAD`, `MINFER`, and `MCLEAR` operate on a replaceable
9-input/8-output execution head; they never alter the OS packet-scheduling tensor.
The authoritative weights remain eight ordinary `ssos.packet.v1` records named
`model:w:0` through `model:w:7`; `MLOAD` reconstructs the fast float matrix from
their signed Q10 bodies. `SAVE` persists those packets with the rest of the
bank. After this firmware
has been flashed once, a Windows model update needs no firmware flash:

```powershell
.\scripts\install-model-windows.ps1 -Port COM4
```

The included `models/basic_surv_esp4` example is a 72-weight head distilled
from the accepted `basic_surv` policy. Its companion NPZ contains the learned
48-to-8 projection that a laptop, Pi, or Uno Q uses to form eight latent
coordinates; the ninth transmitted coordinate is the constant `1.0` bias.
See the model's README for measured held-out and rollout results.

## Build from source

The reference build uses Arduino-ESP32 3.3.5 and this FQBN:

```text
esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,UploadMode=default,FlashMode=qio,FlashSize=16M,PSRAM=disabled,PartitionScheme=app3M_fat9M_16MB
```

Install `arduino-cli`, install the pinned ESP32 core, and run `./build.sh`.
The release binaries in `images/flash` are kept separate from local build
output.

## Benchmark interpretation

The traces in `traces/` contain device output with the unique hardware address
redacted. Only equal-input,
equal-weight, equal-MAC comparisons are reported as equivalent work.
`hello_world` is a different model and is explicitly labeled `UNEQUAL`; it is
not the reported speedup.

The fused 9-to-8 kernel is timed directly. Do not estimate it by multiplying a
9-to-1 measurement by eight.

## Important safety notes

- Never leave DTR asserted. GPIO0/BOOT is controlled by DTR on the tested board.
- Do not hold BOOT while using the guided scripts.
- Do not enable OPI PSRAM for the supplied build.
- Never guess a port when multiple boards are connected.
- A successful hash check proves file integrity, not hardware compatibility.
- Flashing replaces the current application. Export anything you need first.

## Project status

This is an experimental ESP32-S3 reference implementation, not a general
purpose operating system or a safety-certified controller.
