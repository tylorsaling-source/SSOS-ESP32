[CmdletBinding()]
param(
    [string]$Port,
    [ValidateRange(115200, 921600)]
    [int]$Baud = 460800,
    [switch]$Yes,
    [switch]$SkipFlash
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$harness = Join-Path $repoRoot 'validation\v2-hardware\validate_v2_hardware.py'

function Find-Python {
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) { return @{ Exe = $py.Source; Prefix = @('-3') } }
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) { return @{ Exe = $python.Source; Prefix = @() } }
    throw 'Python 3 was not found. Install it from python.org and enable Add Python to PATH.'
}

function Invoke-Python {
    param([string[]]$Arguments)
    & $script:python.Exe @($script:python.Prefix) @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python command failed with exit code $LASTEXITCODE." }
}

function Find-CompatiblePorts {
    $found = @()
    $devices = Get-CimInstance Win32_PnPEntity -ErrorAction Stop |
        Where-Object { $_.PNPDeviceID -match 'VID_303A&PID_1001' }
    foreach ($device in $devices) {
        if ($device.Name -match '\((COM\d+)\)') { $found += $Matches[1].ToUpperInvariant() }
    }
    return @($found | Sort-Object -Unique)
}

try {
    Write-Host 'SSOS-ESP32 V2 physical proof' -ForegroundColor Cyan
    Write-Host 'This workflow will flash one compatible board, install 72 weights, reset it, and prove the outputs.'
    Write-Host ''

    Write-Host '[1/6] Checking the computer...' -ForegroundColor Cyan
    $script:python = Find-Python
    try { Invoke-Python @('-m', 'esptool', 'version') }
    catch { throw 'Esptool is missing. Run: py -3 -m pip install --upgrade esptool' }
    try { Invoke-Python @('-c', 'import serial; print("PySerial ready")') }
    catch { throw 'PySerial is missing. Run: py -3 -m pip install pyserial' }

    Write-Host '[2/6] Finding the board...' -ForegroundColor Cyan
    if ($Port) {
        $Port = $Port.ToUpperInvariant()
        if ($Port -notmatch '^COM\d+$') { throw "Invalid Windows serial port: $Port" }
    } else {
        $ports = @(Find-CompatiblePorts)
        $ports = @($ports | Where-Object { $_ -ne 'COM3' })
        if ($ports.Count -eq 0) { throw 'No compatible non-COM3 ESP32-S3 was found. Reconnect the new board and try again.' }
        if ($ports.Count -gt 1) { throw "More than one compatible board was found: $($ports -join ', '). Rerun with -Port COM<number>." }
        $Port = $ports[0]
    }
    if ($Port -eq 'COM3') { throw 'COM3 is protected. This package will never open or flash COM3.' }
    Write-Host "      Selected $Port. COM3 remains protected." -ForegroundColor Green

    Write-Host '[3/6] Verifying release files...' -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot 'flash-windows.ps1') -ValidateOnly
    if ($LASTEXITCODE -ne 0) { throw 'Release-image validation failed.' }

    if ($SkipFlash) {
        Write-Host '[4/6] Flash skipped by request; validating the firmware already on the board.' -ForegroundColor Yellow
        $flashStatus = 'preexisting'
    } else {
        Write-Host '[4/6] Flashing and read-back verifying V2...' -ForegroundColor Cyan
        $flashArguments = @{ Port = $Port; Baud = $Baud }
        if ($Yes) { $flashArguments.Yes = $true }
        & (Join-Path $PSScriptRoot 'flash-windows.ps1') @flashArguments
        if ($LASTEXITCODE -ne 0) { throw 'Firmware flash failed.' }
        Start-Sleep -Seconds 2
        $flashStatus = 'performed-this-run'
    }

    Write-Host '[5/6] Installing and checking the packet-backed model...' -ForegroundColor Cyan
    Invoke-Python @($harness, '--port', $Port, '--flash-status', $flashStatus)

    Write-Host '[6/6] Finished.' -ForegroundColor Cyan
    Write-Host 'PASS: the complete V2 physical proof passed. The evidence paths are printed above.' -ForegroundColor Green
} catch {
    Write-Host ''
    Write-Host "FAIL: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Nothing else will be attempted. Correct the displayed problem and rerun the same command.' -ForegroundColor Yellow
    exit 1
}
