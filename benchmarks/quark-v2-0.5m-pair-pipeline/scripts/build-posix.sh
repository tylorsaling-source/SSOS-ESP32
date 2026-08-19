#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sketch="$root/firmware/quark_pair_pipeline"
fqbn='esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,FlashMode=qio,FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB'

for role in worker master; do
  if [ "$role" = master ]; then
    define='-DQUARK_ROLE_PAIR_PIPE_MASTER'
  else
    define='-DQUARK_ROLE_PAIR_PIPE_WORKER'
  fi
  arduino-cli compile --clean --fqbn "$fqbn" \
    --build-property 'compiler.optimization_flags=-O2' \
    --build-property "compiler.cpp.extra_flags=$define" \
    --build-path "$root/build/$role" "$sketch"
done
