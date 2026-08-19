param(
    [ValidateSet('all', 'master', 'worker')]
    [string]$Role = 'all'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Sketch = Join-Path $Root 'firmware\quark_pair_pipeline'
$Fqbn = 'esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,FlashMode=qio,FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB'
$Roles = if ($Role -eq 'all') { @('worker', 'master') } else { @($Role) }

foreach ($Item in $Roles) {
    $Define = if ($Item -eq 'master') {
        '-DQUARK_ROLE_PAIR_PIPE_MASTER'
    } else {
        '-DQUARK_ROLE_PAIR_PIPE_WORKER'
    }
    $Output = Join-Path $Root "build\$Item"
    arduino-cli compile --clean --fqbn $Fqbn `
        --build-property 'compiler.optimization_flags=-O2' `
        --build-property "compiler.cpp.extra_flags=$Define" `
        --build-path $Output $Sketch
    if ($LASTEXITCODE -ne 0) { throw "build failed: $Item" }
}
