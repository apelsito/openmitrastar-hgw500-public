[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Root = "",
    [string]$RouterHost = "192.168.1.90",
    [string]$AelitaHost = "192.168.1.63",
    [int]$TailLines = 80,
    [switch]$IncludeNetwork
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not $Root) {
    $Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
} else {
    $Root = [IO.Path]::GetFullPath($Root)
}

function Read-JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
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
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Get-ProcessMatches {
    @(Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and $_.CommandLine -match 'watch_flash_f74|recover_flash_f74|q3_f45.*COM3'
    } | ForEach-Object {
        [ordered]@{
            process_id = [int]$_.ProcessId
            parent_process_id = [int]$_.ParentProcessId
            name = [string]$_.Name
            command_line = [string]$_.CommandLine
        }
    })
}

function Read-TextTailShared([string]$Path, [int]$MaxBytes = 65536) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return "" }
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        if ($stream.Length -gt $MaxBytes) {
            $stream.Seek(-1 * $MaxBytes, [IO.SeekOrigin]::End) | Out-Null
        }
        $reader = [IO.StreamReader]::new($stream, [Text.UTF8Encoding]::new($false), $true, 4096, $true)
        try {
            return $reader.ReadToEnd()
        } finally {
            $reader.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

function Get-LogMarkers([string]$Path, [int]$Lines) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return @() }
    $text = Read-TextTailShared $Path
    $allLines = @($text -split "`r?`n")
    if ($allLines.Count -eq 0) { return @() }
    $start = [Math]::Max(0, $allLines.Count - $Lines)
    @($allLines[$start..($allLines.Count - 1)] | Where-Object {
        $_ -match 'OMQ3_F45_|WATCH_|ERROR|Exception|UART_RX|TOPAZ|Bootbase|ZHAL|spi_flash|OMSSH|OMNETWORK'
    })
}

$flashRoot = Join-Path $Root "outputs\flash-watch"
$latest = $null
if (Test-Path -LiteralPath $flashRoot -PathType Container) {
    $latest = Get-ChildItem -LiteralPath $flashRoot -Directory |
        Where-Object { $_.Name -like "f74-rf-before-l3-*" } |
        Sort-Object Name -Descending |
        Select-Object -First 1
}

$status = $null
$postgateStatus = $null
$stdoutPath = $null
$stderrPath = $null
$postgateLog = $null
$recoveryStdout = $null
$uartPath = $null
$uartInfo = $null
$markers = @()

if ($latest) {
    $status = Read-JsonFile (Join-Path $latest.FullName "status.json")
    $postgateDir = Join-Path $latest.FullName "attempt-01\postgate"
    $postgateStatus = Read-JsonFile (Join-Path $postgateDir "f74-recovery-postgate-status.json")
    $stdoutPath = Join-Path $latest.FullName "attempt-01\stdout.log"
    $stderrPath = Join-Path $latest.FullName "attempt-01\stderr.log"
    $postgateLog = Join-Path $postgateDir "f74-recovery-postgate.log"
    $recoveryStdout = Join-Path $postgateDir "f74-recovery.stdout.log"
    $markers = @(
        Get-LogMarkers $recoveryStdout $TailLines
        Get-LogMarkers $stdoutPath $TailLines
        Get-LogMarkers $stderrPath $TailLines
    )

    $logText = ""
    if (Test-Path -LiteralPath $recoveryStdout -PathType Leaf) {
        $logText = Read-TextTailShared $recoveryStdout
    }
    $match = [regex]::Match($logText, 'log=(?<path>[A-Z]:\\[^\r\n]+?\.log)')
    if ($match.Success) {
        $uartPath = $match.Groups["path"].Value
    } else {
        $uartCandidate = Get-ChildItem -LiteralPath (Join-Path $Root "outputs\uart-live") -Filter "q3-f45-radio5-powerselect-nonfatal-openlab-autostart-autoboot-atgu-flash-*.log" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($uartCandidate) { $uartPath = $uartCandidate.FullName }
    }
    if ($uartPath -and (Test-Path -LiteralPath $uartPath -PathType Leaf)) {
        $item = Get-Item -LiteralPath $uartPath
        $uartInfo = [ordered]@{
            path = $item.FullName
            bytes = $item.Length
            last_write_time = $item.LastWriteTime.ToString("o")
        }
    }
}

$processes = @(Get-ProcessMatches)
$routerTcp22 = $null
$aelitaTcp22 = $null
if ($IncludeNetwork) {
    $routerTcp22 = Test-TcpQuiet $RouterHost 22
    $aelitaTcp22 = Test-TcpQuiet $AelitaHost 22
}

$decision = "NO_F74_RUN"
if ($latest) {
    $uartBytes = if ($uartInfo) { [int64]$uartInfo.bytes } else { -1 }
    $state = if ($status -and $status.PSObject.Properties["state"]) { [string]$status.state } else { "unknown" }
    $postState = if ($postgateStatus -and $postgateStatus.PSObject.Properties["state"]) { [string]$postgateStatus.state } else { "" }
    if ($postState -eq "pass" -or $state -eq "pass") {
        $decision = "F74_FLASH_AND_POSTGATE_PASS"
    } elseif ($markers -match 'OMQ3_F45_AUTOBREAK_TOPAZ_READY=1') {
        $decision = "TOPAZ_SEEN_FLASH_OR_POSTGATE_ACTIVE"
    } elseif ($uartBytes -eq 0 -and @($processes).Count -gt 0) {
        $decision = "WAITING_UART_RX_ZERO_BYTES"
    } elseif ($uartBytes -gt 0 -and @($processes).Count -gt 0) {
        $decision = "UART_RX_SEEN_WATCHER_ACTIVE"
    } elseif ($state -match 'blocked_uart_rx_silent') {
        $decision = "BLOCKED_UART_RX_SILENT"
    } elseif (@($processes).Count -eq 0) {
        $decision = "F74_WATCHER_NOT_ALIVE"
    } else {
        $decision = "F74_UNCLASSIFIED"
    }
}

[ordered]@{
    schema = "openmitrastar.f74-flash-watch-status-summary/v1"
    checked_at = (Get-Date).ToString("o")
    decision = $decision
    latest_run = if ($latest) { $latest.FullName } else { "" }
    status = $status
    postgate_status = $postgateStatus
    uart = $uartInfo
    router = [ordered]@{
        host = $RouterHost
        tcp22 = $routerTcp22
    }
    aelita = [ordered]@{
        host = $AelitaHost
        tcp22 = $aelitaTcp22
    }
    processes = $processes
    recent_markers = $markers
} | ConvertTo-Json -Depth 8
