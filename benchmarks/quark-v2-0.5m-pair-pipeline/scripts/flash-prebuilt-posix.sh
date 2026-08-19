#!/usr/bin/env sh
set -eu

if [ "$#" -ne 2 ]; then
  echo "usage: $0 master|worker SERIAL_PORT" >&2
  exit 2
fi

role=$1
port=$2
case "$role" in
  master|worker) ;;
  *) echo "role must be master or worker" >&2; exit 2 ;;
esac

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
echo "Target role: $role"
echo "Target port: $port"
echo 'This replaces the bootloader, partition table and application regions.'

python3 -m esptool --chip esp32s3 --port "$port" --baud 921600 write-flash \
  0x0000 "$root/prebuilt/common/bootloader.bin" \
  0x8000 "$root/prebuilt/common/partitions.bin" \
  0xe000 "$root/prebuilt/common/boot_app0.bin" \
  0x10000 "$root/prebuilt/$role/app.bin"
