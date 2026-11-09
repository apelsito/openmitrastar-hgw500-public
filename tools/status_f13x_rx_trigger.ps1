[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("F133", "F134", "F135")]
    [string]$Profile = "F133",
    [string]$HostAddress = "192.168.1.90",
    [string]$Port = "COM3",
    [int]$Tail = 80
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$profileLower = $Profile.ToLowerInvariant()
$flashRoot = Join-Path $Root "outputs\flash-watch"
$postRoot = Join-Path $Root "outputs\postflash"

function Write-Section([string]$Name) {
    Write-Host ""
    Write-Host "=== $Name ==="
}

function Read-JsonOrNull([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try { return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json } catch { return $null }
}

function Show-Tail([string]$Path, [int]$Count) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        Write-Host "path=$Path"
        Get-Content -LiteralPath $Path -Tail $Count
    } else {
        Write-Host "missing=$Path"
    }
}

function Test-TcpQuick([string]$HostName, [int]$PortNumber, [int]$TimeoutMs = 900) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $PortNumber, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

Write-Section "Serial Ports"
$ports = [IO.Ports.SerialPort]::GetPortNames()
Write-Host "OMF13X_STATUS_PORTS=$($ports -join ',')"
$pnp = Get-PnpDevice -Class Ports -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object { $_.FriendlyName -match "\($([regex]::Escape($Port))\)" } |
    Select-Object -First 1
if ($pnp) {
    Write-Host "OMF13X_STATUS_PORT_PRESENT=1 port=$Port name=$($pnp.FriendlyName)"
} else {
    Write-Host "OMF13X_STATUS_PORT_PRESENT=0 port=$Port"
}

Write-Section "Processes"
$procs = @(Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match "arm_f13x_rx_trigger_flash|monitor_f13x_rx_trigger_then_postgate|$profileLower|$Profile|$Port" -and
    $_.CommandLine -notmatch "status_f13x_rx_trigger"
} | Select-Object ProcessId, ParentProcessId, Name, CreationDate, CommandLine)
if ($procs.Count -eq 0) {
    Write-Host "OMF13X_STATUS_PROCESSES=none"
} else {
    $procs | Format-List
}

Write-Section "Latest Trigger"
$triggerDir = $null
if (Test-Path -LiteralPath $flashRoot -PathType Container) {
    $triggerDir = Get-ChildItem -LiteralPath $flashRoot -Directory |
        Where-Object { $_.Name -match "^f13x-rx-trigger-$profileLower-" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}
if (-not $triggerDir) {
    Write-Host "OMF13X_STATUS_TRIGGER=missing profile=$Profile"
} else {
    $triggerStatusPath = Join-Path $triggerDir.FullName "trigger-status.json"
    $trigger = Read-JsonOrNull $triggerStatusPath
    Write-Host "OMF13X_STATUS_TRIGGER_DIR=$($triggerDir.FullName)"
    if ($trigger) {
        Write-Host "OMF13X_STATUS_TRIGGER_STATE=$($trigger.state) flashes=$($trigger.flashes) uart_tx_before_rx=$($trigger.uart_tx_before_rx)"
        Get-Content -Raw -LiteralPath $triggerStatusPath
    } else {
        Write-Host "OMF13X_STATUS_TRIGGER_STATE=unreadable"
    }
    Write-Section "Trigger UART Tail"
    Show-Tail (Join-Path $triggerDir.FullName "trigger-uart.log") $Tail
    Write-Section "Flash Stdout Tail"
    Show-Tail (Join-Path $triggerDir.FullName "flash.stdout.log") $Tail
    Write-Section "Flash Stderr Tail"
    Show-Tail (Join-Path $triggerDir.FullName "flash.stderr.log") ([Math]::Min($Tail, 40))
}

Write-Section "Latest Monitor"
$monitorDir = $null
if (Test-Path -LiteralPath $postRoot -PathType Container) {
    $monitorDir = Get-ChildItem -LiteralPath $postRoot -Directory |
        Where-Object { $_.Name -match "^f13x-rx-trigger-monitor-$profileLower-" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}
if (-not $monitorDir) {
    Write-Host "OMF13X_STATUS_MONITOR=missing profile=$Profile"
} else {
    $monitorStatusPath = Join-Path $monitorDir.FullName "monitor-status.json"
    $monitor = Read-JsonOrNull $monitorStatusPath
    Write-Host "OMF13X_STATUS_MONITOR_DIR=$($monitorDir.FullName)"
    if ($monitor) {
        Write-Host "OMF13X_STATUS_MONITOR_STATE=$($monitor.state) message=$($monitor.message)"
        Get-Content -Raw -LiteralPath $monitorStatusPath
    } else {
        Write-Host "OMF13X_STATUS_MONITOR_STATE=unreadable"
    }
    Write-Section "Monitor Log Tail"
    Show-Tail (Join-Path $monitorDir.FullName "monitor.log") $Tail
}

Write-Section "SSH TCP"
$ssh = Test-TcpQuick $HostAddress 22
Write-Host "OMF13X_STATUS_SSH_TCP=$([int]$ssh) host=$HostAddress port=22"
