param(
    [string]$HostAddress = "192.168.1.90",
    [int]$ClientWaitSeconds = 300,
    [int]$ClientPollInterval = 2,
    [int]$Seconds = 600,
    [int]$Interval = 2,
    [int]$PreSeconds = 10,
    [int]$PostSeconds = 20,
    [string]$RecoveryResultJson,
    [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Waiter = Join-Path $PSScriptRoot "wait_w2_2g_client.py"
$Tx7Gate = Join-Path $PSScriptRoot "run_w2_2g_tx7_gate.ps1"
$RecoveryVerifier = Join-Path $PSScriptRoot "verify_post_tx7_recovery_result.py"
foreach ($Required in @($Waiter, $Tx7Gate, $RecoveryVerifier)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) {
        throw "Missing required file: $Required"
    }
}

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Evidence = [IO.Path]::GetFullPath((Join-Path $Root "outputs\kernel-port\realtek-loop\w2-tx7-auto-gate-$Stamp-RAM-ONLY-NO-FLASH"))
$AllowedRoot = [IO.Path]::GetFullPath((Join-Path $Root "outputs\kernel-port\realtek-loop"))
$AllowedPrefix = $AllowedRoot.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not $Evidence.StartsWith($AllowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Evidence path escapes allowed root: $Evidence"
}

$Plan = [ordered]@{
    schema = "openmitrastar.w2-tx7-auto-client-gate/v1"
    classification = "RAM-ONLY-TX7-NO-FLASH-READ-ONLY-SSH"
    host = $HostAddress
    client_wait_seconds = $ClientWaitSeconds
    client_poll_interval = $ClientPollInterval
    tx7_gate_seconds = $Seconds
    tx7_gate_interval = $Interval
    tx7_gate_pre_seconds = $PreSeconds
    tx7_gate_post_seconds = $PostSeconds
    evidence_dir = $Evidence
    recovery_result_required = $true
    image = [ordered]@{
        name = "linux510-w2-2g-parity-tx7-hybrid32-v1-RAM-TEST-NO-FLASH.bin"
        sha256 = "d547524667d3c1f59b4a4dbf891c1271fe837ee3b5649682a6095492a45781a3"
        bytes = 4330928
    }
    operations = @(
        "verify RecoveryResultJson from current post-TX7 recovery",
        "poll hostapd over existing SSH until a station is associated and AUTHORIZED",
        "only then invoke run_w2_2g_tx7_gate.ps1",
        "write local wait and gate evidence under outputs/kernel-port/realtek-loop"
    )
    mutations = [ordered]@{
        uart_opened = $false
        reboot = $false
        module_reload = $false
        network_reconfigure = $false
        bootenv = $false
        mtd = $false
        flash = $false
    }
}

if ($PlanOnly) {
    $Plan | ConvertTo-Json -Depth 6
    Write-Output "OM2G_TX7_AUTO_GATE_PLAN_PASS=1"
    Write-Output "OM2G_TX7_AUTO_GATE_REQUIRES_RECOVERY_RESULT_JSON=1"
    exit 0
}

if ([string]::IsNullOrWhiteSpace($RecoveryResultJson)) {
    throw "TX7 auto gate execution requires -RecoveryResultJson from a verified OMPOSTTX7_RECOVERY_PASS=1 run"
}
$RecoveryResultJson = [IO.Path]::GetFullPath($RecoveryResultJson)
if (-not (Test-Path -LiteralPath $RecoveryResultJson -PathType Leaf)) {
    throw "RecoveryResultJson not found: $RecoveryResultJson"
}

New-Item -ItemType Directory -Force -Path $Evidence | Out-Null
$Plan | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $Evidence "auto-gate-plan.json") -Encoding UTF8

$RecoveryVerifierOut = Join-Path $Evidence "recovery-result-verifier.stdout.json"
$RecoveryVerifierErr = Join-Path $Evidence "recovery-result-verifier.stderr.txt"
& python $RecoveryVerifier $RecoveryResultJson > $RecoveryVerifierOut 2> $RecoveryVerifierErr
if ($LASTEXITCODE -ne 0) {
    throw "RecoveryResultJson verifier failed; see $RecoveryVerifierErr"
}
$RecoveryVerifierReport = Get-Content -LiteralPath $RecoveryVerifierOut -Raw | ConvertFrom-Json
if (-not ([bool]$RecoveryVerifierReport.ok)) {
    throw "RecoveryResultJson verifier did not return ok=true"
}

$WaitOutput = Join-Path $Evidence "client-wait.json"
Write-Output "OM2G_TX7_AUTO_GATE_WAITING evidence=$Evidence"
& python $Waiter `
    --host $HostAddress `
    --wait-seconds $ClientWaitSeconds `
    --interval $ClientPollInterval `
    --require-authorized `
    --output $WaitOutput
$WaitExit = $LASTEXITCODE
if ($WaitExit -ne 0) {
    Write-Output "OM2G_TX7_AUTO_GATE_NO_CLIENT wait_exit=$WaitExit evidence=$Evidence"
    exit $WaitExit
}

Write-Output "OM2G_TX7_AUTO_GATE_CLIENT_READY evidence=$Evidence"
& $Tx7Gate `
    -HostAddress $HostAddress `
    -Seconds $Seconds `
    -Interval $Interval `
    -PreSeconds $PreSeconds `
    -PostSeconds $PostSeconds `
    -RecoveryResultJson $RecoveryResultJson
$GateExit = $LASTEXITCODE
Write-Output "OM2G_TX7_AUTO_GATE_DONE gate_exit=$GateExit evidence=$Evidence"
exit $GateExit
