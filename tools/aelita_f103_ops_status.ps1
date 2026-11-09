[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Root = "",
    [string]$RouterHost = "192.168.1.90",
    [string]$BootbaseHost = "192.168.1.200",
    [string]$AelitaHost = "192.168.1.63",
    [string]$WatchDir = "outputs\flash-watch\f103-emac-rxrestart-63pokes-watch-active",
    [switch]$SkipNetwork,
    [int]$TcpTimeoutMs = 900,
    [int]$TailLines = 80
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not $Root) {
    $Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
} else {
    $Root = [IO.Path]::GetFullPath($Root)
}
if (-not [IO.Path]::IsPathRooted($WatchDir)) {
    $WatchDir = [IO.Path]::GetFullPath((Join-Path $Root $WatchDir))
}

function Read-JsonFile([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json } catch { return $null }
}

function Test-TcpQuiet([string]$HostAddress, [int]$Port, [int]$TimeoutMsValue) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect($HostAddress, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMsValue, $false)) { return $false }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-PingQuiet([string]$HostAddress, [int]$TimeoutMsValue) {
    $ping = [Net.NetworkInformation.Ping]::new()
    try {
        $reply = $ping.Send($HostAddress, $TimeoutMsValue)
        return ($reply.Status -eq [Net.NetworkInformation.IPStatus]::Success)
    } catch {
        return $false
    } finally {
        $ping.Dispose()
    }
}

function Get-ProcBrief([int]$PidValue) {
    if ($PidValue -le 0) { return $null }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$PidValue" -ErrorAction SilentlyContinue
    if (-not $proc) {
        return [ordered]@{ pid = $PidValue; alive = $false }
    }
    return [ordered]@{
        pid = [int]$proc.ProcessId
        parent_pid = [int]$proc.ParentProcessId
        alive = $true
        name = [string]$proc.Name
        command_line = [string]$proc.CommandLine
    }
}

function Get-TextTail([string]$Path, [int]$Lines) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return "" }
    return ((Get-Content -LiteralPath $Path -Tail $Lines) -join "`n")
}

$statusPath = Join-Path $WatchDir "status.json"
$watchLogPath = Join-Path $WatchDir "watch.log"
$stdoutPath = Join-Path $WatchDir "attempt-01\stdout.log"
$stderrPath = Join-Path $WatchDir "attempt-01\stderr.log"
$status = Read-JsonFile $statusPath

$stdoutTail = Get-TextTail $stdoutPath $TailLines
$stderrTail = Get-TextTail $stderrPath 40
$stdoutFull = ""
if (Test-Path -LiteralPath $stdoutPath -PathType Leaf) {
    $stdoutFull = Get-Content -LiteralPath $stdoutPath -Raw
}
$uartPath = ""
if ($stdoutFull -match 'log=([A-Za-z]:\\[^\r\n]+\.log)') {
    $uartPath = $Matches[1].Trim()
}
$uartInfo = [ordered]@{
    path = $uartPath
    exists = $false
    bytes = $null
    last_write_time = $null
}
if ($uartPath -and (Test-Path -LiteralPath $uartPath -PathType Leaf)) {
    $item = Get-Item -LiteralPath $uartPath
    $uartInfo.exists = $true
    $uartInfo.bytes = [int64]$item.Length
    $uartInfo.last_write_time = $item.LastWriteTime.ToString("o")
}

$watcherPid = 0
if ($status -and $status.PSObject.Properties["watcher_pid"]) { $watcherPid = [int]$status.watcher_pid }
$childProc = Get-CimInstance Win32_Process -Filter "ParentProcessId=$watcherPid" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match "q3_f45_radio5_powerselect" } |
    Select-Object -First 1
$childPid = if ($childProc) { [int]$childProc.ProcessId } else { 0 }
$watcherBrief = Get-ProcBrief $watcherPid
$childBrief = Get-ProcBrief $childPid

$markers = [ordered]@{
    wait_start = ($stdoutFull -match "AUTOBREAK_WAIT_START")
    zhal_seen = ($stdoutFull -match "ZHAL>")
    topaz_ready = ($stdoutFull -match "TOPAZ_READY=1")
    flash_write = ($stdoutFull -match "spi_flash write")
    flash_pass = ($stdoutFull -match "MTD4_FLASH_AND_READBACK_PASS")
    ssh_ready = ($stdoutFull -match "OMSSH_READY")
    uart_silent = ($stdoutFull -match "UART_RX_SILENT_ZERO_BYTES")
    blind_space_count = 0
}
$spaceMatches = [regex]::Matches($stdoutFull, "BLIND_SPACE_SENT=(\d+)")
if ($spaceMatches.Count -gt 0) {
    $markers.blind_space_count = [int]$spaceMatches[$spaceMatches.Count - 1].Groups[1].Value
}

$routerPing = $null
$routerTcp22 = $null
$bootbaseTcp22 = $null
$aelitaTcp22 = $null
if (-not $SkipNetwork) {
    $routerPing = Test-PingQuiet $RouterHost $TcpTimeoutMs
    $routerTcp22 = Test-TcpQuiet $RouterHost 22 $TcpTimeoutMs
    $bootbaseTcp22 = Test-TcpQuiet $BootbaseHost 22 $TcpTimeoutMs
    $aelitaTcp22 = Test-TcpQuiet $AelitaHost 22 $TcpTimeoutMs
}

$state = if ($status -and $status.PSObject.Properties["state"]) { [string]$status.state } else { "missing_status" }
$terminal = "F103_STATUS_UNKNOWN"
if ($markers.flash_pass -or $state -eq "pass") {
    $terminal = "F103_FLASH_READBACK_PASS"
} elseif ($markers.flash_write -or $markers.topaz_ready) {
    $terminal = "F103_BOOTBASE_CAPTURED_FLASH_ACTIVE"
} elseif ($markers.zhal_seen) {
    $terminal = "F103_ZHAL_SEEN_AUTOBREAK_ACTIVE"
} elseif ($markers.uart_silent -or ($uartInfo.exists -and $uartInfo.bytes -eq 0 -and (-not $childBrief -or -not $childBrief.alive))) {
    $terminal = "F103_WATCHER_ENDED_UART_RX_SILENT"
} elseif ($childBrief -and $childBrief.alive -and $uartInfo.exists -and $uartInfo.bytes -eq 0) {
    $terminal = "F103_ARMED_WAITING_UART_RX_ZERO_BYTES"
} elseif ($childBrief -and $childBrief.alive) {
    $terminal = "F103_ARMED_WAITING_BOOTBASE"
} elseif ($state -eq "missing_status") {
    $terminal = "F103_WATCHER_NOT_ARMED"
}

$next = switch ($terminal) {
    "F103_FLASH_READBACK_PASS" { "wait for or run postflash SSH proof and AELITA 2.4 speed gate" }
    "F103_BOOTBASE_CAPTURED_FLASH_ACTIVE" { "do not touch COM3; wait for flash/readback/boot markers" }
    "F103_ZHAL_SEEN_AUTOBREAK_ACTIVE" { "do not touch COM3; watcher is driving ATGU/topaz autobreak" }
    "F103_WATCHER_ENDED_UART_RX_SILENT" { "rearm watcher, then power-cycle HGW with router TX connected to adapter RX" }
    "F103_ARMED_WAITING_UART_RX_ZERO_BYTES" { "keep watcher as sole COM3 owner; physical power-cycle or fix UART RX wiring" }
    "F103_ARMED_WAITING_BOOTBASE" { "wait; power-cycle if Bootbase has not appeared" }
    "F103_WATCHER_NOT_ARMED" { "arm watch_flash_f103_emac_rxrestart_until_bootbase.ps1 before power-cycle" }
    default { "inspect watcher status/logs" }
}

[ordered]@{
    schema = "openmitrastar.aelita-f103-ops-status/v1"
    checked_at = (Get-Date).ToString("o")
    terminal_state = $terminal
    next_action = $next
    router = [ordered]@{
        host = $RouterHost
        ping = $routerPing
        tcp22 = $routerTcp22
    }
    bootbase_host = [ordered]@{
        host = $BootbaseHost
        tcp22 = $bootbaseTcp22
    }
    aelita = [ordered]@{
        host = $AelitaHost
        tcp22 = $aelitaTcp22
    }
    watcher = [ordered]@{
        dir = $WatchDir
        status_path = $statusPath
        state = $state
        pid = $watcherPid
        process = $watcherBrief
        child_pid = $childPid
        child_process = $childBrief
        stdout = $stdoutPath
        stderr = $stderrPath
        watch_log = $watchLogPath
    }
    f103 = [ordered]@{
        candidate_sha256 = if ($status -and $status.PSObject.Properties["candidate_sha256"]) { $status.candidate_sha256 } else { $null }
        current_live_crc32 = if ($status -and $status.PSObject.Properties["current_live_crc32"]) { $status.current_live_crc32 } else { $null }
        expected_full_slot_crc32 = "50cfcf29"
    }
    uart = $uartInfo
    markers = $markers
    stderr_tail = $stderrTail
} | ConvertTo-Json -Depth 8
