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

for tool in cdc-pty usb_bl_reset usb_app_reset ssos_cmd ssos_host ssos_dump ssos_model; do
  echo "building $tool"
  "$CC" -O2 -Wall -Wextra -o "$ROOT/host/$tool" "$ROOT/host/$tool.c" $INC $LIB
done

chmod +x "$ROOT/host/cdc-pty" "$ROOT/host/usb_bl_reset" \
  "$ROOT/host/usb_app_reset" "$ROOT/host/ssos_cmd" \
  "$ROOT/host/ssos_host" "$ROOT/host/ssos_dump" "$ROOT/host/ssos_model"
echo "Termux host tools built."
