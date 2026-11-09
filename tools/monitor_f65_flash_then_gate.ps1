[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RunDir = "",
    [int]$TimeoutSeconds = 21600,
    [int]$PollSeconds = 15,
    [string]$HostAddress = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "/workspace/user-home\Desktop\MitraStar\.codex_tmp\openmitrastar_ramssh_client_ed25519",
    [switch]$Run2gProbe,
    [double]$Min2gMbps = 5.0,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f65-auto-monitor-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$statusOut = Join-Path $OutputDir "monitor-status.json"
$logPath = Join-Path $OutputDir "monitor.log"

function Write-MonitorStatus([string]$State, [string]$Message, [object]$WatcherStatus = $null, [string]$GateResult = "") {
    [ordered]@{
        schema = "openmitrastar.f65-flash-gate-monitor/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        run_dir = $RunDir
        output_dir = $OutputDir
        watcher = $WatcherStatus
        gate_result = $GateResult
    } | ConvertTo-Json -Depth 10 | Set-Content -Encoding ascii -LiteralPath $statusOut
}

function Get-LatestRunDir {
    $latest = Get-ChildItem -LiteralPath (Join-Path $Root "outputs\flash-watch") -Directory -Filter "f65-isolated-5g-*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latest) { return $latest.FullName }
    return ""
}

if (-not $RunDir) {
    $RunDir = Get-LatestRunDir
}
if (-not $RunDir) {
    Write-MonitorStatus "no_watcher" "no f65 watcher run directory found"
    exit 2
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
Write-MonitorStatus "watching" "waiting for F65 flash pass"
"MONITOR_START at=$(Get-Date -Format o) run_dir=$RunDir" | Add-Content -Encoding ascii -LiteralPath $logPath

while ((Get-Date) -lt $deadline) {
    $raw = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "status_f65_isolated_5g_flash_watch.ps1") -RunDir $RunDir -TailLines 20
    $status = $raw | ConvertFrom-Json
    $classification = [string]$status.classification
    "MONITOR_POLL at=$(Get-Date -Format o) classification=$classification state=$($status.status.state)" |
        Add-Content -Encoding ascii -LiteralPath $logPath
    Write-MonitorStatus "watching" "classification=$classification" $status

    if ($classification -eq "FLASH_PASS" -or [bool]$status.markers.flash_pass) {
        $gateDir = Join-Path $OutputDir "post-flash-gate"
        "MONITOR_FLASH_PASS at=$(Get-Date -Format o) gate_dir=$gateDir" | Add-Content -Encoding ascii -LiteralPath $logPath
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "post_flash_f65_radio_gate.ps1") `
            -HostAddress $HostAddress `
            -RouterUser $RouterUser `
            -RouterKey $RouterKey `
            -OutputDir $gateDir `
            -Min2gMbps $Min2gMbps `
            $(if ($Run2gProbe) { "-Run2gProbe" }) *> (Join-Path $OutputDir "post-flash-gate.stdout.log")
        $rc = $LASTEXITCODE
        $resultPath = Join-Path $gateDir "result.json"
        Write-MonitorStatus $(if ($rc -eq 0) { "pass" } else { "gate_failed" }) "post-flash gate rc=$rc" $status $resultPath
        exit $rc
    }

    if ($classification -eq "WATCHER_NOT_RUNNING" -and $status.status.state -eq "timeout") {
        Write-MonitorStatus "watcher_timeout" "watcher ended without F65 flash pass" $status
        exit 1
    }

    Start-Sleep -Seconds $PollSeconds
}

Write-MonitorStatus "timeout" "monitor timeout waiting for F65 flash pass"
exit 1
