param(
    [ValidateSet('all', 'master', 'worker1', 'worker2')]
    [string]$Role = 'all'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Sketch = Join-Path $Root 'firmware\quark_trio_pipeline'
$Fqbn = 'esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc,FlashMode=qio,FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB'
$Roles = if ($Role -eq 'all') { @('worker1', 'worker2', 'master') } else { @($Role) }
$Defines = @{
    master = '-DQUARK_ROLE_TRIO_PIPE_MASTER'
    worker1 = '-DQUARK_ROLE_TRIO_PIPE_WORKER1'
    worker2 = '-DQUARK_ROLE_TRIO_PIPE_WORKER2'
}

foreach ($Item in $Roles) {
    $Output = Join-Path $Root "build\trio-$Item"
    arduino-cli compile --clean --fqbn $Fqbn `
        --build-property 'compiler.optimization_flags=-O2' `
        --build-property "compiler.cpp.extra_flags=$($Defines[$Item])" `
        --build-path $Output $Sketch
    if ($LASTEXITCODE -ne 0) { throw "trio build failed: $Item" }
}
