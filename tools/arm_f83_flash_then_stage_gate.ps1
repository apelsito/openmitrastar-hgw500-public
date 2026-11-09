[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "/workspace/user-home\Desktop\MitraStar\.codex_tmp\openmitrastar_ramssh_client_ed25519",
    [string]$OracleHost = "192.168.1.63",
    [string]$OracleUser = "AELITA",
    [string]$ControllerUrl = "http://192.168.1.43:8008/speed.bin",
    [double]$Min2gMbps = 5.0,
    [double]$Diag2gMbps = 20.0,
    [ValidateRange(0, 21600)]
    [int]$NoRxAbortSeconds = 300,
    [switch]$AllowInfiniteNoRxWait,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [ValidateRange(60, 21600)]
    [int]$MonitorTimeoutSeconds = 21600,
    [switch]$SysRqRebootFirst,
    [switch]$SshRebootFirst,
    [switch]$ConsoleRebootAssist,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Ack = "OPENMITRASTAR_Q3_F83_5G_POST_HOSTAPD_STAGE_2G_MCS7_MTD4_FLASH_1E3AF819"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
if (-not $OutputDir) {
    $OutputDir = Join-Path $Root "outputs\postflash\f83-auto-arm-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$statusPath = Join-Path $OutputDir "status.json"

function Write-Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f83-auto-arm/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        execute = [bool]$Execute
        port = $Port
        host = $HostAddress
        required_ack = $Ack
    }
    foreach ($key in $Extra.Keys) {
        $payload[$key] = $Extra[$key]
    }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $statusPath
}

function Test-ComPortOpen([string]$Name) {
    $serial = [IO.Ports.SerialPort]::new($Name, 115200, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
    $serial.ReadTimeout = 200
    $serial.WriteTimeout = 200
    try {
        $serial.Open()
        return $true
    } finally {
        if ($serial.IsOpen) { $serial.Close() }
        $serial.Dispose()
    }
}

function Quote-PsLiteral([string]$Text) {
    "'" + ($Text -replace "'", "''") + "'"
}

$ports = @([IO.Ports.SerialPort]::GetPortNames() | Sort-Object)
if ($ports -notcontains $Port) {
    Write-Status "no_com_port" "Requested UART port is not enumerated" @{ ports = $ports }
    throw "$Port is not enumerated"
}

try {
    $portOpen = Test-ComPortOpen $Port
} catch {
    Write-Status "com_port_busy" "Requested UART port cannot be opened" @{
        ports = $ports
        error = $_.Exception.Message
    }
    throw
}
if (-not $portOpen) {
    Write-Status "com_port_busy" "Requested UART port cannot be opened" @{ ports = $ports }
    throw "$Port cannot be opened"
}

$dryOut = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "flash_f83_5g_post_hostapd_stage_2g_mcs7.ps1") `
    -Port $Port `
    -ServerIp $ServerIp `
    -ClientIp $ClientIp `
    -HostAddress $HostAddress `
    -NoRxAbortSeconds $NoRxAbortSeconds `
    -FlashTimeoutSeconds $FlashTimeoutSeconds 2>&1
$dryRc = $LASTEXITCODE
$dryLog = Join-Path $OutputDir "flash-dryrun.log"
$dryOut | Set-Content -Encoding utf8 -LiteralPath $dryLog
if ($dryRc -ne 0 -or (($dryOut -join "`n") -notmatch "OMF83_FLASH_WRAPPER_DRY_RUN_PASS=1")) {
    Write-Status "dry_run_failed" "F83 flash wrapper dry-run failed" @{
        dryrun_log = $dryLog
        exit_code = $dryRc
    }
    throw "F83 dry-run failed; see $dryLog"
}

if (-not $Execute) {
    Write-Status "dry_run_pass" "F83 auto-arm dry-run passed; no router writes" @{
        dryrun_log = $dryLog
    }
    Write-Host "OMF83_AUTO_ARM_DRY_RUN_PASS=1 status=$statusPath"
    exit 0
}

if ($NoRxAbortSeconds -eq 0 -and -not $AllowInfiniteNoRxWait) {
    Write-Status "invalid_no_rx_abort" "Execute refuses infinite UART RX wait unless -AllowInfiniteNoRxWait is explicit" @{
        dryrun_log = $dryLog
    }
    throw "Refusing infinite UART RX wait: pass -AllowInfiniteNoRxWait only for a deliberate long manual bench watch."
}
if ($Execute -and $NoRxAbortSeconds -gt 90 -and -not $AllowInfiniteNoRxWait) {
    Write-Status "invalid_no_rx_abort" "Execute refuses long UART RX silence waits unless -AllowInfiniteNoRxWait is explicit" @{
        dryrun_log = $dryLog
        requested_no_rx_abort_seconds = $NoRxAbortSeconds
        max_default_no_rx_abort_seconds = 90
    }
    throw "Refusing long UART RX silence wait: pass -AllowInfiniteNoRxWait only for a deliberate long manual bench watch."
}

$flashDir = Join-Path $Root "outputs\flash-watch\f83-5g-post-hostapd-stage-2g-mcs7-$stamp"
$flashLaunchLog = Join-Path $OutputDir "flash-launch.log"
$flashLaunchStderrLog = Join-Path $OutputDir "flash-launch.stderr.log"
$flashCommand = @(
    "&",
    (Quote-PsLiteral (Join-Path $PSScriptRoot "flash_f83_5g_post_hostapd_stage_2g_mcs7.ps1")),
    "-Execute",
    "-Ack", (Quote-PsLiteral $Ack),
    "-Port", (Quote-PsLiteral $Port),
    "-ServerIp", (Quote-PsLiteral $ServerIp),
    "-ClientIp", (Quote-PsLiteral $ClientIp),
    "-HostAddress", (Quote-PsLiteral $HostAddress),
    "-NoRxAbortSeconds", [string]$NoRxAbortSeconds,
    "-FlashTimeoutSeconds", [string]$FlashTimeoutSeconds,
    "-OutputDir", (Quote-PsLiteral $flashDir)
) -join " "
if ($AllowInfiniteNoRxWait) {
    $flashCommand += " -AllowInfiniteNoRxWait"
}
if ($SysRqRebootFirst) {
    $flashCommand += " -SysRqRebootFirst"
}
if ($SshRebootFirst) {
    $flashCommand += " -SshRebootFirst"
}
if ($ConsoleRebootAssist) {
    $flashCommand += " -ConsoleRebootAssist"
}
$flashCommand | Set-Content -Encoding ascii -LiteralPath (Join-Path $OutputDir "flash-command.ps1")
$flashEncoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($flashCommand))
$env:OM_F83_FLASH_LAUNCH_LOG = $flashLaunchLog
$env:OM_F83_FLASH_LAUNCH_STDERR_LOG = $flashLaunchStderrLog
$flashProc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden `
    -ArgumentList "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $flashEncoded" `
    -RedirectStandardOutput $flashLaunchLog `
    -RedirectStandardError $flashLaunchStderrLog `
    -PassThru

$flashStatus = Join-Path $flashDir "status.json"
$monitorDir = Join-Path $Root "outputs\postflash\f83-flash-pass-then-stage-gate-$stamp"
New-Item -ItemType Directory -Force -Path $monitorDir | Out-Null
$monitorCommand = @(
    "&",
    (Quote-PsLiteral (Join-Path $PSScriptRoot "monitor_f83_flash_then_stage_gate.ps1")),
    "-FlashStatusPath", (Quote-PsLiteral $flashStatus),
    "-TimeoutSeconds", [string]$MonitorTimeoutSeconds,
    "-HostAddress", (Quote-PsLiteral $HostAddress),
    "-RouterUser", (Quote-PsLiteral $RouterUser),
    "-RouterKey", (Quote-PsLiteral $RouterKey),
    "-OracleHost", (Quote-PsLiteral $OracleHost),
        "-OracleUser", (Quote-PsLiteral $OracleUser),
        "-ControllerUrl", (Quote-PsLiteral $ControllerUrl),
        "-Min2gMbps", [string]$Min2gMbps,
        "-Diag2gMbps", [string]$Diag2gMbps,
        "-OutputDir", (Quote-PsLiteral $monitorDir)
    ) -join " "
$monitorCommand | Set-Content -Encoding ascii -LiteralPath (Join-Path $OutputDir "monitor-command.ps1")
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($monitorCommand))
$monitorProc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden `
    -ArgumentList "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded" `
    -RedirectStandardOutput (Join-Path $monitorDir "stdout.log") `
    -RedirectStandardError (Join-Path $monitorDir "stderr.log") `
    -PassThru

Write-Status "armed" "F83 flash watcher and postflash monitor armed" @{
    dryrun_log = $dryLog
    flash_launch_log = $flashLaunchLog
    flash_launch_stderr_log = $flashLaunchStderrLog
    flash_dir = $flashDir
    flash_status = $flashStatus
    flash_pid = $flashProc.Id
    monitor_dir = $monitorDir
    monitor_pid = $monitorProc.Id
}
Write-Host "OMF83_AUTO_ARMED=1 status=$statusPath flash_status=$flashStatus flash_pid=$($flashProc.Id) monitor_pid=$($monitorProc.Id)"


