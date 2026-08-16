[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Port,
    [string]$Model = (Join-Path (Split-Path -Parent $PSScriptRoot) 'models\basic_surv_esp4\ssos_head_rows.json'),
    [switch]$Yes
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Port = $Port.ToUpperInvariant()
if ($Port -notmatch '^COM\d+$') { throw "Invalid Windows serial port: $Port" }
if (-not (Test-Path -LiteralPath $Model)) { throw "Missing model: $Model" }

$document = Get-Content -LiteralPath $Model -Raw | ConvertFrom-Json
if ($document.rows.Count -ne 8) { throw 'Model must contain exactly eight rows.' }
$weights = [System.Collections.Generic.List[double]]::new()
$q10Rows = [System.Collections.Generic.List[object]]::new()
foreach ($row in $document.rows) {
    if ($row.Count -ne 9) { throw 'Every model row must contain exactly nine weights.' }
    foreach ($value in $row) {
        $number = [double]$value
        if ([double]::IsNaN($number) -or [double]::IsInfinity($number) -or $number -lt -8 -or $number -gt 8) {
            throw "Invalid model weight: $number"
        }
        $weights.Add($number)
    }
    $q10Rows.Add(@($row | ForEach-Object { [int][Math]::Round(([double]$_) * 1024.0, [MidpointRounding]::ToEven) }))
}

Write-Host "Target: $Port"
Write-Host "Model:  $Model"
Write-Host 'Action: replace eight packet-bank weight rows, load them into the execution cache, and persist the packet bank; firmware is not flashed.'
if (-not $Yes) {
    $answer = Read-Host "Type MODEL $Port to continue"
    if ($answer -cne "MODEL $Port") { throw 'Confirmation did not match; nothing was written.' }
}

$serial = [System.IO.Ports.SerialPort]::new($Port, 115200, 'None', 8, 'One')
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.NewLine = "`n"
$serial.ReadTimeout = 2500
$serial.WriteTimeout = 2500

function Invoke-SsosCommand {
    param([string]$Command, [string]$Expected)
    $script:serial.WriteLine($Command)
    $deadline = [DateTime]::UtcNow.AddSeconds(4)
    do {
        try {
            $line = $script:serial.ReadLine().Trim()
            if ($line.StartsWith($Expected, [StringComparison]::Ordinal)) { return $line }
            if ($line.StartsWith('ERR ', [StringComparison]::Ordinal)) { throw "Device rejected '$Command': $line" }
        } catch [System.TimeoutException] {
        }
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "No '$Expected' response for '$Command'."
}

try {
    $serial.Open()
    Start-Sleep -Milliseconds 250
    $serial.DiscardInBuffer()
    $status = Invoke-SsosCommand -Command 'MODEL' -Expected 'OK model'
    Write-Host $status
    Invoke-SsosCommand -Command 'MCLEAR' -Expected 'OK model packets cleared' | Out-Null
    for ($row = 0; $row -lt 8; $row++) {
        $body = $q10Rows[$row] -join ','
        $command = "PKT id=model:w:$row d=120,$row,0,0,0,0,0,0,0 role=runtime perm=open body=$body"
        Invoke-SsosCommand -Command $command -Expected "OK recv PKT id=model:w:$row" | Out-Null
    }
    Invoke-SsosCommand -Command 'MLOAD' -Expected 'OK model loaded from packet bank' | Out-Null
    Invoke-SsosCommand -Command 'SAVE' -Expected 'OK saved' | Out-Null
    Invoke-SsosCommand -Command 'LOAD' -Expected 'OK loaded' | Out-Null
    $status = Invoke-SsosCommand -Command 'MODEL' -Expected 'OK model ready=1 source=packet-bank encoding=q10 rows=8'
    Write-Host $status
    $testInput = @(0.125, -0.25, 0.375, -0.5, 0.625, -0.75, 0.875, -1.0, 1.0)
    $inputText = ($testInput | ForEach-Object { ([double]$_).ToString('R', [Globalization.CultureInfo]::InvariantCulture) }) -join ','
    $line = Invoke-SsosCommand -Command "MINFER x=$inputText" -Expected 'OK model y8='
    if ($line -notmatch '^OK model y8=([^ ]+) argmax=(\d+)$') { throw "Unexpected inference response: $line" }
    $actual = $Matches[1].Split(',') | ForEach-Object { [double]::Parse($_, [Globalization.CultureInfo]::InvariantCulture) }
    for ($row = 0; $row -lt 8; $row++) {
        $expected = 0.0
        for ($column = 0; $column -lt 9; $column++) {
            $expected += (([double]$q10Rows[$row][$column]) / 1024.0) * $testInput[$column]
        }
        if ([Math]::Abs($actual[$row] - $expected) -gt 0.00002) {
            throw "Readback inference mismatch at output ${row}: expected $expected, got $($actual[$row])"
        }
    }
    Write-Host "Packet-backed model installed, reloaded, and all 72 weights inference-checked on $Port."
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
}
