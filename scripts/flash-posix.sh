#!/usr/bin/env sh
set -eu
PYTHON=${SSOS_PYTHON:-python3}

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
IMAGE_DIR="$ROOT/images/flash"
PORT=
BAUD=${SSOS_BAUD:-460800}
INITIALIZE_SETTINGS=0
VALIDATE_ONLY=0
YES=0
for arg in "$@"; do
  case "$arg" in
    --initialize-settings) INITIALIZE_SETTINGS=1 ;;
    --validate-only) VALIDATE_ONLY=1 ;;
    --yes) YES=1 ;;
    --*) echo "flash: unknown option: $arg" >&2; exit 2 ;;
    *) [ -z "$PORT" ] || { echo 'flash: only one port is allowed' >&2; exit 2; }; PORT=$arg ;;
  esac
done
case "$PORT" in [Cc][Oo][Mm]3) echo 'COM3 is protected.' >&2; exit 2 ;; esac

sh "$ROOT/scripts/verify-release.sh"
if [ "$INITIALIZE_SETTINGS" = 1 ]; then
  "$PYTHON" "$ROOT/scripts/initialize-settings.py" --validate-only
fi
if [ "$VALIDATE_ONLY" = 1 ]; then
  echo 'Release plan validated; no device opened, no firmware written, no settings erased.'
  exit 0
fi

if [ -z "$PORT" ]; then
  echo "usage: $0 /dev/ttyACM0 [--initialize-settings] [--yes] [--validate-only]" >&2
  echo "macOS example: $0 /dev/cu.usbmodem1101" >&2
  exit 2
fi
if [ ! -e "$PORT" ]; then
  echo "flash: serial port does not exist: $PORT" >&2
  exit 2
fi

"$PYTHON" -m esptool version >/dev/null 2>&1 || {
  echo "flash: install esptool with: python3 -m pip install --upgrade esptool" >&2
  exit 2
}

echo "Target: ESP32-S3 on $PORT"
if [ "$INITIALIZE_SETTINGS" = 1 ]; then
  echo 'Initialize leftover settings: ON. Saved NVS settings/model rows (20 KiB) will be erased.'
else
  echo 'Initialize leftover settings: OFF. Use --initialize-settings for a new/reused-board install.'
fi
echo "  0x0000  ssos_kernel.ino.bootloader.bin"
echo "  0x8000  ssos_kernel.ino.partitions.bin"
echo "  0xe000  boot_app0.bin"
echo "  0x10000 ssos_kernel.ino.bin"
if [ "$YES" != 1 ]; then
printf 'Type FLASH %s to continue: ' "$PORT"
IFS= read -r answer
[ "$answer" = "FLASH $PORT" ] || {
  echo "flash: confirmation did not match; nothing was written" >&2
  exit 3
}
fi

"$PYTHON" -m esptool --chip esp32s3 --port "$PORT" --baud "$BAUD" \
  --before default_reset --after hard_reset write_flash \
  --flash_mode dio --flash_freq 80m --flash_size 16MB \
  0x0000 "$IMAGE_DIR/ssos_kernel.ino.bootloader.bin" \
  0x8000 "$IMAGE_DIR/ssos_kernel.ino.partitions.bin" \
  0xe000 "$IMAGE_DIR/boot_app0.bin" \
  0x10000 "$IMAGE_DIR/ssos_kernel.ino.bin"

"$PYTHON" -m esptool --chip esp32s3 --port "$PORT" --baud "$BAUD" \
  --before default_reset --after hard_reset verify_flash \
  0x0000 "$IMAGE_DIR/ssos_kernel.ino.bootloader.bin" \
  0x8000 "$IMAGE_DIR/ssos_kernel.ino.partitions.bin" \
  0xe000 "$IMAGE_DIR/boot_app0.bin" \
  0x10000 "$IMAGE_DIR/ssos_kernel.ino.bin"

if [ "$INITIALIZE_SETTINGS" = 1 ]; then
  "$PYTHON" "$ROOT/scripts/initialize-settings.py" --port "$PORT" --baud "$BAUD" --yes
fi

echo "Flash and verification completed. Open $PORT at 115200 baud and send ID."
