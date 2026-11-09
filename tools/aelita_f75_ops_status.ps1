[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Root = "",
    [string]$RouterHost = "192.168.1.90",
    [string]$AelitaHost = "192.168.1.63",
    [string]$MonitorDir = "",
    [switch]$SkipNetwork
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not $Root) {
    $Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
} else {
    $Root = [IO.Path]::GetFullPath($Root)
}

function Read-JsonFile([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    } catch {
        return [ordered]@{
            unreadable = $true
            error = $_.Exception.Message
            path = $Path
        }
    }
}

function Test-TcpQuiet([string]$HostAddress, [int]$Port, [int]$TimeoutMs = 1200) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect($HostAddress, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) { return $false }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-PingQuiet([string]$HostAddress, [int]$TimeoutMs = 1200) {
    $ping = [Net.NetworkInformation.Ping]::new()
    try {
        $reply = $ping.Send($HostAddress, $TimeoutMs)
        return ($reply.Status -eq [Net.NetworkInformation.IPStatus]::Success)
    } catch {
        return $false
    } finally {
        $ping.Dispose()
    }
}

function Invoke-F75FlashStatus {
    $raw = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "status_f75_flash_watch.ps1") -Root $Root -RouterHost $RouterHost -IncludeNetwork
    if ($LASTEXITCODE -ne 0) { throw "status_f75_flash_watch.ps1 failed rc=$LASTEXITCODE" }
    return ($raw | ConvertFrom-Json)
}

function Find-LatestMonitorDir {
    if ($MonitorDir) {
        if ([IO.Path]::IsPathRooted($MonitorDir)) { return [IO.Path]::GetFullPath($MonitorDir) }
        return [IO.Path]::GetFullPath((Join-Path $Root $MonitorDir))
    }
    $rootDir = Join-Path $Root "outputs\postflash"
    if (-not (Test-Path -LiteralPath $rootDir -PathType Container)) { return "" }
    $latest = Get-ChildItem -LiteralPath $rootDir -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "router-ssh-radio-monitor-f75-*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latest) { return $latest.FullName }
    return ""
}

function Find-LatestDryRunMonitorDir {
    $rootDir = Join-Path $Root "outputs\postflash"
    if (-not (Test-Path -LiteralPath $rootDir -PathType Container)) { return "" }
    $latest = Get-ChildItem -LiteralPath $rootDir -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "f75-2g-pass-then-5g-dryrun-*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latest) { return $latest.FullName }
    return ""
}

function Find-LatestRfSmokeMonitorDir {
    $rootDir = Join-Path $Root "outputs\postflash"
    if (-not (Test-Path -LiteralPath $rootDir -PathType Container)) { return "" }
    $latest = Get-ChildItem -LiteralPath $rootDir -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "f75-5g-dryrun-pass-then-rf-smoke-*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latest) { return $latest.FullName }
    return ""
}

function Find-LatestAelita5gMonitorDir {
    $rootDir = Join-Path $Root "outputs\postflash"
    if (-not (Test-Path -LiteralPath $rootDir -PathType Container)) { return "" }
    $latest = Get-ChildItem -LiteralPath $rootDir -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "f75-rf-smoke-pass-then-aelita-5g-*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latest) { return $latest.FullName }
    return ""
}

function Get-ProcessBrief([int[]]$ProcessIds) {
    @($ProcessIds | Where-Object { $_ -gt 0 } | ForEach-Object {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$_" -ErrorAction SilentlyContinue
        if ($proc) {
            [ordered]@{
                process_id = [int]$proc.ProcessId
                name = [string]$proc.Name
                alive = $true
            }
        } else {
            [ordered]@{
                process_id = [int]$_
                alive = $false
            }
        }
    })
}

$flash = Invoke-F75FlashStatus
$monitorPath = Find-LatestMonitorDir
$monitorStatus = Read-JsonFile (Join-Path $monitorPath "monitor-status.json")
$dryRunMonitorPath = Find-LatestDryRunMonitorDir
$dryRunMonitorStatus = Read-JsonFile (Join-Path $dryRunMonitorPath "status.json")
$rfSmokeMonitorPath = Find-LatestRfSmokeMonitorDir
$rfSmokeMonitorStatus = Read-JsonFile (Join-Path $rfSmokeMonitorPath "status.json")
$aelita5gMonitorPath = Find-LatestAelita5gMonitorDir
$aelita5gMonitorStatus = Read-JsonFile (Join-Path $aelita5gMonitorPath "status.json")
$monitorPid = 0
if ($monitorPath) {
    $monProc = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match [regex]::Escape($monitorPath) } |
        Select-Object -First 1
    if ($monProc) { $monitorPid = [int]$monProc.ProcessId }
}
$dryRunMonitorPid = 0
if ($dryRunMonitorPath) {
    $dryProc = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match [regex]::Escape($dryRunMonitorPath) } |
        Select-Object -First 1
    if ($dryProc) { $dryRunMonitorPid = [int]$dryProc.ProcessId }
}
$rfSmokeMonitorPid = 0
if ($rfSmokeMonitorPath) {
    $rfProc = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match [regex]::Escape($rfSmokeMonitorPath) } |
        Select-Object -First 1
    if ($rfProc) { $rfSmokeMonitorPid = [int]$rfProc.ProcessId }
}
$aelita5gMonitorPid = 0
if ($aelita5gMonitorPath) {
    $aelita5gProc = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match [regex]::Escape($aelita5gMonitorPath) } |
        Select-Object -First 1
    if ($aelita5gProc) { $aelita5gMonitorPid = [int]$aelita5gProc.ProcessId }
}

$routerPing = $flash.router.ping
$routerTcp22 = $flash.router.tcp22
$aelitaTcp22 = $null
if (-not $SkipNetwork) {
    if ($null -eq $routerPing) { $routerPing = Test-PingQuiet $RouterHost }
    if ($null -eq $routerTcp22) { $routerTcp22 = Test-TcpQuiet $RouterHost 22 }
    $aelitaTcp22 = Test-TcpQuiet $AelitaHost 22
}

$flashDecision = [string]$flash.decision
$monitorState = if ($monitorStatus -and $monitorStatus.PSObject.Properties["state"]) { [string]$monitorStatus.state } else { "missing" }
$dryRunMonitorState = if ($dryRunMonitorStatus -and $dryRunMonitorStatus.PSObject.Properties["state"]) { [string]$dryRunMonitorStatus.state } else { "missing" }
$rfSmokeMonitorState = if ($rfSmokeMonitorStatus -and $rfSmokeMonitorStatus.PSObject.Properties["state"]) { [string]$rfSmokeMonitorStatus.state } else { "missing" }
$aelita5gMonitorState = if ($aelita5gMonitorStatus -and $aelita5gMonitorStatus.PSObject.Properties["state"]) { [string]$aelita5gMonitorStatus.state } else { "missing" }
$terminal = "UNKNOWN"
if ($aelita5gMonitorState -eq "pass") {
    $terminal = "F75_2G_AND_5G_AELITA_GATE_PASS"
} elseif ($rfSmokeMonitorState -eq "pass") {
    $terminal = "F75_2G_PASS_5G_DRYRUN_PASS_RF_SMOKE_PASS"
} elseif ($dryRunMonitorState -eq "pass") {
    $terminal = "F75_2G_PASS_5G_DRYRUN_PASS"
} elseif ($flashDecision -eq "F75_FLASH_PASS" -or $monitorState -eq "pass") {
    $terminal = "F75_FLASHED_POSTGATE_PASS_OR_DONE"
} elseif ($flashDecision -eq "F75_BOOT_SSH_SEEN" -or $monitorState -eq "router_ssh_seen") {
    $terminal = "F75_BOOTED_GATE_RUNNING"
} elseif ($flashDecision -eq "TOPAZ_SEEN_FLASH_ACTIVE") {
    $terminal = "BOOTBASE_CAPTURED_FLASH_ACTIVE"
} elseif ($flashDecision -eq "ARMED_WAITING_UART_RX_ZERO_BYTES") {
    $terminal = "WAITING_PHYSICAL_POWER_CYCLE_OR_UART_RX"
} elseif ($flashDecision -eq "ENDED_UART_RX_SILENT") {
    $terminal = "WATCHER_ENDED_UART_RX_SILENT"
}

$next = switch ($terminal) {
    "F75_2G_AND_5G_AELITA_GATE_PASS" { "inspect final 2.4/5G evidence; begin OEM parity/rate tuning" }
    "F75_2G_PASS_5G_DRYRUN_PASS_RF_SMOKE_PASS" { "run AELITA 5G client/auth/data gate or continue 2.4 speed tuning" }
    "F75_2G_PASS_5G_DRYRUN_PASS" { "run bounded manual 5G RF smoke or continue 2.4 speed tuning" }
    "F75_FLASHED_POSTGATE_PASS_OR_DONE" { "inspect radio-gate result; continue 2.4 speed tuning or bounded manual 5G" }
    "F75_BOOTED_GATE_RUNNING" { "wait for post_flash_f65_radio_gate.ps1 result" }
    "BOOTBASE_CAPTURED_FLASH_ACTIVE" { "do not touch COM3; wait for flash/readback/boot markers" }
    "WAITING_PHYSICAL_POWER_CYCLE_OR_UART_RX" { "power-cycle HGW while F75 watcher owns COM3" }
    "WATCHER_ENDED_UART_RX_SILENT" { "rearm F75 watcher, then power-cycle HGW" }
    default { "inspect F75 flash status and monitor logs" }
}

$flashPid = 0
if ($flash.status -and $flash.status.PSObject.Properties["current_process_id"]) {
    $flashPid = [int]$flash.status.current_process_id
}

[ordered]@{
    schema = "openmitrastar.aelita-f75-ops-status/v1"
    checked_at = (Get-Date).ToString("o")
    terminal_state = $terminal
    next_action = $next
    router = [ordered]@{
        host = $RouterHost
        ping = $routerPing
        tcp22 = $routerTcp22
    }
    aelita = [ordered]@{
        host = $AelitaHost
        tcp22 = $aelitaTcp22
    }
    flash = [ordered]@{
        decision = $flashDecision
        run = $flash.latest_run
        pid = $flashPid
        uart_bytes = if ($flash.uart) { $flash.uart.bytes } else { $null }
        candidate_sha256 = if ($flash.status -and $flash.status.inputs) { $flash.status.inputs.candidate_sha256 } else { $null }
        full_slot_crc32 = if ($flash.status -and $flash.status.inputs) { $flash.status.inputs.full_slot_crc32 } else { $null }
        current_live_crc32 = if ($flash.status) { $flash.status.current_live_crc32 } else { $null }
    }
    postflash_monitor = [ordered]@{
        dir = $monitorPath
        state = $monitorState
        pid = $monitorPid
        gate_result = if ($monitorStatus) { $monitorStatus.gate_result } else { "" }
    }
    five_g_dryrun_monitor = [ordered]@{
        dir = $dryRunMonitorPath
        state = $dryRunMonitorState
        pid = $dryRunMonitorPid
        result = if ($dryRunMonitorStatus -and $dryRunMonitorStatus.PSObject.Properties["result"]) { $dryRunMonitorStatus.result } else { "" }
        five_g_terminal_state = if ($dryRunMonitorStatus -and $dryRunMonitorStatus.PSObject.Properties["five_g_terminal_state"]) { $dryRunMonitorStatus.five_g_terminal_state } else { "" }
    }
    five_g_rf_smoke_monitor = [ordered]@{
        dir = $rfSmokeMonitorPath
        state = $rfSmokeMonitorState
        pid = $rfSmokeMonitorPid
        result = if ($rfSmokeMonitorStatus -and $rfSmokeMonitorStatus.PSObject.Properties["result"]) { $rfSmokeMonitorStatus.result } else { "" }
        five_g_terminal_state = if ($rfSmokeMonitorStatus -and $rfSmokeMonitorStatus.PSObject.Properties["five_g_terminal_state"]) { $rfSmokeMonitorStatus.five_g_terminal_state } else { "" }
    }
    aelita_5g_installed_monitor = [ordered]@{
        dir = $aelita5gMonitorPath
        state = $aelita5gMonitorState
        pid = $aelita5gMonitorPid
        result = if ($aelita5gMonitorStatus -and $aelita5gMonitorStatus.PSObject.Properties["result"]) { $aelita5gMonitorStatus.result } else { "" }
        five_g_terminal_state = if ($aelita5gMonitorStatus -and $aelita5gMonitorStatus.PSObject.Properties["five_g_terminal_state"]) { $aelita5gMonitorStatus.five_g_terminal_state } else { "" }
    }
    processes = Get-ProcessBrief @($flashPid, $monitorPid, $dryRunMonitorPid, $rfSmokeMonitorPid, $aelita5gMonitorPid)
} | ConvertTo-Json -Depth 8
