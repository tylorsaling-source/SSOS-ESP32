[CmdletBinding()]
param(
    [int]$Count = 1024,
    [int]$Seed = 1337,
    [string]$Python = 'py -3'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Local = Join-Path $Here '_local'
$States = Join-Path $Local 'states.jsonl'
$Teacher = Join-Path $Local 'jev_teacher.jsonl'
$OutDir = Join-Path $Local 'distilled'
$PromptedForKey = $false

New-Item -ItemType Directory -Force -Path $Local | Out-Null

if (-not $env:TYPESAFE_API_KEY) {
    Write-Host 'TYPESAFE_API_KEY is not set for this process.'
    $secure = Read-Host 'Paste your TypeSafe API key (input hidden)' -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $env:TYPESAFE_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        $PromptedForKey = $true
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

if (-not $env:TYPESAFE_API_KEY) { throw 'No TypeSafe API key supplied.' }

$parts = $Python -split ' '
$exe = $parts[0]
$prefix = @()
if ($parts.Count -gt 1) { $prefix = @($parts[1..($parts.Count - 1)]) }

function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$PyArgs)
    & $exe @prefix @PyArgs
    if ($LASTEXITCODE -ne 0) { throw "Python command failed with exit code $LASTEXITCODE" }
}

try {
    Write-Host 'Installing/updating experiment dependencies...'
    Invoke-Python -m pip install --upgrade numpy typesafe-sdk

    Write-Host "Generating $Count deterministic SSOS-like states..."
    Invoke-Python (Join-Path $Here 'generate_states.py') $States --count $Count --seed $Seed

    if (Test-Path $Teacher) { Remove-Item -Force $Teacher }
    Write-Host 'Calling Jev for eight atomic judgments per state...'
    Invoke-Python (Join-Path $Here 'collect_jev_teacher.py') $States $Teacher

    if (Test-Path $OutDir) { Remove-Item -Recurse -Force $OutDir }
    Write-Host 'Distilling Jev probabilities into the fixed SSOS V2 9->8 / 72-weight Q10 head...'
    Invoke-Python (Join-Path $Here 'distill_system_one.py') --teacher-jsonl $Teacher --seed $Seed --out $OutDir

    $reportPath = Join-Path $OutDir 'report.json'
    $report = Get-Content -Raw -LiteralPath $reportPath | ConvertFrom-Json
    $worst = $report.per_head | Sort-Object threshold_agreement_q10 | Select-Object -First 1
    $pass = ([double]$report.mean_threshold_agreement_q10 -ge 0.90) -and
            ([double]$report.mean_mae_q10 -le 0.08) -and
            ([double]$report.max_probability_delta_float_vs_q10 -le 0.005) -and
            ([double]$worst.threshold_agreement_q10 -ge 0.80)

    Write-Host ''
    Write-Host '=== REAL JEV -> SSOS V2 RESULT ==='
    Write-Host ('Mean threshold agreement : {0:P2}' -f [double]$report.mean_threshold_agreement_q10)
    Write-Host ('Mean probability MAE      : {0:N5}' -f [double]$report.mean_mae_q10)
    Write-Host ('Max Q10 probability delta : {0:N6}' -f [double]$report.max_probability_delta_float_vs_q10)
    Write-Host ('Worst head                : {0} ({1:P2})' -f $worst.name, [double]$worst.threshold_agreement_q10)
    Write-Host ('Gate                      : {0}' -f $(if ($pass) { 'PASS' } else { 'FAIL' }))
    Write-Host "Report: $reportPath"
    Write-Host "V2-compatible rows: $(Join-Path $OutDir 'ssos_head_rows.json')"

    if (-not $pass) { exit 2 }
} finally {
    if ($PromptedForKey) {
        Remove-Item Env:TYPESAFE_API_KEY -ErrorAction SilentlyContinue
    }
}
