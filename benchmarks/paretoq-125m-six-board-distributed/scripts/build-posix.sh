#!/usr/bin/env sh
set -eu
package=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
fqbn='esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,CPUFreq=240,FlashMode=qio,FlashSize=16M,PartitionScheme=custom,PSRAM=opi,DebugLevel=none,EraseFlash=none'
arduino-cli compile --fqbn "$fqbn" --build-property 'compiler.optimization_flags=-O2' --output-dir "$package/build/arduino-node" "$package/firmware/paretoq_node"
