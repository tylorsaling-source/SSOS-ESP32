# Offline integration check. Only an invented test credential is used.
$ErrorActionPreference = 'Stop'
$savedEnvironmentKey = $env:TYPESAFE_API_KEY
$testRoot = Join-Path $PSScriptRoot ('_local\credential-test-' + [guid]::NewGuid().ToString('N'))
$testKey = Join-Path $testRoot 'key.dpapi'
$global:ssosTestSentinel = 'offline-test-' + [guid]::NewGuid().ToString('N')
$global:ssosTestFailCollection = $false
$global:ssosTestOutputPaths = [System.Collections.Generic.List[string]]::new()

function Read-Host {
    param($Prompt, [switch]$AsSecureString)
    ConvertTo-SecureString $global:ssosTestSentinel -AsPlainText -Force
}

function Invoke-OfflinePython {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$CommandArgs)
    $global:LASTEXITCODE = 0
    switch -Wildcard ($CommandArgs[0]) {
        '*generate_states.py' {
            if ($env:TYPESAFE_API_KEY) { throw 'Credential was loaded before collection.' }
            $global:ssosTestOutputPaths.Add($CommandArgs[1])
            Set-Content -LiteralPath $CommandArgs[1] -Value 'offline-test-artifact'
        }
        '*collect_jev_teacher.py' {
            if ($env:TYPESAFE_API_KEY -cne $global:ssosTestSentinel) { throw 'DPAPI key did not reach collector.' }
            if ($global:ssosTestFailCollection) { $global:LASTEXITCODE = 9 }
        }
        '*distill_system_one.py' {
            if ($env:TYPESAFE_API_KEY) { throw 'Credential remained after collection.' }
            $outIndex = [Array]::IndexOf($CommandArgs, '--out')
            $outputDirectory = $CommandArgs[$outIndex + 1]
            New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
            @{
                mean_threshold_agreement_q10 = 0.95
                mean_mae_q10 = 0.02
                max_probability_delta_float_vs_q10 = 0.001
                per_head = @(@{ name = 'offline_mock'; threshold_agreement_q10 = 0.90 })
            } | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $outputDirectory 'report.json')
        }
        default { throw 'Unexpected offline Python command.' }
    }
}

try {
    Remove-Item Env:TYPESAFE_API_KEY -ErrorAction SilentlyContinue
    & (Join-Path $PSScriptRoot 'set_typesafe_key_windows.ps1') -KeyFile $testKey
    if ((Get-Content -Raw $testKey).Contains($global:ssosTestSentinel)) { throw 'Credential stored as plaintext.' }
    & (Join-Path $PSScriptRoot 'run_real_jev_windows.ps1') -Count 32 -KeyFile $testKey -Python Invoke-OfflinePython -SkipDependencyInstall *> $null
    if ($env:TYPESAFE_API_KEY) { throw 'Credential leaked into parent environment.' }
    $global:ssosTestFailCollection = $true
    $failed = $false
    try {
        & (Join-Path $PSScriptRoot 'run_real_jev_windows.ps1') -Count 32 -KeyFile $testKey -Python Invoke-OfflinePython -SkipDependencyInstall *> $null
    } catch {
        $failed = $true
    }
    if (-not $failed) { throw 'Collector failure was not propagated.' }
    if ($env:TYPESAFE_API_KEY) { throw 'Credential remained after failure.' }
    if ($global:ssosTestOutputPaths.Count -ne 2 -or $global:ssosTestOutputPaths[0] -eq $global:ssosTestOutputPaths[1]) {
        throw 'Runs did not receive separate artifact paths.'
    }
    foreach ($artifact in $global:ssosTestOutputPaths) {
        if ((Get-Content -Raw $artifact).Trim() -ne 'offline-test-artifact') { throw 'Earlier artifact was lost.' }
    }
    # GitHub's PowerShell wrapper propagates LASTEXITCODE. Clear the expected
    # mocked collector failure only after all failure-path assertions pass.
    $global:LASTEXITCODE = 0
    Write-Host 'PASS: DPAPI roundtrip, collector-only key access, failure cleanup, and previous-run preservation (offline mocks).'
} finally {
    if ($null -ne $savedEnvironmentKey) { $env:TYPESAFE_API_KEY = $savedEnvironmentKey }
    else { Remove-Item Env:TYPESAFE_API_KEY -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $testKey) { Remove-Item -LiteralPath $testKey }
    Remove-Variable ssosTestSentinel,ssosTestFailCollection,ssosTestOutputPaths -Scope Global -ErrorAction SilentlyContinue
}
