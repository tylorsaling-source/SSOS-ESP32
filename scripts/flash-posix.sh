#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
IMAGE_DIR="$ROOT/images/flash"
PORT=${1:-}
BAUD=${SSOS_BAUD:-460800}

if [ -z "$PORT" ]; then
  echo "usage: $0 /dev/ttyACM0" >&2
  echo "macOS example: $0 /dev/cu.usbmodem1101" >&2
  exit 2
fi
if [ ! -e "$PORT" ]; then
  echo "flash: serial port does not exist: $PORT" >&2
  exit 2
fi

sh "$ROOT/scripts/verify-release.sh"
python3 -m esptool version >/dev/null 2>&1 || {
  echo "flash: install esptool with: python3 -m pip install --upgrade esptool" >&2
  exit 2
}

echo "Target: ESP32-S3 on $PORT"
echo "  0x0000  ssos_kernel.ino.bootloader.bin"
echo "  0x8000  ssos_kernel.ino.partitions.bin"
echo "  0xe000  boot_app0.bin"
echo "  0x10000 ssos_kernel.ino.bin"
printf 'Type FLASH %s to continue: ' "$PORT"
IFS= read -r answer
[ "$answer" = "FLASH $PORT" ] || {
  echo "flash: confirmation did not match; nothing was written" >&2
  exit 3
}

python3 -m esptool --chip esp32s3 --port "$PORT" --baud "$BAUD" \
  --before default_reset --after hard_reset write_flash \
  --flash_mode dio --flash_freq 80m --flash_size 16MB \
  0x0000 "$IMAGE_DIR/ssos_kernel.ino.bootloader.bin" \
  0x8000 "$IMAGE_DIR/ssos_kernel.ino.partitions.bin" \
  0xe000 "$IMAGE_DIR/boot_app0.bin" \
  0x10000 "$IMAGE_DIR/ssos_kernel.ino.bin"

python3 -m esptool --chip esp32s3 --port "$PORT" --baud "$BAUD" \
  --before default_reset --after hard_reset verify_flash \
  0x0000 "$IMAGE_DIR/ssos_kernel.ino.bootloader.bin" \
  0x8000 "$IMAGE_DIR/ssos_kernel.ino.partitions.bin" \
  0xe000 "$IMAGE_DIR/boot_app0.bin" \
  0x10000 "$IMAGE_DIR/ssos_kernel.ino.bin"

echo "Flash and verification completed. Open $PORT at 115200 baud and send ID."
