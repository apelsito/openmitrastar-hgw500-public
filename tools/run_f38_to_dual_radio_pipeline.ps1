[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RouterHost = "192.168.1.90",
    [string]$AelitaHost = "192.168.1.63",
    [string]$AelitaUser = "AELITA",
    [string]$ControllerIp = "192.168.1.43",
    [int]$WaitSeconds = 0,
    [int]$PollSeconds = 10,
    [double]$Min2gMbps = 5.0,
    [switch]$Execute5g,
    [string]$Ack = "",
    [string]$Stable2gAck = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$waitScript = Join-Path $PSScriptRoot "wait_f38_flash_or_action.ps1"
$triageScript = Join-Path $PSScriptRoot "triage_f38_postflash.ps1"
$queueGuardScript = Join-Path $PSScriptRoot "run_2g_queue_guard_after_f38_low.ps1"
$qtnAfterF38Script = Join-Path $PSScriptRoot "run_qtn_5g_after_f38_ready.ps1"
$qtnAck = "OPENMITRASTAR_QTN_5G_AELITA_ONE_SHOT_RAM_ONLY"
$stableAck = "OPENMITRASTAR_2G_STABLE_FOR_QTN5G"

function Invoke-JsonScript {
    param(
        [Parameter(Mandatory=$true)]
        [string[]]$ScriptArgs
    )
    $raw = & pwsh.exe @ScriptArgs
    $rc = $LASTEXITCODE
    $text = ($raw -join "`n").Trim()
    $obj = $null
    if ($text) {
        try {
            $obj = $text | ConvertFrom-Json
        } catch {
            $jsonLine = ($text -split "`r?`n" | Where-Object { $_.Trim().StartsWith("{") } | Select-Object -Last 1)
            if ($jsonLine) {
                $obj = $jsonLine | ConvertFrom-Json
            }
        }
    }
    return [ordered]@{
        rc = $rc
        raw = $text
        json = $obj
    }
}

if ($PollSeconds -lt 1) {
    throw "-PollSeconds must be >= 1"
}

$waitResult = $null
if ($WaitSeconds -gt 0) {
    $waitResult = Invoke-JsonScript -ScriptArgs @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", $waitScript,
        "-RouterHost", $RouterHost,
        "-AelitaHost", $AelitaHost,
        "-TimeoutSeconds", "$WaitSeconds",
        "-PollSeconds", "$PollSeconds",
        "-TcpTimeoutSeconds", "1"
    )
}

$triageResult = Invoke-JsonScript -ScriptArgs @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", $triageScript,
    "-RouterHost", $RouterHost,
    "-AelitaHost", $AelitaHost,
    "-Min2gMbps", "$Min2gMbps"
)
if ($triageResult.rc -ne 0 -or $null -eq $triageResult.json) {
    throw "triage_f38_postflash.ps1 failed rc=$($triageResult.rc)"
}

$triage = $triageResult.json
$terminal = [string]$triage.terminal_state
$pipelineState = switch ($terminal) {
    "FLASH_NOT_STARTED_WAITING_BOOTBASE" { "WAITING_POWER_CYCLE" }
    "FLASH_PENDING_POSTFLASH_WATCHING" { "WAITING_FLASH_PASS" }
    "FLASH_PASS_POSTFLASH_RUNNING" { "WAITING_POSTFLASH_GATE" }
    "READY_2G_PASS" { "READY_FOR_5G" }
    "READY_2G_LOW_ANALYZE_BE_QUEUE" { "READY_FOR_2G_QUEUE_GUARD_ANALYSIS" }
    "READY_2G_FAIL_ANALYZE_EVIDENCE" { "READY_FOR_2G_EVIDENCE_ANALYSIS" }
    "MANAGEMENT_PARTIAL_AFTER_FLASH" { "FIX_MANAGEMENT_BEFORE_RADIO" }
    "MANAGEMENT_DOWN_AFTER_FLASH" { "FIX_EMAC_MANAGEMENT_BEFORE_RADIO" }
    default { "INSPECT_MANUALLY" }
}

$nextCommand = switch ($pipelineState) {
    "WAITING_POWER_CYCLE" {
        "physically power-cycle AELITA; keep current watcher running"
    }
    "READY_FOR_2G_QUEUE_GUARD_ANALYSIS" {
        "pwsh -NoProfile -ExecutionPolicy Bypass -File $queueGuardScript -Action apply"
    }
    "READY_FOR_5G" {
        "pwsh -NoProfile -ExecutionPolicy Bypass -File $qtnAfterF38Script -V6SchedulerDiag"
    }
    default {
        [string]$triage.next_action
    }
}

$qtnResult = $null
if ($pipelineState -eq "READY_FOR_5G") {
    $qtnArgs = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", $qtnAfterF38Script,
        "-RouterHost", $RouterHost,
        "-AelitaHost", $AelitaHost,
        "-AelitaUser", $AelitaUser,
        "-ControllerIp", $ControllerIp,
        "-Min2gMbps", "$Min2gMbps",
        "-V6SchedulerDiag"
    )
    if ($Execute5g) {
        if ($Ack -ne $qtnAck -or $Stable2gAck -ne $stableAck) {
            throw "Execute5g requires -Ack $qtnAck and -Stable2gAck $stableAck"
        }
        $qtnArgs += @("-Execute", "-Ack", $qtnAck, "-Stable2gAck", $stableAck)
    }
    $qtnResult = Invoke-JsonScript -ScriptArgs $qtnArgs
}

[ordered]@{
    schema = "openmitrastar.f38-dual-radio-pipeline/v1"
    checked_at = (Get-Date).ToString("o")
    execute_5g = [bool]$Execute5g
    wait = if ($waitResult) {
        [ordered]@{
            rc = $waitResult.rc
            state = if ($waitResult.json) { $waitResult.json.state } else { $null }
            terminal_for_operator = if ($waitResult.json) { $waitResult.json.terminal_for_operator } else { $null }
        }
    } else { $null }
    terminal_state = $terminal
    pipeline_state = $pipelineState
    next_command = $nextCommand
    router = $triage.ops.router
    aelita_oracle = $triage.ops.aelita_oracle
    watcher = [ordered]@{
        run_dir = $triage.ops.watcher.run_dir
        classification = $triage.ops.watcher.classification
        bootbase_seen = $triage.ops.watcher.markers.bootbase_seen
        flash_marker_seen = $triage.ops.watcher.markers.flash_marker_seen
        flash_pass = $triage.ops.watcher.markers.flash_pass
        flash_evidence_count = $triage.ops.flash_evidence.count
    }
    postflash_result = $triage.postflash_result
    qtn5g = if ($qtnResult) {
        [ordered]@{
            rc = $qtnResult.rc
            state = if ($qtnResult.json) { $qtnResult.json.state } else { $null }
            ready_for_5g = if ($qtnResult.json) { $qtnResult.json.ready_for_5g } else { $null }
            qtn_mode = if ($qtnResult.json) { $qtnResult.json.qtn_mode } else { $null }
        }
    } else { $null }
    safety = [ordered]@{
        opens_uart = $false
        flash = $false
        mtd = $false
        bootenv = $false
        five_ghz_requires_ready_2g_pass = $true
    }
} | ConvertTo-Json -Depth 10
