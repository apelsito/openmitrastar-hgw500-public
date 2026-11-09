param(
    [string]$HostAddress = "192.168.1.90",
    [int]$Seconds = 600,
    [int]$Interval = 2,
    [int]$PreSeconds = 10,
    [int]$PostSeconds = 20,
    [string]$RecoveryResultJson,
    [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"
$CandidateGate = Join-Path $PSScriptRoot "run_w2_2g_candidate_gate.ps1"
$RecoveryVerifier = Join-Path $PSScriptRoot "verify_post_tx7_recovery_result.py"
if (-not (Test-Path -LiteralPath $CandidateGate -PathType Leaf)) {
    throw "Missing candidate gate wrapper: $CandidateGate"
}
if (-not (Test-Path -LiteralPath $RecoveryVerifier -PathType Leaf)) {
    throw "Missing post-TX7 recovery result verifier: $RecoveryVerifier"
}

if ($PlanOnly) {
    & $CandidateGate `
        -ImageName "linux510-w2-2g-parity-tx7-hybrid32-v1-RAM-TEST-NO-FLASH.bin" `
        -ExpectedSha256 "d547524667d3c1f59b4a4dbf891c1271fe837ee3b5649682a6095492a45781a3" `
        -ExpectedBytes 4330928 `
        -Variant "TX7" `
        -HostAddress $HostAddress `
        -Seconds $Seconds `
        -Interval $Interval `
        -PreSeconds $PreSeconds `
        -PostSeconds $PostSeconds `
        -PlanOnly
    Write-Output "OM2G_TX7_REQUIRES_RECOVERY_RESULT_JSON=1"
    exit $LASTEXITCODE
}

if ([string]::IsNullOrWhiteSpace($RecoveryResultJson)) {
    throw "TX7 execution requires -RecoveryResultJson from a verified OMPOSTTX7_RECOVERY_PASS=1 run"
}

$RecoveryResultJson = [IO.Path]::GetFullPath($RecoveryResultJson)
if (-not (Test-Path -LiteralPath $RecoveryResultJson -PathType Leaf)) {
    throw "RecoveryResultJson not found: $RecoveryResultJson"
}

$RecoveryResult = Get-Content -LiteralPath $RecoveryResultJson -Raw | ConvertFrom-Json
if ($RecoveryResult.schema -ne "openmitrastar.post-tx7-recovery-result/v1") {
    throw "RecoveryResultJson has unexpected schema: $($RecoveryResult.schema)"
}
if (-not ([bool]$RecoveryResult.pass) -or -not ([bool]$RecoveryResult.result_verifier_ok)) {
    throw "RecoveryResultJson is not a verified OMPOSTTX7_RECOVERY_PASS=1 result"
}

$VerifierStdout = Join-Path ([IO.Path]::GetDirectoryName($RecoveryResultJson)) "tx7-recovery-result-verifier.stdout.json"
$VerifierStderr = Join-Path ([IO.Path]::GetDirectoryName($RecoveryResultJson)) "tx7-recovery-result-verifier.stderr.txt"
& python $RecoveryVerifier $RecoveryResultJson > $VerifierStdout 2> $VerifierStderr
$VerifierExit = $LASTEXITCODE
if ($VerifierExit -ne 0) {
    throw "RecoveryResultJson verifier failed: $VerifierExit"
}
$VerifierReport = Get-Content -LiteralPath $VerifierStdout -Raw | ConvertFrom-Json
if (-not ([bool]$VerifierReport.ok)) {
    throw "RecoveryResultJson verifier did not return ok=true"
}

& $CandidateGate `
    -ImageName "linux510-w2-2g-parity-tx7-hybrid32-v1-RAM-TEST-NO-FLASH.bin" `
    -ExpectedSha256 "d547524667d3c1f59b4a4dbf891c1271fe837ee3b5649682a6095492a45781a3" `
    -ExpectedBytes 4330928 `
    -Variant "TX7" `
    -HostAddress $HostAddress `
    -Seconds $Seconds `
    -Interval $Interval `
    -PreSeconds $PreSeconds `
    -PostSeconds $PostSeconds
exit $LASTEXITCODE
