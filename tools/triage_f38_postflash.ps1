[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RunDir = "",
    [string]$PostflashDir = "",
    [string]$RouterHost = "192.168.1.90",
    [string]$AelitaHost = "192.168.1.63",
    [double]$Min2gMbps = 5.0,
    [switch]$SkipNetwork
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$opsScript = Join-Path $PSScriptRoot "aelita_f38_ops_status.ps1"
$postflashRoot = Join-Path $Root "outputs\postflash"

function Read-JsonFile([string]$Path) {
    if ($Path -and (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return (Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json)
    }
    return $null
}

function Find-LatestPostflashDir {
    if ($PostflashDir) {
        if ([IO.Path]::IsPathRooted($PostflashDir)) {
            return [IO.Path]::GetFullPath($PostflashDir)
        }
        return [IO.Path]::GetFullPath((Join-Path $Root $PostflashDir))
    }
    if (-not (Test-Path -LiteralPath $postflashRoot -PathType Container)) {
        return $null
    }
    $latest = Get-ChildItem -LiteralPath $postflashRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "f5-emacrxrestart-auto-*" -or $_.Name -like "f5-radio-gate-*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latest) { return $latest.FullName }
    return $null
}

function Invoke-OpsStatus {
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", $opsScript,
        "-RouterHost", $RouterHost,
        "-AelitaHost", $AelitaHost,
        "-TcpTimeoutSeconds", "1"
    )
    if ($RunDir) { $args += @("-RunDir", $RunDir) }
    if ($SkipNetwork) { $args += "-SkipNetwork" }
    $raw = & pwsh.exe @args
    if ($LASTEXITCODE -ne 0) {
        throw "aelita_f38_ops_status.ps1 failed rc=$LASTEXITCODE"
    }
    return ($raw | ConvertFrom-Json)
}

function Get-TerminalState([object]$Ops, [object]$PostState, [object]$PostResult) {
    $watchClass = [string]$Ops.watcher.classification
    $flashPass = [bool]$Ops.watcher.markers.flash_pass
    $flashCount = [int]$Ops.flash_evidence.count

    if ($flashCount -eq 0 -and -not $flashPass) {
        return "FLASH_NOT_STARTED_WAITING_BOOTBASE"
    }
    if ($PostResult -and $PostResult.terminal_state) {
        switch ([string]$PostResult.terminal_state) {
            "PASS_SSH_AND_2G_PROBE" { return "READY_2G_PASS" }
            "PASS_SSH_READY" { return "READY_SSH_2G_NOT_REQUESTED" }
            "SSH_READY_2G_THROUGHPUT_LOW" { return "READY_2G_LOW_ANALYZE_BE_QUEUE" }
            "SSH_READY_2G_PROBE_FAIL" { return "READY_2G_FAIL_ANALYZE_EVIDENCE" }
            "PING_ONLY_SSH_NOT_READY" { return "MANAGEMENT_PARTIAL_AFTER_FLASH" }
            "NO_MANAGEMENT" { return "MANAGEMENT_DOWN_AFTER_FLASH" }
            "ERROR" { return "POSTFLASH_GATE_ERROR" }
            default { return "POSTFLASH_GATE_" + ([string]$PostResult.terminal_state) }
        }
    }
    if ($PostState -and $PostState.state) {
        switch ([string]$PostState.state) {
            "watching" { return "FLASH_PENDING_POSTFLASH_WATCHING" }
            "flash_pass_seen" { return "FLASH_PASS_POSTFLASH_RUNNING" }
            "postflash_gate_pass" { return "POSTFLASH_GATE_PASS_WITHOUT_RESULT" }
            "postflash_gate_fail" { return "POSTFLASH_GATE_FAIL_NO_RESULT" }
            "watcher_terminal_without_flash" { return "WATCHER_TERMINAL_WITHOUT_FLASH" }
            "timeout" { return "POSTFLASH_WATCH_TIMEOUT" }
        }
    }
    if ($flashPass -or $watchClass -eq "FLASH_PASS") {
        return "FLASH_PASS_POSTFLASH_RESULT_MISSING"
    }
    return "UNKNOWN"
}

function Get-NextAction([string]$TerminalState) {
    switch ($TerminalState) {
        "FLASH_NOT_STARTED_WAITING_BOOTBASE" {
            return "physical power-cycle AELITA; keep existing watcher as sole COM3 owner"
        }
        "FLASH_PENDING_POSTFLASH_WATCHING" {
            return "wait for OMF5_AUTONOMOUS_MTD4_FLASH_AND_READBACK_PASS=1"
        }
        "FLASH_PASS_POSTFLASH_RUNNING" {
            return "wait for post_flash_f5_radio_gate.ps1 to finish"
        }
        "READY_2G_PASS" {
            return "record 2.4 GHz pass, then move to bounded 5 GHz bring-up with wifi0 isolated"
        }
        "READY_SSH_2G_NOT_REQUESTED" {
            return "run post_flash_f5_radio_gate.ps1 with -Run2gProbe"
        }
        "READY_2G_LOW_ANALYZE_BE_QUEUE" {
            return "inspect two_g_low_evidence, OMRTLQGUARD/OMRTLBE/OMRTLRA, then prepare BE queue/reclaim-poll fix"
        }
        "READY_2G_FAIL_ANALYZE_EVIDENCE" {
            return "inspect aelita-2g summary/result and router low-throughput evidence before changing rates"
        }
        "MANAGEMENT_PARTIAL_AFTER_FLASH" {
            return "debug SSH/dropbear/hostkey after ping before radio changes"
        }
        "MANAGEMENT_DOWN_AFTER_FLASH" {
            return "inspect UART boot markers and EMAC logs; do not proceed to radio tuning"
        }
        default {
            return "inspect ops status, postflash state, and postflash result"
        }
    }
}

$ops = Invoke-OpsStatus
$runDirResolved = if ($RunDir) { [IO.Path]::GetFullPath((Join-Path $Root $RunDir)) } elseif ($ops.watcher.run_dir) { [string]$ops.watcher.run_dir } else { $null }
$postStatePath = if ($runDirResolved) { Join-Path $runDirResolved "postflash-gate-state.json" } else { $null }
$postState = Read-JsonFile $postStatePath

$flashStarted = [bool](
    [int]$ops.flash_evidence.count -gt 0 -or
    [bool]$ops.watcher.markers.flash_pass -or
    [string]$ops.watcher.classification -eq "FLASH_PASS"
)
$postDir = if ($PostflashDir -or $flashStarted) { Find-LatestPostflashDir } else { $null }
$postResultPath = if ($postDir) { Join-Path $postDir "result.json" } else { $null }
$postResult = Read-JsonFile $postResultPath

$terminalState = Get-TerminalState $ops $postState $postResult
$twoGSummary = if ($postResult -and $postResult.two_g_summary) { $postResult.two_g_summary } else { $null }
$meetsMin = if ($twoGSummary -and $null -ne $twoGSummary.meets_min) { [bool]$twoGSummary.meets_min } else { $null }
$speedMbps = if ($twoGSummary -and $null -ne $twoGSummary.speed_Mbps) { $twoGSummary.speed_Mbps } else { $null }

[ordered]@{
    schema = "openmitrastar.f38-postflash-triage/v1"
    checked_at = (Get-Date).ToString("o")
    terminal_state = $terminalState
    next_action = Get-NextAction $terminalState
    min_2g_Mbps = $Min2gMbps
    ops = [ordered]@{
        router = $ops.router
        aelita_oracle = $ops.aelita_oracle
        watcher = $ops.watcher
        flash_evidence = $ops.flash_evidence
        ready_for_postflash_gate = $ops.ready_for_postflash_gate
    }
    postflash_watch = [ordered]@{
        state_path = $postStatePath
        state = $postState
    }
    postflash_result = [ordered]@{
        dir = $postDir
        result_path = $postResultPath
        terminal_state = if ($postResult) { $postResult.terminal_state } else { $null }
        two_g_speed_Mbps = $speedMbps
        two_g_meets_min = $meetsMin
        two_g_low_evidence = if ($postResult) { $postResult.two_g_low_evidence } else { $null }
    }
} | ConvertTo-Json -Depth 12
