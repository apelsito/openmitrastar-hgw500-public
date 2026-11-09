[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Root = "",
    [string]$RouterHost = "192.168.1.90",
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

function Get-F75Processes {
    $seen = @{}
    $items = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and
            ($_.CommandLine -match 'flash_f75_2g_stable_5g_manual' -or
             $_.CommandLine -match 'q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash')
        } |
        ForEach-Object {
            [ordered]@{
                process_id = [int]$_.ProcessId
                parent_process_id = [int]$_.ParentProcessId
                name = [string]$_.Name
                command_line = [string]$_.CommandLine
            }
        })
    foreach ($item in $items) {
        $seen[[int]$item.process_id] = $true
    }
    if ($script:status -and $script:status.PSObject.Properties["current_process_id"]) {
        $pidFromStatus = [int]$script:status.current_process_id
        if (-not $seen.ContainsKey($pidFromStatus)) {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pidFromStatus" -ErrorAction SilentlyContinue
            if ($proc) {
                $items += [ordered]@{
                    process_id = [int]$proc.ProcessId
                    parent_process_id = [int]$proc.ParentProcessId
                    name = [string]$proc.Name
                    command_line = [string]$proc.CommandLine
                }
            }
        }
    }
    $items
}

function Get-Markers([string]$Text, [int]$Lines) {
    if (-not $Text) { return @() }
    $allLines = @($Text -split "`r?`n")
    if ($allLines.Count -eq 0) { return @() }
    $start = [Math]::Max(0, $allLines.Count - $Lines)
    @($allLines[$start..($allLines.Count - 1)] |
        Where-Object {
            $_ -and
            $_ -notmatch '^#< CLIXML' -and
            $_ -notmatch '<Objs Version=' -and
            $_ -notmatch 'System.Management.Automation.(Progress|Information)Record' -and
            $_ -notmatch 'Preparando m.dulos para el primer uso' -and
            $_ -match 'OMF75|OMQ3_F45_|UART_RX|TOPAZ|Bootbase|ZHAL|spi_flash|OMNETWORK|OMSSH|PASS|FAIL|Exception|error'
        } |
        ForEach-Object {
            if ($_.Length -gt 300) { $_.Substring(0, 300) + "...[truncated]" } else { $_ }
        })
}

$flashRoot = Join-Path $Root "outputs\flash-watch"
$latest = $null
if (Test-Path -LiteralPath $flashRoot -PathType Container) {
    $latest = Get-ChildItem -LiteralPath $flashRoot -Directory |
        Where-Object { $_.Name -like "f75-2g-stable-5g-manual-*" } |
        Sort-Object Name -Descending |
        Select-Object -First 1
}

$status = $null
$stdout = ""
$stderr = ""
$stdoutPath = ""
$stderrPath = ""
$uartPath = ""
$uartInfo = $null
if ($latest) {
    $status = Read-JsonFile (Join-Path $latest.FullName "status.json")
    $script:status = $status
    $stdoutPath = Join-Path $latest.FullName "stdout.log"
    $stderrPath = Join-Path $latest.FullName "stderr.log"
    $stdout = Read-TextTailShared $stdoutPath
    $stderr = Read-TextTailShared $stderrPath
    $match = [regex]::Match($stdout, 'log=(?<path>[A-Z]:\\[^\r\n]+?\.log)')
    if ($match.Success) {
        $uartPath = $match.Groups["path"].Value
    }
    if ($uartPath -and (Test-Path -LiteralPath $uartPath -PathType Leaf)) {
        $item = Get-Item -LiteralPath $uartPath
        $uartInfo = [ordered]@{
            path = $item.FullName
            bytes = [int64]$item.Length
            last_write_time = $item.LastWriteTime.ToString("o")
        }
    }
}

$routerTcp22 = $null
$routerPing = $null
if ($IncludeNetwork) {
    $routerPing = Test-PingQuiet $RouterHost
    $routerTcp22 = Test-TcpQuiet $RouterHost 22
}

$processes = @(Get-F75Processes)
$markers = @(Get-Markers $stdout $TailLines) + @(Get-Markers $stderr $TailLines)
$decision = "NO_F75_RUN"
if ($latest) {
    if ($markers -match 'MTD4_FLASH_AND_READBACK_PASS=1') {
        $decision = "F75_FLASH_PASS"
    } elseif ($markers -match 'OMSSH_READY|FLASH_BOOT_SSH_PASS=1') {
        $decision = "F75_BOOT_SSH_SEEN"
    } elseif ($markers -match 'OMQ3_F45_AUTOBREAK_TOPAZ_READY=1') {
        $decision = "TOPAZ_SEEN_FLASH_ACTIVE"
    } elseif ($uartInfo -and [int64]$uartInfo.bytes -eq 0 -and $processes.Count -gt 0) {
        $decision = "ARMED_WAITING_UART_RX_ZERO_BYTES"
    } elseif ($processes.Count -gt 0) {
        $decision = "ARMED_OR_RUNNING"
    } elseif ($markers -match 'UART_RX_SILENT_ZERO_BYTES') {
        $decision = "ENDED_UART_RX_SILENT"
    } else {
        $decision = "F75_NOT_RUNNING_OR_UNCLASSIFIED"
    }
}

[ordered]@{
    schema = "openmitrastar.f75-flash-watch-status-summary/v1"
    checked_at = (Get-Date).ToString("o")
    decision = $decision
    latest_run = if ($latest) { $latest.FullName } else { "" }
    status = $status
    uart = $uartInfo
    router = [ordered]@{
        host = $RouterHost
        ping = $routerPing
        tcp22 = $routerTcp22
    }
    processes = $processes
    recent_markers = $markers
} | ConvertTo-Json -Depth 8
