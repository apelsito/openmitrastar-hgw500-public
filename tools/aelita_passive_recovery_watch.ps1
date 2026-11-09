[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateRange(5, 600)]
    [int]$PollSeconds = 10,
    [ValidateRange(60, 86400)]
    [int]$MaxRuntimeSeconds = 21600,
    [string]$Port = "COM3",
    [int]$Baud = 115200,
    [string]$RouterHost = "192.168.1.90",
    [string]$AelitaHost = "192.168.1.63",
    [string]$ExpectedPnpDeviceId = "FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000",
    [string]$OutputDir = "",
    [switch]$Once
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $OutputDir = Join-Path $Root "outputs\watchdogs\aelita-passive-recovery-active"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StatusPath = Join-Path $OutputDir "status.json"
$LogPath = Join-Path $OutputDir "watch.log"

function Test-Tcp([string]$HostName, [int]$PortNumber) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $PortNumber, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(700, $false)
        if (-not $ok) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-PingOnce([string]$HostName) {
    try {
        return [bool](Test-Connection -ComputerName $HostName -Count 1 -Quiet -ErrorAction SilentlyContinue)
    } catch {
        return $false
    }
}

function Read-JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try {
        return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-JsonProp($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $Default }
    return $prop.Value
}

function Get-CaptureProcesses() {
    @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match "capture_topaz_uart_resilient\.ps1" -and $_.CommandLine -match [regex]::Escape($ExpectedPnpDeviceId) })
}

function Get-LatestCaptureDir() {
    $dirs = @(Get-ChildItem -Path (Join-Path $Root "outputs\uart-live\passive-recovery-*") -Directory -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending)
    if ($dirs.Count -eq 0) { return $null }
    return $dirs[0].FullName
}

function Start-PassiveCapture() {
    $existing = @(Get-CaptureProcesses)
    if ($existing.Count -gt 0) {
        return [ordered]@{
            started = $false
            reason = "already-running"
            pids = @($existing | ForEach-Object { [int]$_.ProcessId })
        }
    }

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $captureDir = Join-Path $Root "outputs\uart-live\passive-recovery-$stamp"
    New-Item -ItemType Directory -Force -Path $captureDir | Out-Null
    $stdout = Join-Path $captureDir "capture.stdout.log"
    $stderr = Join-Path $captureDir "capture.stderr.log"
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $Root "tools\capture_topaz_uart_resilient.ps1"),
        "-Port", $Port,
        "-Baud", "$Baud",
        "-Seconds", "3600",
        "-OutputDirectory", $captureDir,
        "-RunId", "passive-recovery-$stamp",
        "-ExpectedPnpDeviceId", $ExpectedPnpDeviceId
    )
    $proc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList $args -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    return [ordered]@{
        started = $true
        pid = [int]$proc.Id
        output_dir = $captureDir
        stdout = $stdout
        stderr = $stderr
    }
}

function Get-CaptureSummary() {
    $dir = Get-LatestCaptureDir
    if (-not $dir) {
        $fallbackDirs = @(Get-ChildItem -Path (Join-Path $Root "outputs\uart-live\passive-after-watchstop-*") -Directory -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending)
        if ($fallbackDirs.Count -gt 0) { $dir = $fallbackDirs[0].FullName }
    }
    $statusPath = if ($dir) { Join-Path $dir "capture-status.json" } else { "" }
    $status = Read-JsonFile $statusPath
    $uartLog = if ($dir) { Join-Path $dir "uart.log" } else { "" }
    $uartBytes = 0
    if ($uartLog -and (Test-Path -LiteralPath $uartLog -PathType Leaf)) {
        $uartBytes = [int64](Get-Item -LiteralPath $uartLog).Length
    }
    return [ordered]@{
        dir = $dir
        status_path = $statusPath
        state = Get-JsonProp $status "state" $null
        ready = [bool](Get-JsonProp $status "ready" $false)
        rx_only = [bool](Get-JsonProp $status "rx_only" $false)
        bytes = Get-JsonProp $status "bytes" $uartBytes
        log_bytes = $uartBytes
        error = Get-JsonProp $status "error" $null
    }
}

function Write-Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.passive-recovery-watch/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        log = $LogPath
        pid = $PID
        poll_seconds = $PollSeconds
        max_runtime_seconds = $MaxRuntimeSeconds
        router = [ordered]@{
            host = $RouterHost
            ping = Test-PingOnce $RouterHost
            tcp22 = Test-Tcp $RouterHost 22
            tcp80 = Test-Tcp $RouterHost 80
        }
        aelita = [ordered]@{
            host = $AelitaHost
            tcp22 = Test-Tcp $AelitaHost 22
        }
        passive_capture = Get-CaptureSummary
        writes_uart = $false
        starts_blind_autobreak = $false
        direct_flash = $false
    }
    foreach ($key in $Extra.Keys) { $payload[$key] = $Extra[$key] }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $StatusPath
    "[$((Get-Date).ToString('o'))] $State $Message" | Add-Content -Encoding ascii -LiteralPath $LogPath
}

$deadline = [DateTime]::UtcNow.AddSeconds($MaxRuntimeSeconds)
Write-Status "starting" "passive recovery watch starting"

while ([DateTime]::UtcNow -lt $deadline) {
    $captureStart = Start-PassiveCapture
    $capture = Get-CaptureSummary
    $routerSsh = Test-Tcp $RouterHost 22
    $routerPing = Test-PingOnce $RouterHost
    $state = "waiting"
    $message = "waiting for UART RX bytes or router network recovery"
    if ($routerSsh) {
        $state = "router_ssh_ready"
        $message = "router SSH is reachable; run SSH proof and 2.4 gate"
    } elseif ($routerPing) {
        $state = "router_ping_ready"
        $message = "router ping is reachable; wait for SSH or inspect boot"
    } elseif ([int64]$capture.bytes -gt 0 -or [int64]$capture.log_bytes -gt 0) {
        $state = "uart_rx_seen"
        $message = "UART RX bytes captured; inspect uart.log before any flash"
    }

    Write-Status $state $message @{ capture_start = $captureStart }
    if ($Once -or $state -in @("router_ssh_ready", "uart_rx_seen")) { exit 0 }
    Start-Sleep -Seconds $PollSeconds
}

Write-Status "timeout" "passive recovery watch max runtime elapsed"
exit 1
