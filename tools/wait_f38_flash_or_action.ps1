[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RouterHost = "192.168.1.90",
    [string]$AelitaHost = "192.168.1.63",
    [string]$RunDir = "",
    [int]$TimeoutSeconds = 0,
    [int]$PollSeconds = 10,
    [int]$TcpTimeoutSeconds = 1,
    [string]$OutputPath = "",
    [switch]$SkipNetwork
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$opsScript = Join-Path $PSScriptRoot "aelita_f38_ops_status.ps1"

function Invoke-OpsStatus {
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", $opsScript,
        "-RouterHost", $RouterHost,
        "-AelitaHost", $AelitaHost,
        "-TcpTimeoutSeconds", "$TcpTimeoutSeconds"
    )
    if ($RunDir) { $args += @("-RunDir", $RunDir) }
    if ($SkipNetwork) { $args += "-SkipNetwork" }
    $raw = & pwsh.exe @args
    if ($LASTEXITCODE -ne 0) {
        throw "aelita_f38_ops_status.ps1 failed rc=$LASTEXITCODE"
    }
    return ($raw | ConvertFrom-Json)
}

function Get-ActionState([object]$Status) {
    $markers = $Status.watcher.markers
    $classification = [string]$Status.watcher.classification
    $flashCount = [int]$Status.flash_evidence.count

    if ([bool]$markers.flash_pass -or $classification -eq "FLASH_PASS") {
        return "FLASH_PASS"
    }
    if ($flashCount -gt 0 -or [bool]$markers.flash_marker_seen) {
        return "FLASH_ACTIVITY"
    }
    if ([bool]$markers.topaz_ready -or [bool]$markers.bootbase_seen) {
        return "BOOTBASE_CAPTURED"
    }
    if ($Status.router.tcp22 -eq $true) {
        return "ROUTER_SSH_READY"
    }
    if ($classification -eq "WAITING_PHYSICAL_POWER_CYCLE_OLD_EMAC_FREEZE") {
        return "WAITING_PHYSICAL_POWER_CYCLE"
    }
    if ($classification -eq "WATCHER_NOT_RUNNING") {
        return "WATCHER_NOT_RUNNING"
    }
    return $classification
}

function Test-TerminalForOperator([string]$State) {
    return @(
        "FLASH_PASS",
        "FLASH_ACTIVITY",
        "BOOTBASE_CAPTURED",
        "ROUTER_SSH_READY",
        "WATCHER_NOT_RUNNING"
    ) -contains $State
}

function Write-Snapshot([object]$Status, [string]$State, [bool]$Terminal) {
    $row = [ordered]@{
        schema = "openmitrastar.f38-action-wait/v1"
        checked_at = (Get-Date).ToString("o")
        state = $State
        terminal_for_operator = $Terminal
        router_ping = $Status.router.ping
        router_tcp22 = $Status.router.tcp22
        aelita_tcp22 = $Status.aelita_oracle.tcp22
        watcher_classification = $Status.watcher.classification
        watcher_run_dir = $Status.watcher.run_dir
        bootbase_seen = $Status.watcher.markers.bootbase_seen
        topaz_ready = $Status.watcher.markers.topaz_ready
        flash_marker_seen = $Status.watcher.markers.flash_marker_seen
        flash_pass = $Status.watcher.markers.flash_pass
        flash_evidence_count = $Status.flash_evidence.count
        next_action = $Status.next_action
    }
    $json = $row | ConvertTo-Json -Depth 6 -Compress
    Write-Output $json
    if ($OutputPath) {
        $parent = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($OutputPath))
        if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        $json | Set-Content -Encoding ascii -LiteralPath $OutputPath
    }
}

if ($PollSeconds -lt 1) {
    throw "PollSeconds must be >= 1"
}

$deadline = if ($TimeoutSeconds -gt 0) { (Get-Date).AddSeconds($TimeoutSeconds) } else { $null }
do {
    $status = Invoke-OpsStatus
    $state = Get-ActionState $status
    $terminal = Test-TerminalForOperator $state
    Write-Snapshot $status $state $terminal
    if ($terminal) {
        exit 0
    }
    if ($TimeoutSeconds -le 0) {
        exit 2
    }
    Start-Sleep -Seconds $PollSeconds
} while ((Get-Date) -lt $deadline)

exit 2
