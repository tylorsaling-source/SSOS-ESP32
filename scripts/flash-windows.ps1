[CmdletBinding()]
param(
    [string]$Port,
    [ValidateRange(115200, 921600)]
    [int]$Baud = 460800,
    [switch]$Yes,
    [switch]$ValidateOnly,
    [switch]$SkipReadBackVerify
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$imageDir = Join-Path $repoRoot 'images\flash'
$sumFile = Join-Path $imageDir 'SHA256SUMS'
$flashMap = @(
    @{ Offset = '0x0000'; Name = 'ssos_kernel.ino.bootloader.bin' },
    @{ Offset = '0x8000'; Name = 'ssos_kernel.ino.partitions.bin' },
    @{ Offset = '0xe000'; Name = 'boot_app0.bin' },
    @{ Offset = '0x10000'; Name = 'ssos_kernel.ino.bin' }
)

function Find-Python {
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) { return @{ Exe = $py.Source; Prefix = @('-3') } }
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) { return @{ Exe = $python.Source; Prefix = @() } }
    throw 'Python 3 was not found. Install it from python.org and enable Add Python to PATH.'
}

function Invoke-Python {
    param([string[]]$Arguments)
    $exe = $script:python.Exe
    $prefix = @($script:python.Prefix)
    & $exe @prefix @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE."
    }
}

function Confirm-Images {
    if (-not (Test-Path -LiteralPath $sumFile)) {
        throw "Missing checksum file: $sumFile"
    }
    $expected = @{}
    foreach ($line in Get-Content -LiteralPath $sumFile) {
        if ($line -match '^([0-9a-fA-F]{64})\s+\*?(.+)$') {
            $expected[$Matches[2].Trim()] = $Matches[1].ToUpperInvariant()
        }
    }
    foreach ($entry in $flashMap) {
        $path = Join-Path $imageDir $entry.Name
        if (-not (Test-Path -LiteralPath $path)) { throw "Missing image: $path" }
        if (-not $expected.ContainsKey($entry.Name)) { throw "No checksum for $($entry.Name)" }
        $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
        if ($actual -ne $expected[$entry.Name]) { throw "Checksum mismatch: $($entry.Name)" }
        Write-Host "verified  $($entry.Name)"
    }
}

function Find-CompatiblePorts {
    $found = @()
    try {
        $devices = Get-CimInstance Win32_PnPEntity -ErrorAction Stop |
            Where-Object { $_.PNPDeviceID -match 'VID_303A&PID_1001' }
        foreach ($device in $devices) {
            if ($device.Name -match '\((COM\d+)\)') { $found += $Matches[1].ToUpperInvariant() }
        }
    } catch {
        Write-Warning "Automatic USB discovery was unavailable: $($_.Exception.Message)"
    }
    return @($found | Sort-Object -Unique)
}

function Release-ControlLines {
    param([string]$SelectedPort)
    try {
        $serial = [System.IO.Ports.SerialPort]::new($SelectedPort, 115200)
        $serial.DtrEnable = $false
        $serial.RtsEnable = $false
        $serial.Open()
        Start-Sleep -Milliseconds 150
        $serial.Close()
        $serial.Dispose()
        Write-Host 'released  DTR=0 RTS=0'
    } catch {
        Write-Warning 'Could not explicitly reopen the port to release DTR/RTS. Disconnect USB if the board remains in ROM mode.'
    }
}

Confirm-Images
if ($ValidateOnly) {
    Write-Host 'Release validation completed; no device was opened and nothing was written.'
    return
}
$script:python = Find-Python
try {
    Invoke-Python @('-m', 'esptool', 'version')
} catch {
    throw 'esptool is unavailable. Run: py -3 -m pip install --upgrade esptool'
}

if ($Port) {
    $Port = $Port.ToUpperInvariant()
    if ($Port -notmatch '^COM\d+$') { throw "Invalid Windows serial port: $Port" }
} else {
    $ports = @(Find-CompatiblePorts)
    if ($ports.Count -eq 1) {
        $Port = $ports[0]
    } elseif ($ports.Count -eq 0) {
        throw 'No ESP32-S3 USB Serial/JTAG port was found. Reconnect it or pass -Port COM<number>.'
    } else {
        throw "Multiple compatible ports were found: $($ports -join ', '). Pass -Port explicitly."
    }
}
if ($Port -eq 'COM3') {
    throw 'COM3 is protected. This script will never open or flash COM3.'
}

Write-Host ''
Write-Host "Target: ESP32-S3 on $Port"
Write-Host "Baud:   $Baud"
foreach ($entry in $flashMap) { Write-Host ("{0,8}  {1}" -f $entry.Offset, $entry.Name) }
Write-Host ''

if (-not $Yes) {
    $answer = Read-Host "Type FLASH $Port to continue"
    if ($answer -cne "FLASH $Port") { throw 'Confirmation did not match; nothing was written.' }
}

$pairs = @()
foreach ($entry in $flashMap) {
    $pairs += $entry.Offset
    $pairs += (Join-Path $imageDir $entry.Name)
}

try {
    Invoke-Python (@(
        '-m', 'esptool', '--chip', 'esp32s3', '--port', $Port,
        '--baud', "$Baud", '--before', 'default_reset', '--after', 'hard_reset',
        'write_flash', '--flash_mode', 'dio', '--flash_freq', '80m',
        '--flash_size', '16MB'
    ) + $pairs)

    if (-not $SkipReadBackVerify) {
        Invoke-Python (@(
            '-m', 'esptool', '--chip', 'esp32s3', '--port', $Port,
            '--baud', "$Baud", '--before', 'default_reset', '--after', 'hard_reset',
            'verify_flash'
        ) + $pairs)
    }
} finally {
    Release-ControlLines -SelectedPort $Port
}

Write-Host ''
Write-Host 'Flash and verification completed. Open the port at 115200 baud and send ID.'
