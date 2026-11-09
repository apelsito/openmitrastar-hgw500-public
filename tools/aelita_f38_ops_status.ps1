[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RouterHost = "192.168.1.90",
    [string]$AelitaHost = "192.168.1.63",
    [string]$RunDir = "",
    [switch]$SkipNetwork,
    [int]$TcpTimeoutSeconds = 3
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$statusScript = Join-Path $PSScriptRoot "status_f5_safe2g_emacrxrestart_flash_watch.ps1"
$flashBuildDir = Join-Path $Root "work\mission-state\f5-safe2g-emacrxrestart-gzipinit\build"

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutSeconds) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne([TimeSpan]::FromSeconds($TimeoutSeconds))
        if (-not $ok) {
            return $false
        }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Get-FlashEvidence {
    if (-not (Test-Path -LiteralPath $flashBuildDir -PathType Container)) {
        return [ordered]@{
            count = 0
            latest = $null
            latest_result = $null
        }
    }
    $dirs = @(Get-ChildItem -LiteralPath $flashBuildDir -Directory -Filter "flash-one-shot-*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending)
    $latest = if ($dirs.Count -gt 0) { $dirs[0] } else { $null }
    $resultPath = if ($latest) { Join-Path $latest.FullName "result.json" } else { $null }
    [ordered]@{
        count = $dirs.Count
        latest = if ($latest) { $latest.FullName } else { $null }
        latest_result = if ($resultPath -and (Test-Path -LiteralPath $resultPath -PathType Leaf)) { $resultPath } else { $null }
    }
}

function Get-WatcherStatus {
    $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $statusScript)
    if ($RunDir) {
        $args += @("-RunDir", $RunDir)
    }
    $raw = & pwsh.exe @args
    $rc = $LASTEXITCODE
    if ($rc -ne 0) {
        throw "status_f5_safe2g_emacrxrestart_flash_watch.ps1 failed rc=$rc"
    }
    return ($raw | ConvertFrom-Json)
}

$watch = $null
$watchError = $null
try {
    $watch = Get-WatcherStatus
} catch {
    $watchError = $_.Exception.Message
}

$routerPing = $null
$routerTcp22 = $null
$aelitaTcp22 = $null
if (-not $SkipNetwork) {
    $routerPing = [bool](Test-Connection -ComputerName $RouterHost -Count 1 -Quiet -ErrorAction SilentlyContinue)
    $routerTcp22 = [bool](Test-TcpPort $RouterHost 22 $TcpTimeoutSeconds)
    $aelitaTcp22 = [bool](Test-TcpPort $AelitaHost 22 $TcpTimeoutSeconds)
}

$flashEvidence = Get-FlashEvidence
$classification = if ($watch) { [string]$watch.classification } else { "WATCHER_STATUS_UNAVAILABLE" }

$nextAction = switch ($classification) {
    "FLASH_PASS" {
        "inspect latest flash-one-shot result and run post_flash_f5_radio_gate.ps1"
    }
    "FLASH_IN_PROGRESS_OR_FAILED_AFTER_BOOTBASE" {
        "inspect watch.log and latest flash-one-shot backend logs before touching COM3"
    }
    "BOOTBASE_CAPTURED_WAITING_FLASH" {
        "wait for flash backend; do not start another COM3 owner"
    }
    "WAITING_PHYSICAL_POWER_CYCLE_OLD_EMAC_FREEZE" {
        "physical power-cycle AELITA; existing watcher owns COM3 and will catch Bootbase"
    }
    "WATCHER_RUNNING_NO_BOOTBASE_YET" {
        "keep watcher running and inspect watch.log tail"
    }
    default {
        "inspect watcher status before opening COM3"
    }
}

$readyForPostflash = [bool](
    $watch -and
    $watch.markers.flash_pass -and
    $routerPing -eq $true -and
    $routerTcp22 -eq $true
)

[ordered]@{
    schema = "openmitrastar.aelita-f38-ops-status/v1"
    checked_at = (Get-Date).ToString("o")
    router = [ordered]@{
        host = $RouterHost
        ping = $routerPing
        tcp22 = $routerTcp22
    }
    aelita_oracle = [ordered]@{
        host = $AelitaHost
        tcp22 = $aelitaTcp22
    }
    watcher = if ($watch) {
        [ordered]@{
            run_dir = $watch.run_dir
            classification = $classification
            state = if ($watch.status) { $watch.status.state } else { $null }
            attempt = if ($watch.status) { $watch.status.attempt } else { $null }
            processes = $watch.watcher_processes
            markers = $watch.markers
            log = $watch.log
        }
    } else {
        [ordered]@{
            classification = $classification
            error = $watchError
        }
    }
    flash_evidence = $flashEvidence
    ready_for_postflash_gate = $readyForPostflash
    next_action = $nextAction
} | ConvertTo-Json -Depth 10
