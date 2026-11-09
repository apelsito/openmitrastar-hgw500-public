[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$HostAddress = "192.168.1.90",
    [string]$ChainDir = "",
    [string]$ChainOutputDir = "",
    [string]$F93Dir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

function Get-LatestDir([string]$Pattern, [string]$Base) {
    $item = Get-ChildItem -LiteralPath $Base -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like $Pattern } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($item) { return $item.FullName }
    return $null
}

function Read-JsonOrNull([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json } catch { return $null }
}

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutSeconds = 2) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne([TimeSpan]::FromSeconds($TimeoutSeconds))) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

if (-not $ChainDir -and $ChainOutputDir) {
    $ChainDir = $ChainOutputDir
}
if (-not $ChainDir) {
    $ChainDir = Get-LatestDir "f93-restore-then-f95-*" (Join-Path $Root "outputs\postflash")
}
if (-not $F93Dir) {
    $F93Dir = Get-LatestDir "f93-restore-*" (Join-Path $Root "outputs\flash-watch")
}

$chainStatus = if ($ChainDir) { Read-JsonOrNull (Join-Path $ChainDir "chain-status.json") } else { $null }
$f93Status = if ($F93Dir) { Read-JsonOrNull (Join-Path $F93Dir "status.json") } else { $null }
$uartLog = $null
if ($ChainDir -and $f93Status -and $f93Status.PSObject.Properties["output_dir"]) {
    $stdout = Join-Path ([string]$f93Status.output_dir) "wrapper.stdout.log"
    if (Test-Path -LiteralPath $stdout -PathType Leaf) {
        $line = Get-Content -LiteralPath $stdout -ErrorAction SilentlyContinue |
            Select-String -Pattern "log=.*q3-f45.*\.log" |
            Select-Object -Last 1
        if ($line -and [string]$line.Line -match "log=(.+)$") {
            $uartLog = $Matches[1].Trim()
        }
    }
}
if (-not $uartLog) {
    $latestUart = Get-ChildItem -LiteralPath (Join-Path $Root "outputs\uart-live") -Filter "q3-f45-radio5-powerselect-nonfatal-openlab-autostart-autoboot-atgu-flash-*.log" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latestUart) { $uartLog = $latestUart.FullName }
}

$uartInfo = $null
if ($uartLog -and (Test-Path -LiteralPath $uartLog -PathType Leaf)) {
    $item = Get-Item -LiteralPath $uartLog
    $ageSeconds = [Math]::Round(((Get-Date) - $item.LastWriteTime).TotalSeconds, 1)
    $uartInfo = [ordered]@{
        path = $item.FullName
        bytes = [int64]$item.Length
        updated_at = $item.LastWriteTime.ToString("o")
        age_seconds = $ageSeconds
    }
}

$blindSpaceCount = $null
if ($F93Dir) {
    $stdout = Join-Path $F93Dir "wrapper.stdout.log"
    if (Test-Path -LiteralPath $stdout -PathType Leaf) {
        $lastBlind = Get-Content -LiteralPath $stdout -ErrorAction SilentlyContinue |
            Select-String -Pattern "OMQ3_F45_AUTOBREAK_BLIND_SPACE_SENT=(\d+)" |
            Select-Object -Last 1
        if ($lastBlind -and [string]$lastBlind.Line -match "BLIND_SPACE_SENT=(\d+)") {
            $blindSpaceCount = [int]$Matches[1]
        }
    }
}

$processes = @(Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match "flash_f93_2g_ht40sgi|flash_f95|monitor_f93_restore_then_f95|q3_f45" } |
    ForEach-Object {
        [ordered]@{
            pid = [int]$_.ProcessId
            name = [string]$_.Name
            command = [string]$_.CommandLine
        }
    })

$routerTcp22 = [bool](Test-TcpPort $HostAddress 22 2)
$uartBytes = if ($uartInfo) { [int64]$uartInfo.bytes } else { $null }
$uartAgeSeconds = if ($uartInfo) { [double]$uartInfo.age_seconds } else { $null }
$uartZeroStale = [bool](
    -not $routerTcp22 -and
    $f93Status -and [string]$f93Status.state -eq "running_foreground" -and
    $uartBytes -eq 0 -and
    $uartAgeSeconds -ne $null -and
    $uartAgeSeconds -ge 30
)
$recommendation = "UNKNOWN"
if ($uartZeroStale) {
    $recommendation = "WAITING_FOR_PHYSICAL_POWER_CYCLE_OR_ROUTER_TX_TO_FTDI_RX"
} elseif ($routerTcp22 -and $chainStatus -and [string]$chainStatus.state -eq "watching_f93") {
    $recommendation = "ROUTER_SSH_VISIBLE_CHECK_CHAIN_OR_F93_STATUS"
} elseif ($chainStatus -and [string]$chainStatus.state -eq "pass") {
    $recommendation = "CHAIN_COMPLETE_REVIEW_2G_GATE"
} elseif ($chainStatus -and [string]$chainStatus.state -match "failed|timeout") {
    $recommendation = "CHAIN_FAILED_REVIEW_OUTPUT_DIR"
}

[ordered]@{
    schema = "openmitrastar.f93-f95-chain-status/v1"
    updated_at = (Get-Date).ToString("o")
    host = $HostAddress
    router_tcp22 = $routerTcp22
    chain_dir = $ChainDir
    chain_state = if ($chainStatus) { [string]$chainStatus.state } else { "missing" }
    f93_dir = $F93Dir
    f93_state = if ($f93Status) { [string]$f93Status.state } else { "missing" }
    uart = $uartInfo
    uart_zero_bytes_stale = $uartZeroStale
    blind_space_count = $blindSpaceCount
    recommendation = $recommendation
    next_action = if ($uartZeroStale) {
        "Physical power-cycle with UART connected, or verify router TX is wired to FTDI RX. Do not start a second COM3 owner."
    } elseif ($recommendation -eq "ROUTER_SSH_VISIBLE_CHECK_CHAIN_OR_F93_STATUS") {
        "Inspect F93 watcher status and decide whether to let chain continue or restart cleanly."
    } elseif ($recommendation -eq "CHAIN_COMPLETE_REVIEW_2G_GATE") {
        "Review F95 2.4 GHz gate output."
    } elseif ($recommendation -eq "CHAIN_FAILED_REVIEW_OUTPUT_DIR") {
        "Review chain output directory and flash watcher logs."
    } else {
        "Review chain and F93 status files."
    }
    active_processes = $processes
} | ConvertTo-Json -Depth 8
