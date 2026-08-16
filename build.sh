#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
CLI=${ARDUINO_CLI:-}
if [ -z "$CLI" ]; then CLI=$(command -v arduino-cli || true); fi
[ -n "$CLI" ] && [ -x "$CLI" ] || {
  echo "build: arduino-cli was not found" >&2
  echo "install it or set ARDUINO_CLI=/absolute/path/to/arduino-cli" >&2
  exit 2
}

FQBN="esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,UploadMode=default,FlashMode=qio,FlashSize=16M,PSRAM=disabled,PartitionScheme=app3M_fat9M_16MB"
BUILD_DIR=${SSOS_BUILD_DIR:-$ROOT/firmware/build}

"$CLI" compile \
  --config-file "$ROOT/arduino-cli.yaml" \
  --fqbn "$FQBN" \
  --build-path "$BUILD_DIR" \
  --warnings default \
  "$ROOT/firmware/ssos_kernel"

echo "Build completed: $BUILD_DIR/ssos_kernel.ino.bin"
