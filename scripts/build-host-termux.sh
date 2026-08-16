#!/data/data/com.termux/files/usr/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
PREFIX=${PREFIX:-/data/data/com.termux/files/usr}
CC=${CC:-$PREFIX/bin/clang}
INC="-I$PREFIX/include/libusb-1.0"
LIB="-L$PREFIX/lib -lusb-1.0 -lm -pthread"

[ -x "$CC" ] || {
  echo "build-host: install clang first: pkg install clang" >&2
  exit 2
}
[ -f "$PREFIX/include/libusb-1.0/libusb.h" ] || {
  echo "build-host: install libusb first: pkg install libusb" >&2
  exit 2
}

SUPPORTED="cdc-pty usb_bl_reset usb_app_reset ssos_cmd ssos_dump"
for tool in $SUPPORTED; do
  echo "building $tool"
  "$CC" -O2 -Wall -Wextra -o "$ROOT/host/$tool" "$ROOT/host/$tool.c" $INC $LIB
done

chmod +x "$ROOT/host/cdc-pty" "$ROOT/host/usb_bl_reset" \
  "$ROOT/host/usb_app_reset" "$ROOT/host/ssos_cmd" "$ROOT/host/ssos_dump"

if [ "${SSOS_BUILD_LEGACY:-0}" = "1" ]; then
  echo "WARNING: building legacy research clients; they are incompatible with the current protocol." >&2
  for tool in ssos_host ssos_model; do
    echo "building legacy $tool"
    "$CC" -O2 -Wall -Wextra -o "$ROOT/host/$tool" "$ROOT/host/$tool.c" $INC $LIB
    chmod +x "$ROOT/host/$tool"
  done
else
  echo "Skipping incompatible legacy prototypes ssos_host and ssos_model."
fi

echo "Supported Termux host tools built."
