[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "ee219d02",
    [ValidateRange(60, 21600)]
    [int]$BootWaitSeconds = 21600,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [ValidateRange(0, 21600)]
    [int]$NoRxAbortSeconds = 90,
    [switch]$AllowInfiniteNoRxWait,
    [switch]$PulseResetLinesFirst,
    [switch]$SysRqRebootFirst,
    [switch]$SshRebootFirst,
    [switch]$ConsoleRebootAssist,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$BuildDir = Join-Path $Root "work\mission-state\q3-persistent-composite-f89-2g-rate-trace-after-f88\build"
$BuildResultPath = Join-Path $BuildDir "build-result.json"
$RequiredAck = "OPENMITRASTAR_Q3_F89_2G_RATE_TRACE_AFTER_F88_MTD4_FLASH_3F582995"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
if (-not $OutputDir) {
    $OutputDir = Join-Path $Root "outputs\flash-watch\f89-2g-rate-trace-after-f88-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StatusPath = Join-Path $OutputDir "status.json"

function Write-F89Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f89-flash-wrapper/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        build_dir = $BuildDir
        execute = [bool]$Execute
        current_process_id = [int]$PID
        port = $Port
        server_ip = $ServerIp
        client_ip = $ClientIp
        host = $HostAddress
        current_live_crc32 = $CurrentLiveCrc32.ToLowerInvariant()
        boot_wait_seconds = $BootWaitSeconds
        no_rx_abort_seconds = $NoRxAbortSeconds
        flash_timeout_seconds = $FlashTimeoutSeconds
        required_ack = $RequiredAck
    }
    foreach ($key in $Extra.Keys) { $payload[$key] = $Extra[$key] }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $StatusPath
}

function Get-Sha256Hex([string]$Path) {
    if (Get-Command Get-FileHash -ErrorAction SilentlyContinue) {
        return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    }
    $stream = [IO.File]::OpenRead($Path)
    try {
        $sha = [Security.Cryptography.SHA256]::Create()
        try {
            return ([BitConverter]::ToString($sha.ComputeHash($stream)) -replace "-", "").ToLowerInvariant()
        } finally {
            $sha.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

function Set-F89FlashEnvironment([object]$BuildResult) {
    $candidate = [IO.Path]::GetFullPath([string]$BuildResult.candidate)
    $prefix = [IO.Path]::GetFileNameWithoutExtension($candidate)
    if ($prefix.EndsWith(".webformat")) {
        $prefix = $prefix.Substring(0, $prefix.Length - ".webformat".Length)
    }
    $decompressed = Join-Path $BuildDir ($prefix + ".decompressed.bin")
    $kconfig = Join-Path $BuildDir ($prefix + ".config")
    $bootbase = Join-Path $BuildDir "bootbase-contract.json"
    $manifest = Join-Path $BuildDir "manifest.json"
    foreach ($path in @($candidate, $decompressed, $kconfig, $bootbase, $manifest)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "missing F89 flash input: $path"
        }
    }
    if ((Get-Sha256Hex $candidate) -ne [string]$BuildResult.candidate_sha256) {
        throw "F89 candidate hash mismatch"
    }
    if ((Get-Item -LiteralPath $candidate).Length -ne [long]$BuildResult.candidate_bytes) {
        throw "F89 candidate size mismatch"
    }
    $env:OM_Q3_FLASH_ACK = $RequiredAck
    $env:OM_Q3_FLASH_BUILD_DIR = $BuildDir
    $env:OM_Q3_FLASH_CANDIDATE = $candidate
    $env:OM_Q3_FLASH_BOOTBASE_CONTRACT = $bootbase
    $env:OM_Q3_FLASH_MANIFEST = $manifest
    $env:OM_Q3_FLASH_INITRAMFS = $decompressed
    $env:OM_Q3_FLASH_KCONFIG = $kconfig
    $env:OM_Q3_FLASH_EXPECTED_SHA256 = [string]$BuildResult.candidate_sha256
    $env:OM_Q3_FLASH_EXPECTED_BYTES = [string]$BuildResult.candidate_bytes
    $env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $CurrentLiveCrc32.ToLowerInvariant()
    return [ordered]@{
        candidate = $candidate
        candidate_sha256 = [string]$BuildResult.candidate_sha256
        candidate_bytes = [long]$BuildResult.candidate_bytes
        candidate_crc32 = [string]$BuildResult.candidate_crc32
        full_slot_crc32 = [string]$BuildResult.full_slot_crc32
        full_slot_sha256 = [string]$BuildResult.full_slot_sha256
        decompressed = $decompressed
        kconfig = $kconfig
        bootbase_contract = $bootbase
        manifest = $manifest
    }
}

if (-not (Test-Path -LiteralPath $BuildResultPath -PathType Leaf)) {
    Write-F89Status "missing_build" "F89 build-result.json not found"
    throw "F89 build-result.json not found: $BuildResultPath"
}
$buildResult = Get-Content -LiteralPath $BuildResultPath -Raw | ConvertFrom-Json
if ([string]$buildResult.status -ne "PASS") {
    Write-F89Status "build_not_pass" "F89 build-result.json is not PASS"
    throw "F89 build-result.json is not PASS"
}
$inputs = Set-F89FlashEnvironment $buildResult

$preflightLog = Join-Path $OutputDir "preflight.log"
$preflight = & python (Join-Path $Root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py") `
    --port $Port `
    --server-ip $ServerIp `
    --client-ip $ClientIp `
    --host $HostAddress `
    --timeout $FlashTimeoutSeconds 2>&1
$preflightRc = $LASTEXITCODE
$preflight | Set-Content -Encoding utf8 -LiteralPath $preflightLog
if ($preflightRc -ne 0 -or (($preflight -join "`n") -notmatch "MTD4_FLASH_ONE_SHOT_DRY_RUN_PASS=1")) {
    Write-F89Status "preflight_failed" "F89 local flash preflight failed" @{
        inputs = $inputs
        preflight_log = $preflightLog
        exit_code = $preflightRc
    }
    throw "F89 backend dry-run preflight failed; see $preflightLog"
}

if (-not $Execute) {
    Write-F89Status "dry_run_pass" "F89 local flash preflight passed; no router writes" @{
        inputs = $inputs
        preflight_log = $preflightLog
    }
    Write-Host "OMF89_FLASH_WRAPPER_DRY_RUN_PASS=1 status=$StatusPath"
    exit 0
}
if ($Ack -ne $RequiredAck) {
    Write-F89Status "ack_required" "Execute requires exact F89 acknowledgement" @{
        inputs = $inputs
        preflight_log = $preflightLog
    }
    throw "Execute requires exact Ack: $RequiredAck"
}
if ($NoRxAbortSeconds -eq 0 -and -not $AllowInfiniteNoRxWait) {
    Write-F89Status "invalid_no_rx_abort" "Execute refuses infinite UART RX wait unless explicitly allowed" @{
        inputs = $inputs
        preflight_log = $preflightLog
    }
    throw "Refusing infinite UART RX wait"
}

Write-F89Status "running_foreground" "F89 flash watcher running in foreground" @{
    inputs = $inputs
    preflight_log = $preflightLog
}
$q3Params = @{
    Execute = $true
    Ack = $RequiredAck
    Port = $Port
    ServerIp = $ServerIp
    ClientIp = $ClientIp
    HostAddress = $HostAddress
    BootWaitSeconds = $BootWaitSeconds
    NoRxAbortSeconds = $NoRxAbortSeconds
    FlashTimeoutSeconds = $FlashTimeoutSeconds
    CurrentLiveCrc32 = $CurrentLiveCrc32.ToLowerInvariant()
    AllowNoRxRebootAssist = $true
}
if ($PulseResetLinesFirst) { $q3Params.PulseResetLinesFirst = $true }
if ($SysRqRebootFirst) { $q3Params.SysRqRebootFirst = $true }
if ($SshRebootFirst) { $q3Params.SshRebootFirst = $true }
if ($ConsoleRebootAssist) { $q3Params.ConsoleRebootAssist = $true }

$rc = 1
$failureReason = $null
try {
    & (Join-Path $Root "tools\q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1") @q3Params
    $rc = [int]$LASTEXITCODE
} catch {
    Write-Host "OMF89_FLASH_WRAPPER_EXCEPTION=$($_.Exception.Message)"
    $failureReason = $_.Exception.Message
    $rc = 1
}
if ($rc -eq 0) {
    Write-F89Status "pass" "F89 flash completed and boot/SSH gate passed" @{
        inputs = $inputs
        preflight_log = $preflightLog
    }
} else {
    $failedState = "failed"
    $failedMessage = "F89 flash wrapper failed"
    if ($failureReason -match "UART_RX_SILENT_ZERO_BYTES") {
        $failedState = "uart_rx_zero"
        $failedMessage = "F89 flash wrapper aborted because UART RX stayed silent"
    }
    Write-F89Status $failedState $failedMessage @{
        inputs = $inputs
        preflight_log = $preflightLog
        exit_code = $rc
        failure_reason = $failureReason
    }
}
exit $rc
