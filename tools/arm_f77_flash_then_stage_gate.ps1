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
    [ValidateRange(0, 21600)]
    [int]$NoRxAbortSeconds = 300,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [ValidateRange(60, 21600)]
    [int]$MonitorTimeoutSeconds = 21600,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Ack = "OPENMITRASTAR_Q3_F77_2G_MCS7_NOGUARD_5G_STAGE_GUARD_MTD4_FLASH_05EA7BAE"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
if (-not $OutputDir) {
    $OutputDir = Join-Path $Root "outputs\postflash\f77-auto-arm-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$statusPath = Join-Path $OutputDir "status.json"

function Write-Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f77-auto-arm/v1"
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

$dryOut = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "flash_f77_2g_fast_5g_stage_guard.ps1") `
    -Port $Port `
    -ServerIp $ServerIp `
    -ClientIp $ClientIp `
    -HostAddress $HostAddress `
    -NoRxAbortSeconds $NoRxAbortSeconds `
    -FlashTimeoutSeconds $FlashTimeoutSeconds 2>&1
$dryRc = $LASTEXITCODE
$dryLog = Join-Path $OutputDir "flash-dryrun.log"
$dryOut | Set-Content -Encoding utf8 -LiteralPath $dryLog
if ($dryRc -ne 0 -or (($dryOut -join "`n") -notmatch "OMF77_FLASH_WRAPPER_DRY_RUN_PASS=1")) {
    Write-Status "dry_run_failed" "F77 flash wrapper dry-run failed" @{
        dryrun_log = $dryLog
        exit_code = $dryRc
    }
    throw "F77 dry-run failed; see $dryLog"
}

if (-not $Execute) {
    Write-Status "dry_run_pass" "F77 auto-arm dry-run passed; no router writes" @{
        dryrun_log = $dryLog
    }
    Write-Host "OMF77_AUTO_ARM_DRY_RUN_PASS=1 status=$statusPath"
    exit 0
}

$flashDir = Join-Path $Root "outputs\flash-watch\f77-2g-fast-5g-stage-guard-$stamp"
$flashOut = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "flash_f77_2g_fast_5g_stage_guard.ps1") `
    -Execute `
    -Background `
    -Ack $Ack `
    -Port $Port `
    -ServerIp $ServerIp `
    -ClientIp $ClientIp `
    -HostAddress $HostAddress `
    -NoRxAbortSeconds $NoRxAbortSeconds `
    -FlashTimeoutSeconds $FlashTimeoutSeconds `
    -OutputDir $flashDir 2>&1
$flashRc = $LASTEXITCODE
$flashLaunchLog = Join-Path $OutputDir "flash-launch.log"
$flashOut | Set-Content -Encoding utf8 -LiteralPath $flashLaunchLog
if ($flashRc -ne 0 -or (($flashOut -join "`n") -notmatch "OMF77_FLASH_WRAPPER_BACKGROUND_ARMED=1")) {
    Write-Status "flash_arm_failed" "F77 flash watcher did not arm" @{
        flash_launch_log = $flashLaunchLog
        exit_code = $flashRc
    }
    throw "F77 flash watcher did not arm; see $flashLaunchLog"
}

$flashStatus = Join-Path $flashDir "status.json"
$monitorDir = Join-Path $Root "outputs\postflash\f77-flash-pass-then-stage-gate-$stamp"
New-Item -ItemType Directory -Force -Path $monitorDir | Out-Null
$monitorCommand = @(
    "&",
    (Quote-PsLiteral (Join-Path $PSScriptRoot "monitor_f77_flash_then_stage_gate.ps1")),
    "-FlashStatusPath", (Quote-PsLiteral $flashStatus),
    "-TimeoutSeconds", [string]$MonitorTimeoutSeconds,
    "-HostAddress", (Quote-PsLiteral $HostAddress),
    "-RouterUser", (Quote-PsLiteral $RouterUser),
    "-RouterKey", (Quote-PsLiteral $RouterKey),
    "-OracleHost", (Quote-PsLiteral $OracleHost),
    "-OracleUser", (Quote-PsLiteral $OracleUser),
    "-ControllerUrl", (Quote-PsLiteral $ControllerUrl),
    "-Min2gMbps", [string]$Min2gMbps,
    "-OutputDir", (Quote-PsLiteral $monitorDir)
) -join " "
$monitorCommand | Set-Content -Encoding ascii -LiteralPath (Join-Path $OutputDir "monitor-command.ps1")
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($monitorCommand))
$monitorProc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden `
    -ArgumentList "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded" `
    -RedirectStandardOutput (Join-Path $monitorDir "stdout.log") `
    -RedirectStandardError (Join-Path $monitorDir "stderr.log") `
    -PassThru

Write-Status "armed" "F77 flash watcher and postflash monitor armed" @{
    dryrun_log = $dryLog
    flash_launch_log = $flashLaunchLog
    flash_dir = $flashDir
    flash_status = $flashStatus
    monitor_dir = $monitorDir
    monitor_pid = $monitorProc.Id
}
Write-Host "OMF77_AUTO_ARMED=1 status=$statusPath flash_status=$flashStatus monitor_pid=$($monitorProc.Id)"
