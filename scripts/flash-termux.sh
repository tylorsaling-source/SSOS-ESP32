#!/data/data/com.termux/files/usr/bin/sh
set -eu
PYTHON=${SSOS_PYTHON:-python3}

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
PREFIX=${PREFIX:-/data/data/com.termux/files/usr}
USB="$PREFIX/bin/termux-usb"
IMAGE_DIR="$ROOT/images/flash"
PTYFILE="$ROOT/host/pty.path"
DEV=${SSOS_USB:-}
INITIALIZE_SETTINGS=0
VALIDATE_ONLY=0
YES=0
for arg in "$@"; do
  case "$arg" in
    --initialize-settings) INITIALIZE_SETTINGS=1 ;;
    --validate-only) VALIDATE_ONLY=1 ;;
    --yes) YES=1 ;;
    --*) echo "flash: unknown option: $arg" >&2; exit 2 ;;
    *) DEV=$arg ;;
  esac
done
case "$DEV" in [Cc][Oo][Mm]3) echo 'COM3 is protected.' >&2; exit 2 ;; esac
sh "$ROOT/scripts/verify-release.sh"
if [ "$INITIALIZE_SETTINGS" = 1 ]; then
  "$PYTHON" "$ROOT/scripts/initialize-settings.py" --validate-only
fi
if [ "$VALIDATE_ONLY" = 1 ]; then
  echo 'Release plan validated; no USB device opened, no firmware written, no settings erased.'
  exit 0
fi

for tool in "$USB" "$ROOT/host/usb_bl_reset" "$ROOT/host/usb_app_reset" "$ROOT/host/cdc-pty"; do
  [ -x "$tool" ] || {
    echo "flash: missing executable $tool" >&2
    echo "run ./scripts/build-host-termux.sh first" >&2
    exit 2
  }
done
"$PYTHON" -m esptool version >/dev/null 2>&1 || {
  echo "flash: install esptool with: python -m pip install --upgrade esptool" >&2
  exit 2
}

if [ -z "$DEV" ]; then
  devices=$($USB -l 2>/dev/null | sed -n 's/.*"\(\/dev\/bus\/usb\/[0-9]*\/[0-9]*\)".*/\1/p')
  count=$(printf '%s\n' "$devices" | sed '/^$/d' | wc -l | tr -d ' ')
  if [ "$count" = 1 ]; then
    DEV=$devices
  else
    echo "flash: found $count USB devices; pass the exact /dev/bus/usb path" >&2
    $USB -l >&2 || true
    exit 2
  fi
fi

echo "Target USB path: $DEV"
echo "Board must be ESP32-S3-WROOM-1U N16R8 with 16 MB flash."
if [ "$INITIALIZE_SETTINGS" = 1 ]; then
  echo 'Initialize leftover settings: ON. Saved NVS settings/model rows (20 KiB) will be erased.'
else
  echo 'Initialize leftover settings: OFF. Use --initialize-settings for a new/reused-board install.'
fi
if [ "$YES" != 1 ]; then
printf 'Type FLASH %s to continue: ' "$DEV"
IFS= read -r answer
[ "$answer" = "FLASH $DEV" ] || {
  echo "flash: confirmation did not match; nothing was written" >&2
  exit 3
}
fi

$USB -e "$ROOT/host/usb_bl_reset" "$DEV"
sleep 1
devices=$($USB -l 2>/dev/null | sed -n 's/.*"\(\/dev\/bus\/usb\/[0-9]*\/[0-9]*\)".*/\1/p')
count=$(printf '%s\n' "$devices" | sed '/^$/d' | wc -l | tr -d ' ')
if [ "$count" = 1 ]; then DEV=$devices; fi

rm -f "$PTYFILE"
SSOS_PTY_FILE="$PTYFILE" SSOS_NO_BL_RESET=1 \
  $USB -e "$ROOT/host/cdc-pty" "$DEV" >/tmp/ssos-cdc-pty.log 2>&1 &
BRIDGE_PID=$!
cleanup() {
  kill "$BRIDGE_PID" 2>/dev/null || true
  rm -f "$PTYFILE"
}
trap cleanup EXIT INT TERM

i=0
while [ "$i" -lt 40 ] && [ ! -s "$PTYFILE" ]; do
  kill -0 "$BRIDGE_PID" 2>/dev/null || {
    cat /tmp/ssos-cdc-pty.log >&2 || true
    exit 4
  }
  i=$((i + 1))
  sleep 0.25
done
PTY=$(tr -d '\r\n' < "$PTYFILE")
[ -n "$PTY" ] || {
  cat /tmp/ssos-cdc-pty.log >&2 || true
  echo "flash: no PTY was created" >&2
  exit 4
}

"$PYTHON" -m esptool --chip esp32s3 --port "$PTY" --baud 115200 \
  --before no_reset --after no_reset --no-stub write_flash \
  --flash_mode dio --flash_freq 80m --flash_size 16MB \
  0x0000 "$IMAGE_DIR/ssos_kernel.ino.bootloader.bin" \
  0x8000 "$IMAGE_DIR/ssos_kernel.ino.partitions.bin" \
  0xe000 "$IMAGE_DIR/boot_app0.bin" \
  0x10000 "$IMAGE_DIR/ssos_kernel.ino.bin"

"$PYTHON" -m esptool --chip esp32s3 --port "$PTY" --baud 115200 \
  --before no_reset --after no_reset --no-stub verify_flash \
  0x0000 "$IMAGE_DIR/ssos_kernel.ino.bootloader.bin" \
  0x8000 "$IMAGE_DIR/ssos_kernel.ino.partitions.bin" \
  0xe000 "$IMAGE_DIR/boot_app0.bin" \
  0x10000 "$IMAGE_DIR/ssos_kernel.ino.bin"

if [ "$INITIALIZE_SETTINGS" = 1 ]; then
  "$PYTHON" "$ROOT/scripts/initialize-settings.py" --port "$PTY" --baud 115200 \
    --before no-reset --after no-reset --no-stub --yes
fi

cleanup
trap - EXIT INT TERM
$USB -e "$ROOT/host/usb_app_reset" "$DEV"
echo "Flash and verification completed. Use ssos_cmd -c ID to verify the application."
