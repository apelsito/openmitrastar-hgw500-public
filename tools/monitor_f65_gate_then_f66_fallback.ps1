[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$F65MonitorDir = "/workspace/user-home\Desktop\MitraStar\outputs\postflash\f65-mgmt-watch-20260826-0734",
    [int]$TimeoutSeconds = 21600,
    [int]$PollSeconds = 20,
    [double]$Min2gMbps = 5.0,
    [string]$OutputDir = "",
    [switch]$ExecuteFallback,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [switch]$Once
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$RequiredAck = "OPENMITRASTAR_F65_GATE_LOW_2G_START_F66_QGUARD_D9DA4471"
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f65-to-f66-fallback-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$statusPath = Join-Path $OutputDir "fallback-status.json"
$logPath = Join-Path $OutputDir "fallback-monitor.log"

function Test-ProcessAlive([AllowNull()][object]$PidValue) {
    if ($null -eq $PidValue) { return $false }
    try {
        $pidInt = [int]$PidValue
    } catch {
        return $false
    }
    return [bool](Get-Process -Id $pidInt -ErrorAction SilentlyContinue)
}

function Get-F66WatcherAlive {
    $matches = @(Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { [string]$_.CommandLine -like "*watch_flash_f66_2g_qguard_until_bootbase.ps1*" })
    return $matches
}

function Write-FallbackStatus([string]$State, [string]$Message, [object]$MonitorStatus, [object]$Gate, [string]$F66RunDir = "") {
    [ordered]@{
        schema = "openmitrastar.f65-gate-to-f66-fallback/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        f65_monitor_dir = $F65MonitorDir
        output_dir = $OutputDir
        execute_fallback = [bool]$ExecuteFallback
        min_2g_mbps = $Min2gMbps
        f65_monitor = $MonitorStatus
        gate = $Gate
        f66_run_dir = $F66RunDir
    } | ConvertTo-Json -Depth 14 | Set-Content -Encoding ascii -LiteralPath $statusPath
}

function Read-JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return (Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json)
}

function Start-F66Watcher {
    if (-not $ExecuteFallback) {
        return ""
    }
    if ($Ack -ne $RequiredAck) {
        throw "ExecuteFallback requires exact Ack: $RequiredAck"
    }
    $existing = @(Get-F66WatcherAlive)
    if ($existing.Count -gt 0) {
        throw "F66 watcher already running"
    }
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "watch_flash_f66_2g_qguard_until_bootbase.ps1"),
        "-Port", $Port,
        "-ServerIp", $ServerIp,
        "-ClientIp", $ClientIp,
        "-HostAddress", $HostAddress,
        "-PulseResetLinesFirst",
        "-ConsoleRebootAssist",
        "-SysRqRebootFirst"
    )
    $proc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList $args -PassThru
    return "pid=$($proc.Id)"
}

if (-not (Test-Path -LiteralPath $F65MonitorDir -PathType Container)) {
    Write-FallbackStatus "no_f65_monitor" "F65 monitor directory not found" $null $null
    exit 2
}

"FALLBACK_MONITOR_START at=$(Get-Date -Format o) f65_monitor=$F65MonitorDir execute=$([int]$ExecuteFallback.IsPresent)" |
    Add-Content -Encoding ascii -LiteralPath $logPath

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    $monitorStatusPath = Join-Path $F65MonitorDir "monitor-status.json"
    $monitor = Read-JsonFile $monitorStatusPath
    $gate = $null
    $gatePath = ""
    if ($monitor -and $monitor.PSObject.Properties.Name -contains "gate_result") {
        $gatePath = [string]$monitor.gate_result
        if ($gatePath -and -not [IO.Path]::IsPathRooted($gatePath)) {
            $gatePath = Join-Path $Root $gatePath
        }
        if ($gatePath) { $gate = Read-JsonFile $gatePath }
    }

    $f65WatcherAlive = $false
    if ($monitor -and $monitor.PSObject.Properties.Name -contains "watcher" -and $monitor.watcher) {
        $f65WatcherAlive = Test-ProcessAlive $monitor.watcher.watcher.pid
    }
    $terminal = if ($gate -and $gate.PSObject.Properties.Name -contains "terminal_state") { [string]$gate.terminal_state } else { "" }
    $meetsMin = $null
    if ($gate -and $gate.PSObject.Properties.Name -contains "two_g_summary" -and $gate.two_g_summary) {
        if ($gate.two_g_summary.PSObject.Properties.Name -contains "meets_min") {
            $meetsMin = [bool]$gate.two_g_summary.meets_min
        }
    }

    "FALLBACK_MONITOR_POLL at=$(Get-Date -Format o) f65_alive=$f65WatcherAlive terminal=$terminal meets_min=$meetsMin gate=$gatePath" |
        Add-Content -Encoding ascii -LiteralPath $logPath

    if ($terminal -eq "PASS_TOPOLOGY_AND_2G_SPEED" -or $meetsMin -eq $true) {
        Write-FallbackStatus "no_fallback_needed" "F65 2.4 throughput meets threshold" $monitor $gate
        exit 0
    }

    if ($terminal -eq "PASS_TOPOLOGY_2G_THROUGHPUT_LOW" -or ($terminal -eq "PASS_TOPOLOGY_2G_PROBE_FAIL" -and $meetsMin -eq $false)) {
        if ($f65WatcherAlive) {
            Write-FallbackStatus "waiting_f65_watcher_exit" "F65 gate requests fallback but F65 watcher still owns lifecycle" $monitor $gate
        } else {
            $f66 = Start-F66Watcher
            if ($ExecuteFallback) {
                Write-FallbackStatus "f66_started" "F66 watcher started after low 2.4 throughput" $monitor $gate $f66
            } else {
                Write-FallbackStatus "would_start_f66" "F65 gate requests fallback; rerun with ExecuteFallback and exact Ack to start F66 watcher" $monitor $gate
            }
            exit 0
        }
    } else {
        Write-FallbackStatus "watching" "waiting for F65 gate result" $monitor $gate
    }
    if ($Once) { exit 0 }
    Start-Sleep -Seconds ([Math]::Max(1, $PollSeconds))
}

Write-FallbackStatus "timeout" "timeout waiting for F65 gate result" $monitor $gate
exit 1
