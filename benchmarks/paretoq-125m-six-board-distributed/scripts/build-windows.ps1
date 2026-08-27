$ErrorActionPreference = 'Stop'
$Package = Split-Path -Parent $PSScriptRoot
$Sketch = Join-Path $Package 'firmware\paretoq_node'
$Output = Join-Path $Package 'build\arduino-node'
$Fqbn = 'esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,CPUFreq=240,FlashMode=qio,FlashSize=16M,PartitionScheme=custom,PSRAM=opi,DebugLevel=none,EraseFlash=none'
arduino-cli compile --fqbn $Fqbn --build-property 'compiler.optimization_flags=-O2' --output-dir $Output $Sketch
