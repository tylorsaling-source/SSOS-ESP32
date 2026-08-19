param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('master', 'worker')]
    [string]$Role,

    [Parameter(Mandatory = $true)]
    [string]$Port
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Common = Join-Path $Root 'prebuilt\common'
$Application = Join-Path $Root "prebuilt\$Role\app.bin"

Write-Host "Target role: $Role"
Write-Host "Target port: $Port"
Write-Host 'This replaces the bootloader, partition table and application regions.'

$Arguments = @(
    '--chip', 'esp32s3', '--port', $Port, '--baud', '921600',
    'write-flash',
    '0x0000', (Join-Path $Common 'bootloader.bin'),
    '0x8000', (Join-Path $Common 'partitions.bin'),
    '0xe000', (Join-Path $Common 'boot_app0.bin'),
    '0x10000', $Application
)

python -m esptool @Arguments
if ($LASTEXITCODE -ne 0) { throw "flash failed: $Role on $Port" }
