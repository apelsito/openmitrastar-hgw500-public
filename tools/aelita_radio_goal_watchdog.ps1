[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateRange(10, 600)]
    [int]$PollSeconds = 60,
    [ValidateRange(60, 86400)]
    [int]$MaxRuntimeSeconds = 21600,
    [switch]$Once,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $OutputDir = Join-Path $Root "outputs\watchdogs\aelita-radio-goal-watchdog-active"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StatusPath = Join-Path $OutputDir "status.json"
$LogPath = Join-Path $OutputDir "watchdog.log"
$F103NoRxAbortSeconds = 45

function Write-Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.radio-goal-watchdog/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        log = $LogPath
        pid = $PID
        poll_seconds = $PollSeconds
        max_runtime_seconds = $MaxRuntimeSeconds
        touches_com3_directly = $false
        direct_flash = $false
    }
    foreach ($key in $Extra.Keys) { $payload[$key] = $Extra[$key] }
    $payload | ConvertTo-Json -Depth 10 | Set-Content -Encoding ascii -LiteralPath $StatusPath
    "[$((Get-Date).ToString('o'))] $State $Message" | Add-Content -Encoding ascii -LiteralPath $LogPath
}

function Read-Decision() {
    $raw = & (Join-Path $Root "tools\aelita_radio_goal_decision.ps1") 2>$null
    $exitVar = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
    $rc = if ($exitVar) { [int]$exitVar.Value } else { 0 }
    if ($rc -ne 0 -or -not $raw) { return $null }
    try {
        return ($raw -join "`n") | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-MatchingProcess([string]$Pattern) {
    @(Get-CimInstance Win32_Process -Filter "name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match $Pattern })
}

function Start-F103Watcher() {
    $existing = @(Get-MatchingProcess "watch_flash_f103|q3_f45_radio5_powerselect")
    if ($existing.Count -gt 0) {
        return [ordered]@{ started = $false; reason = "already-running"; pids = @($existing | ForEach-Object { [int]$_.ProcessId }) }
    }
    $script = Join-Path $Root "tools\watch_flash_f103_emac_rxrestart_until_bootbase.ps1"
    $out = Join-Path $Root "outputs\flash-watch\f103-emac-rxrestart-63pokes-watch-active"
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", $script,
        "-Attempts", "1",
        "-BootWaitSeconds", "21600",
        "-NoRxAbortSeconds", "$F103NoRxAbortSeconds",
        "-AllowBlindAutobreak",
        "-AllowNoRxRebootAssist",
        "-SysRqRebootFirst",
        "-SysRqRetrySeconds", "5",
        "-ConsoleRebootAssist",
        "-ConsoleRebootRetrySeconds", "5",
        "-PulseResetLinesFirst",
        "-OutputDir", $out
    )
    $proc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList $args -PassThru
    return [ordered]@{ started = $true; pid = [int]$proc.Id; output_dir = $out; no_rx_abort_seconds = $F103NoRxAbortSeconds }
}

function Restart-StuckF103Watcher() {
    $existing = @(Get-MatchingProcess "watch_flash_f103|q3_f45_radio5_powerselect")
    $stopped = @()
    foreach ($proc in @($existing | Sort-Object ParentProcessId -Descending)) {
        try {
            Stop-Process -Id ([int]$proc.ProcessId) -Force -ErrorAction Stop
            $stopped += [int]$proc.ProcessId
        } catch {
            $stopped += "failed:$([int]$proc.ProcessId)"
        }
    }
    Start-Sleep -Milliseconds 500
    $started = Start-F103Watcher
    return [ordered]@{ stopped = $stopped; started = $started }
}

function Start-PostF103Gate() {
    $existing = @(Get-MatchingProcess "watch_post_f103_2g_gate")
    if ($existing.Count -gt 0) {
        return [ordered]@{ started = $false; reason = "already-running"; pids = @($existing | ForEach-Object { [int]$_.ProcessId }) }
    }
    $script = Join-Path $Root "tools\watch_post_f103_2g_gate.ps1"
    $out = Join-Path $Root "outputs\postflash\f103-postflash-autogate-active"
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", $script,
        "-OutputDir", $out,
        "-PollSeconds", "15",
        "-MaxWaitSeconds", "21600"
    )
    $proc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList $args -PassThru
    return [ordered]@{ started = $true; pid = [int]$proc.Id; output_dir = $out }
}

$deadline = [DateTime]::UtcNow.AddSeconds($MaxRuntimeSeconds)
Write-Status "starting" "AELITA radio goal watchdog starting"

while ([DateTime]::UtcNow -lt $deadline) {
    $decision = Read-Decision
    if ($null -eq $decision) {
        Write-Status "decision_unavailable" "radio decision tool did not return JSON"
        if ($Once) { exit 2 }
        Start-Sleep -Seconds $PollSeconds
        continue
    }

    $decisionName = [string]$decision.decision
    $actions = [ordered]@{}
    $postGate = Start-PostF103Gate
    $actions["post_f103_gate"] = $postGate

    if ($decisionName -eq "F103_WATCHER_STUCK_UART_RX_ZERO_REOPEN") {
        $actions["f103_reopen"] = Restart-StuckF103Watcher
        $actions["f103_rearm"] = [ordered]@{ started = $false; reason = "handled-by-reopen"; decision = $decisionName }
    } elseif ($decisionName -eq "F103_WATCHER_EXPIRED_UART_RX_ZERO") {
        $actions["f103_rearm"] = Start-F103Watcher
    } else {
        $actions["f103_rearm"] = [ordered]@{ started = $false; reason = "not-needed"; decision = $decisionName }
    }

    Write-Status "ok" "watchdog iteration completed" @{
        decision = $decisionName
        next_action = [string]$decision.next_action
        actions = $actions
    }

    if ($Once) { exit 0 }
    Start-Sleep -Seconds $PollSeconds
}

Write-Status "timeout" "watchdog max runtime elapsed"
exit 1
