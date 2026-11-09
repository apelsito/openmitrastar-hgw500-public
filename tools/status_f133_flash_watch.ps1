param(
    [string]$Root = "",
    [string]$HostAddress = "192.168.1.90",
    [int]$Tail = 80
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not $Root) {
    $Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
} else {
    $Root = [IO.Path]::GetFullPath($Root)
}

function Write-Section([string]$Name) {
    Write-Host ""
    Write-Host "=== $Name ==="
}

function Show-FileTail([string]$Path, [int]$Count) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        Write-Host "path=$Path"
        Get-Content -LiteralPath $Path -Tail $Count
    } else {
        Write-Host "missing=$Path"
    }
}

function Test-TcpQuick([string]$HostName, [int]$PortNumber, [int]$TimeoutMs = 700) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $PortNumber, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

$flashRoot = Join-Path $Root "outputs\flash-watch"
$uartRoot = Join-Path $Root "outputs\uart-live"

Write-Section "F133 Watch Processes"
$procs = @(Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $PID -and
    $_.CommandLine -match 'f133|57FB4F87|q3_f45_radio5_powerselect|arm_f133' -and
    $_.CommandLine -notmatch 'status_f133_flash_watch'
} | Select-Object ProcessId, ParentProcessId, Name, CreationDate, CommandLine)
if ($procs.Count -eq 0) {
    Write-Host "OMF133_STATUS_PROCESS=none"
} else {
    $procs | Format-List
}

Write-Section "Latest F133 Watch Directory"
$latest = $null
if (Test-Path -LiteralPath $flashRoot -PathType Container) {
    $latest = Get-ChildItem -LiteralPath $flashRoot -Directory |
        Where-Object { $_.Name -match '^(f133-(wait-powercycle|detached|5g-disable)|f13x-rx-trigger-f133)' } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}
if (-not $latest) {
    Write-Host "OMF133_STATUS_WATCH_DIR=missing"
} else {
    Write-Host "OMF133_STATUS_WATCH_DIR=$($latest.FullName)"
    Get-ChildItem -LiteralPath $latest.FullName -Force |
        Select-Object Name, Length, LastWriteTime |
        Format-Table -AutoSize

    Write-Section "Latest Status JSON"
    foreach ($name in @("status.json", "wait-status.json")) {
        $path = Join-Path $latest.FullName $name
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            Write-Host "file=$name"
            Get-Content -Raw -LiteralPath $path
        }
    }

    $triggerStatus = Join-Path $latest.FullName "trigger-status.json"
    if (Test-Path -LiteralPath $triggerStatus -PathType Leaf) {
        Write-Host "file=trigger-status.json"
        Get-Content -Raw -LiteralPath $triggerStatus
    }

    Write-Section "Flash Stdout Tail"
    Show-FileTail (Join-Path $latest.FullName "flash.stdout.log") $Tail

    Write-Section "Flash Stderr Tail"
    Show-FileTail (Join-Path $latest.FullName "flash.stderr.log") ([Math]::Min($Tail, 40))

    Write-Section "Trigger UART Tail"
    Show-FileTail (Join-Path $latest.FullName "trigger-uart.log") ([Math]::Min($Tail, 80))
}

Write-Section "Latest UART Log"
$latestUart = $null
if (Test-Path -LiteralPath $uartRoot -PathType Container) {
    $latestUart = Get-ChildItem -LiteralPath $uartRoot -File |
        Where-Object { $_.Name -match 'q3-f45-radio5-powerselect-nonfatal-openlab-autostart-autoboot-atgu-flash' } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}
if (-not $latestUart) {
    Write-Host "OMF133_STATUS_UART_LOG=missing"
} else {
    Write-Host "OMF133_STATUS_UART_LOG=$($latestUart.FullName)"
    Write-Host "OMF133_STATUS_UART_BYTES=$($latestUart.Length)"
    if ($latestUart.Length -gt 0) {
        Get-Content -LiteralPath $latestUart.FullName -Tail $Tail
    }
}

Write-Section "SSH TCP"
$tcp = Test-TcpQuick $HostAddress 22
if ($tcp) {
    Write-Host "OMF133_STATUS_SSH_TCP=pass host=$HostAddress port=22"
} else {
    Write-Host "OMF133_STATUS_SSH_TCP=fail host=$HostAddress port=22"
}
