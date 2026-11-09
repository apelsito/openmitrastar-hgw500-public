param(
    [ValidateRange(60, 21600)]
    [int]$TimeoutSeconds = 21600,
    [ValidateRange(5, 300)]
    [int]$PollSeconds = 30,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f70-f73-status-watch-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$watchStatus = Join-Path $OutputDir "watch-status.json"
$watchLog = Join-Path $OutputDir "watch.log"
$latest = Join-Path $Root "outputs\postflash\latest-f70-f73-goal-status.json"

function Write-WatchStatus([string]$State, [string]$Message, [string]$Decision = "", [int]$ExitCode = 0) {
    [ordered]@{
        schema = "openmitrastar.f70-f73-status-watch/v1"
        state = $State
        message = $Message
        decision = $Decision
        exit_code = $ExitCode
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        latest_status = $latest
    } | ConvertTo-Json -Depth 6 | Set-Content -Encoding ascii -LiteralPath $watchStatus
}

"F70_F73_STATUS_WATCH_START at=$(Get-Date -Format o) output=$OutputDir" |
    Add-Content -Encoding ascii -LiteralPath $watchLog
Write-WatchStatus "watching" "starting status loop"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    $json = & (Join-Path $PSScriptRoot "status_f70_f73_goal.ps1")
    $rc = 0
    if (Test-Path variable:global:LASTEXITCODE) {
        $rc = [int]$global:LASTEXITCODE
    }
    if ($rc -ne 0) {
        "F70_F73_STATUS_WATCH_POLL at=$(Get-Date -Format o) rc=$rc decision=status-script-failed" |
            Add-Content -Encoding ascii -LiteralPath $watchLog
        Write-WatchStatus "status_failed" "status script failed" "status-script-failed" $rc
        exit $rc
    }
    $status = $json | ConvertFrom-Json
    $decision = [string]$status.decision
    "F70_F73_STATUS_WATCH_POLL at=$(Get-Date -Format o) decision=$decision router_tcp22=$($status.router.tcp22) f70=$($status.f70_restore.state) chain=$($status.f70_to_f73_chain.state) uart_bytes=$($status.uart.bytes)" |
        Add-Content -Encoding ascii -LiteralPath $watchLog
    Write-WatchStatus "watching" "latest decision: $decision" $decision

    if ($decision -in @("F73_POSTGATE_PASS", "F73_FAILED_INSPECT_OUTPUT", "F70_RESTORE_NOT_PASS_INSPECT")) {
        Write-WatchStatus "terminal" "terminal decision: $decision" $decision
        exit $(if ($decision -eq "F73_POSTGATE_PASS") { 0 } else { 1 })
    }
    Start-Sleep -Seconds $PollSeconds
}

Write-WatchStatus "timeout" "timeout waiting for terminal decision" "timeout" 1
exit 1
