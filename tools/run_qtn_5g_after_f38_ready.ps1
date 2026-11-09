[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RouterHost = "192.168.1.90",
    [string]$AelitaHost = "192.168.1.63",
    [string]$AelitaUser = "AELITA",
    [string]$ControllerIp = "192.168.1.43",
    [string]$RestoreSsid = "MOVISTAR-WIFI6-A348",
    [string]$ExpectedBssid = "",
    [int]$Seconds = 120,
    [double]$Min2gMbps = 5.0,
    [switch]$V6SchedulerDiag,
    [switch]$TxPathTrace,
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Stable2gAck = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$triageScript = Join-Path $PSScriptRoot "triage_f38_postflash.ps1"
$qtnScript = Join-Path $PSScriptRoot "run_qtn_5g_aelita_one_shot.py"
$requiredAck = "OPENMITRASTAR_QTN_5G_AELITA_ONE_SHOT_RAM_ONLY"
$requiredStableAck = "OPENMITRASTAR_2G_STABLE_FOR_QTN5G"

if ($TxPathTrace -and $V6SchedulerDiag) {
    throw "-TxPathTrace and -V6SchedulerDiag are mutually exclusive"
}
if ($Seconds -lt 60 -or $Seconds -gt 900) {
    throw "-Seconds must be 60..900"
}

$triageRaw = & pwsh.exe -NoProfile -ExecutionPolicy Bypass -File $triageScript `
    -RouterHost $RouterHost -AelitaHost $AelitaHost -Min2gMbps $Min2gMbps
if ($LASTEXITCODE -ne 0) {
    throw "triage_f38_postflash.ps1 failed rc=$LASTEXITCODE"
}
$triage = $triageRaw | ConvertFrom-Json
$ready = [string]$triage.terminal_state -eq "READY_2G_PASS"

$modeArg = if ($V6SchedulerDiag) {
    "--v6-scheduler-diag"
} elseif ($TxPathTrace) {
    "--tx-path-trace"
} else {
    "--v6-scheduler-diag"
}

$qtnArgs = @(
    $qtnScript,
    "--ack", $requiredAck,
    "--stable-2g-ack", $requiredStableAck,
    "--router-host", $RouterHost,
    "--oracle-host", $AelitaHost,
    "--oracle-user", $AelitaUser,
    "--controller-ip", $ControllerIp,
    "--restore-ssid", $RestoreSsid,
    "--seconds", "$Seconds",
    $modeArg
)
if ($ExpectedBssid) {
    $qtnArgs += @("--expected-bssid", $ExpectedBssid)
}
if ($Execute) {
    if ($Ack -ne $requiredAck -or $Stable2gAck -ne $requiredStableAck) {
        throw "execute requires -Ack $requiredAck and -Stable2gAck $requiredStableAck"
    }
    $qtnArgs = @($qtnScript, "--execute") + $qtnArgs[1..($qtnArgs.Count - 1)]
}

$exactCommand = "python " + (($qtnArgs | ForEach-Object {
    if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
}) -join " ")

$result = [ordered]@{
    schema = "openmitrastar.f38-ready-qtn5g-gate/v1"
    checked_at = (Get-Date).ToString("o")
    execute = [bool]$Execute
    ready_for_5g = $ready
    triage_terminal_state = $triage.terminal_state
    triage_next_action = $triage.next_action
    two_g_speed_Mbps = $triage.postflash_result.two_g_speed_Mbps
    two_g_meets_min = $triage.postflash_result.two_g_meets_min
    qtn_mode = if ($V6SchedulerDiag -or -not $TxPathTrace) { "v6-scheduler-diag" } else { "tx-path-trace" }
    topology = "wifi0 isolated L3; never add wifi0 to br0 in this gate"
    exact_command = $exactCommand
    safety = [ordered]@{
        opens_uart = $false
        flash = $false
        mtd = $false
        bootenv = $false
        starts_5g_only_after_ready_2g_pass = $ready
    }
}

if (-not $ready) {
    $result.state = "NOT_READY"
    $result | ConvertTo-Json -Depth 8
    exit 2
}

if (-not $Execute) {
    $result.state = "READY_DRY_RUN"
    $result | ConvertTo-Json -Depth 8
    exit 0
}

$result.state = "EXECUTING_QTN_5G_ONE_SHOT"
$result | ConvertTo-Json -Depth 8
& python @qtnArgs
exit $LASTEXITCODE
