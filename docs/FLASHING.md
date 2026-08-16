# Flashing and recovery

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
only the four documented ranges and perform a read-back verification.
