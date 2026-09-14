# Flashing and recovery

Flashing installs the SSOS firmware application and its two seed controller
records. The published images do not install V2 model rows. Additional packet
state and model rows are sent afterward through the serial protocol. `SAVE`
forces an immediate persistence attempt; the runtime can also persist after its
adaptive background flush threshold.

## Before connecting the board

Confirm that the target is an ESP32-S3-WROOM-1U N16R8 with 16 MB flash. The
prebuilt release is not a universal ESP32 image.

Close Arduino Serial Monitor, PuTTY, VS Code serial monitors, and any other
program holding the selected port. Use a data-capable USB cable and connect the
board directly when possible.

The release uses this flash map:

| Offset | Image |
| ---: | --- |
| `0x0000` | `ssos_kernel.ino.bootloader.bin` |
| `0x8000` | `ssos_kernel.ino.partitions.bin` |
| `0xe000` | `boot_app0.bin` |
| `0x10000` | `ssos_kernel.ino.bin` |

All four files must pass `images/flash/SHA256SUMS` before writing starts.

## V2.0.1: initialize leftover settings for a new installation

An older application's saved settings can leave too little usable NVS space
for V2 to save its packet bank, even when inference works. V2.0.1's Windows
proof command initializes this region by default, with a notice before the
confirmation. It verifies the images, flashes and verifies them, then clears
only the release NVS partition at `0x9000`, length `0x5000` (20 KiB).

```powershell
.\scripts\validate-v2-windows.cmd -Port COM20
.\scripts\flash-windows.cmd -Port COM20 -InitializeSettings
```

```sh
sh scripts/flash-posix.sh /dev/ttyACM0 --initialize-settings
sh scripts/flash-termux.sh /dev/bus/usb/001/002 --initialize-settings
```

Flash-only installers preserve NVS unless this option is supplied. The
Windows proof command's `-KeepSettings` switch opts out explicitly. Use
`-ValidateOnly` on Windows or `--validate-only` on POSIX/Termux to inspect the
plan without opening a device. Python 3.10+, Esptool 5.1+, and PySerial are
required for the Windows proof; use `SSOS_PYTHON` to select a Python executable
for POSIX/Termux if it is not named `python3`.

Initialization permanently discards saved settings/model rows. It never reads
them into a backup, erases the full chip, or runs as an automatic response to
an ordinary `SAVE`. The helper verifies release image checksums and rejects
a different/overlapping NVS partition layout before any erase. COM3 is refused.

## Windows

Run `scripts\flash-windows.cmd`. The launcher uses the signed PowerShell
installation already included with Windows; the firmware script itself is
readable at `scripts\flash-windows.ps1`.

When exactly one `VID_303A&PID_1001` serial device is present, the script can
select it. With zero or multiple matches, pass `-Port COM<number>` explicitly.

The confirmation prompt includes the selected COM port. This prevents an Enter
key or copied command from silently flashing a different board.

Common failures:

- **Python was not found:** reinstall Python and enable Add Python to PATH.
- **No module named esptool:** run `py -3 -m pip install --upgrade esptool`.
- **Access denied:** close every serial monitor using that COM port.
- **No compatible port found:** check Device Manager under Ports and USB
  devices, then pass the visible COM port explicitly.

## Termux

Termux does not expose the board as a normal `/dev/tty` device. The supplied
helpers use the file descriptor granted by `termux-usb`.

Run `scripts/build-host-termux.sh` once after installing clang and libusb. Then
pass the exact USB path shown by `termux-usb -l` to
`scripts/flash-termux.sh`.

Do not hold BOOT. `usb_bl_reset` deliberately pulses into the ROM bootloader;
`usb_app_reset` explicitly releases DTR and pulses RTS to start the app.

## Linux and macOS

Run `scripts/flash-posix.sh <serial-port>`. The script does not guess the port.
Linux users may need membership in the distribution's serial-device group or a
udev rule. macOS usually names the device `/dev/cu.usbmodem*`.
The shell checksum check requires `sha256sum` (GNU coreutils on macOS).

## Recovery

1. Disconnect power for ten seconds.
2. Reconnect with one known-good data cable and no serial monitor open.
3. Run the guided script again and select the exact device.
4. If automatic reset fails, tap RESET once when esptool begins connecting.
   Do not keep BOOT held.
5. After a successful write, reconnect and send `ID` at 115200 baud.

Expected identity fields include `chip=esp32s3`, `proto=ssos.packet.v1`, and
`fuse=9to8`. The board-specific MAC is intentionally not part of public
documentation.

## What the scripts do not do

They do not erase the full flash, change fuses, enable flash encryption, alter
secure boot, or flash any device without an explicit confirmation. They write
the four documented image ranges and perform a digest verification; when
settings initialization is selected, they also clear only the documented
20 KiB NVS range after image verification.
