[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RunDir = "",
    [int]$TimeoutSeconds = 21600,
    [int]$PollSeconds = 10,
    [string]$HostAddress = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "/workspace/user-home\Desktop\MitraStar\.codex_tmp\openmitrastar_ramssh_client_ed25519",
    [string]$OracleHost = "192.168.1.63",
    [string]$OracleUser = "AELITA",
    [string]$ControllerUrl = "http://192.168.1.43:8008/speed.bin",
    [double]$Min2gMbps = 5.0,
    [switch]$Run2gProbe,
    [switch]$Run5gProbe,
    [ValidateSet("txpath", "v6scheduler")]
    [string]$FiveGProfile = "txpath",
    [ValidateRange(60, 900)]
    [int]$FiveGSeconds = 120,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f66-auto-2g-monitor-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$statusOut = Join-Path $OutputDir "monitor-status.json"
$logPath = Join-Path $OutputDir "monitor.log"

function Write-MonitorStatus([string]$State, [string]$Message, [object]$WatcherStatus = $null, [string]$GateResult = "") {
    [ordered]@{
        schema = "openmitrastar.f66-flash-2g-gate-monitor/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        run_dir = $RunDir
        output_dir = $OutputDir
        run_2g_probe = [bool]$Run2gProbe
        run_5g_probe = [bool]$Run5gProbe
        five_g_profile = $FiveGProfile
        five_g_seconds = $FiveGSeconds
        watcher = $WatcherStatus
        gate_result = $GateResult
    } | ConvertTo-Json -Depth 10 | Set-Content -Encoding ascii -LiteralPath $statusOut
}

function Read-JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

function Get-LatestRunDir {
    $latest = @(Get-ChildItem -LiteralPath (Join-Path $Root "outputs\flash-watch") -Directory -Filter "f66-2g-qguard-*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1)
    if ($latest.Count -gt 0) { return $latest[0].FullName }
    return ""
}

function Test-ProcessAlive([AllowNull()][object]$PidValue) {
    if ($null -eq $PidValue) { return $false }
    try {
        $pidInt = [int]$PidValue
    } catch {
        return $false
    }
    return [bool](Get-Process -Id $pidInt -ErrorAction SilentlyContinue)
}

"F66_2G_MONITOR_START at=$(Get-Date -Format o) output=$OutputDir" |
    Add-Content -Encoding ascii -LiteralPath $logPath
Write-MonitorStatus "watching" "waiting for F66 watcher"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$gateStarted = $false
while ((Get-Date) -lt $deadline) {
    if (-not $RunDir) {
        $RunDir = Get-LatestRunDir
    }
    if (-not $RunDir) {
        "F66_2G_MONITOR_POLL at=$(Get-Date -Format o) no_f66_run_dir=1" |
            Add-Content -Encoding ascii -LiteralPath $logPath
        Write-MonitorStatus "waiting_f66_run" "no F66 flash-watch directory yet"
        Start-Sleep -Seconds $PollSeconds
        continue
    }

    $statusPath = Join-Path $RunDir "status.json"
    $status = Read-JsonFile $statusPath
    if (-not $status) {
        "F66_2G_MONITOR_POLL at=$(Get-Date -Format o) missing_status run_dir=$RunDir" |
            Add-Content -Encoding ascii -LiteralPath $logPath
        Write-MonitorStatus "waiting_f66_status" "F66 status.json not present yet"
        Start-Sleep -Seconds $PollSeconds
        continue
    }

    $state = [string]$status.state
    $alive = $false
    if ($status.PSObject.Properties.Name -contains "watcher_pid") {
        $alive = Test-ProcessAlive $status.watcher_pid
    }
    "F66_2G_MONITOR_POLL at=$(Get-Date -Format o) state=$state alive=$alive run_dir=$RunDir" |
        Add-Content -Encoding ascii -LiteralPath $logPath
    Write-MonitorStatus "watching" "F66 state=$state alive=$alive" $status

    if ($state -eq "pass") {
        if ($gateStarted) {
            Write-MonitorStatus "gate_already_started" "F66 pass already observed" $status
            exit 0
        }
        $gateStarted = $true
        $gateDir = Join-Path $OutputDir "post-flash-2g-gate"
        $stdoutPath = Join-Path $OutputDir "post-flash-2g-gate.stdout.log"
        "F66_2G_MONITOR_FLASH_PASS at=$(Get-Date -Format o) gate_dir=$gateDir" |
            Add-Content -Encoding ascii -LiteralPath $logPath

        $gateArgs = @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $PSScriptRoot "post_flash_f65_radio_gate.ps1"),
            "-HostAddress", $HostAddress,
            "-RouterUser", $RouterUser,
            "-RouterKey", $RouterKey,
            "-OracleHost", $OracleHost,
            "-OracleUser", $OracleUser,
            "-ControllerUrl", $ControllerUrl,
            "-OutputDir", $gateDir,
            "-Min2gMbps", "$Min2gMbps",
            "-FiveGProfile", $FiveGProfile,
            "-FiveGSeconds", "$FiveGSeconds"
        )
        if ($Run2gProbe) { $gateArgs += "-Run2gProbe" }
        if ($Run5gProbe) { $gateArgs += "-Run5gProbe" }
        $proc = Start-Process -FilePath "powershell.exe" `
            -WindowStyle Hidden `
            -ArgumentList $gateArgs `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError (Join-Path $OutputDir "post-flash-2g-gate.stderr.log") `
            -Wait `
            -PassThru
        $rc = [int]$proc.ExitCode
        $resultPath = Join-Path $gateDir "result.json"
        Write-MonitorStatus $(if ($rc -eq 0) { "pass" } else { "gate_failed" }) "post-flash 2G gate rc=$rc" $status $resultPath
        exit $rc
    }

    if ($state -in @("blocked_uart_rx_silent_zero_bytes", "timeout")) {
        Write-MonitorStatus $state "F66 watcher ended before flash pass" $status
        exit 1
    }

    if (-not $alive -and $state -in @("attempt_running", "retry_wait", "starting")) {
        Write-MonitorStatus "stale_f66_watcher" "F66 watcher process is not alive" $status
        exit 1
    }

    Start-Sleep -Seconds $PollSeconds
}

Write-MonitorStatus "timeout" "monitor timeout waiting for F66 flash pass"
exit 1
