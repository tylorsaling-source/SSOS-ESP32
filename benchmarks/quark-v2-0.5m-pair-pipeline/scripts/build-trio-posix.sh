#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sketch="$root/firmware/quark_trio_pipeline"
fqbn='esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,FlashMode=qio,FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB'

for role in worker1 worker2 master; do
  case "$role" in
    master) define='-DQUARK_ROLE_TRIO_PIPE_MASTER' ;;
    worker1) define='-DQUARK_ROLE_TRIO_PIPE_WORKER1' ;;
    worker2) define='-DQUARK_ROLE_TRIO_PIPE_WORKER2' ;;
  esac
  arduino-cli compile --clean --fqbn "$fqbn" \
    --build-property 'compiler.optimization_flags=-O2' \
    --build-property "compiler.cpp.extra_flags=$define" \
    --build-path "$root/build/trio-$role" "$sketch"
done
