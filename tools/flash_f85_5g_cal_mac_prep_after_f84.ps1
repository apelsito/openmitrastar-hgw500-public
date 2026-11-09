[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [switch]$Background,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "89ac7c94",
    [ValidateRange(60, 21600)]
    [int]$BootWaitSeconds = 21600,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [ValidateRange(0, 21600)]
    [int]$NoRxAbortSeconds = 300,
    [switch]$NoBlindAutobreak,
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
$BuildDir = Join-Path $Root "work\mission-state\q3-persistent-composite-f85-5g-cal-mac-prep-after-f84\build"
$BuildResultPath = Join-Path $BuildDir "build-result.json"
$RequiredAck = "OPENMITRASTAR_Q3_F85_5G_CAL_MAC_PREP_AFTER_F84_MTD4_FLASH_E78CA868"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
if (-not $OutputDir) {
    $OutputDir = Join-Path $Root "outputs\flash-watch\f85-5g-cal-mac-prep-after-f84-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StatusPath = Join-Path $OutputDir "status.json"
$StdoutPath = Join-Path $OutputDir "stdout.log"
$StderrPath = Join-Path $OutputDir "stderr.log"

function Write-F85Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f85-flash-wrapper/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        build_dir = $BuildDir
        execute = [bool]$Execute
        background = [bool]$Background
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
    if ($env:OM_F85_FLASH_LAUNCH_LOG) {
        $payload.external_stdout_log = $env:OM_F85_FLASH_LAUNCH_LOG
    }
    if ($env:OM_F85_FLASH_LAUNCH_STDERR_LOG) {
        $payload.external_stderr_log = $env:OM_F85_FLASH_LAUNCH_STDERR_LOG
    }
    foreach ($key in $Extra.Keys) {
        $payload[$key] = $Extra[$key]
    }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $StatusPath
}

function Get-Sha256Hex([string]$Path) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Get-FlashOwners {
    $self = $PID
    $parent = $null
    try {
        $current = Get-CimInstance Win32_Process -Filter "ProcessId=$self" -ErrorAction Stop
        $parent = [int]$current.ParentProcessId
    } catch {
        $parent = $null
    }
    @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ProcessId -ne $self -and
            (-not $parent -or $_.ProcessId -ne $parent) -and
            $_.CommandLine -and
            (
                $_.CommandLine -match 'q3_f45|bootbase_flash|capture_topaz|oem_uart' -or
                ($_.Name -match 'powershell|pwsh' -and $_.CommandLine -match 'flash_f(?:7[56789]|8[0-9]).*_5g' -and $_.CommandLine -match '-Execute')
            )
        } |
        ForEach-Object {
            [ordered]@{
                process_id = [int]$_.ProcessId
                parent_process_id = [int]$_.ParentProcessId
                name = [string]$_.Name
                command_line = [string]$_.CommandLine
            }
        })
}

function Set-F85FlashEnvironment([object]$BuildResult) {
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
            throw "missing F85 flash input: $path"
        }
    }
    if ((Get-Sha256Hex $candidate) -ne [string]$BuildResult.candidate_sha256) {
        throw "F85 candidate hash mismatch"
    }
    if ((Get-Item -LiteralPath $candidate).Length -ne [long]$BuildResult.candidate_bytes) {
        throw "F85 candidate size mismatch"
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
    Write-F85Status "missing_build" "F85 build-result.json not found"
    throw "F85 build-result.json not found: $BuildResultPath"
}

$buildResult = Get-Content -LiteralPath $BuildResultPath -Raw | ConvertFrom-Json
if ([string]$buildResult.status -ne "PASS") {
    Write-F85Status "build_not_pass" "F85 build-result.json is not PASS"
    throw "F85 build-result.json is not PASS"
}
$inputs = Set-F85FlashEnvironment $buildResult

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
    Write-F85Status "preflight_failed" "F85 local flash preflight failed" @{
        inputs = $inputs
        preflight_log = $preflightLog
        exit_code = $preflightRc
    }
    throw "F85 backend dry-run preflight failed; see $preflightLog"
}

if (-not $Execute) {
    Write-F85Status "dry_run_pass" "F85 local flash preflight passed; no router writes" @{
        inputs = $inputs
        preflight_log = $preflightLog
    }
    Write-Host "OMF85_FLASH_WRAPPER_DRY_RUN_PASS=1 status=$StatusPath"
    exit 0
}

if ($Ack -ne $RequiredAck) {
    Write-F85Status "ack_required" "Execute requires exact F85 acknowledgement" @{
        inputs = $inputs
        preflight_log = $preflightLog
    }
    throw "Execute requires exact Ack: $RequiredAck"
}

if ($NoRxAbortSeconds -eq 0 -and -not $AllowInfiniteNoRxWait) {
    Write-F85Status "invalid_no_rx_abort" "Execute refuses infinite UART RX wait unless -AllowInfiniteNoRxWait is explicit" @{
        inputs = $inputs
        preflight_log = $preflightLog
    }
    throw "Refusing infinite UART RX wait: pass -AllowInfiniteNoRxWait only for a deliberate long manual bench watch."
}

$owners = @(Get-FlashOwners)
if ($owners.Count -gt 0) {
    Write-F85Status "busy_com3" "Another COM3/flash/UART owner is active" @{
        inputs = $inputs
        preflight_log = $preflightLog
        owners = $owners
    }
    throw "Another COM3/flash/UART owner is active"
}

if ($Background) {
    function Quote-PsLiteral([string]$Text) {
        "'" + ($Text -replace "'", "''") + "'"
    }
    $command = @(
        "&",
        (Quote-PsLiteral $PSCommandPath),
        "-Execute",
        "-Ack", (Quote-PsLiteral $RequiredAck),
        "-Port", (Quote-PsLiteral $Port),
        "-ServerIp", (Quote-PsLiteral $ServerIp),
        "-ClientIp", (Quote-PsLiteral $ClientIp),
        "-HostAddress", (Quote-PsLiteral $HostAddress),
        "-CurrentLiveCrc32", (Quote-PsLiteral $CurrentLiveCrc32.ToLowerInvariant()),
        "-BootWaitSeconds", [string]$BootWaitSeconds,
        "-FlashTimeoutSeconds", [string]$FlashTimeoutSeconds,
        "-NoRxAbortSeconds", [string]$NoRxAbortSeconds,
        "-OutputDir", (Quote-PsLiteral $OutputDir)
    )
    if ($NoBlindAutobreak) { $command += "-NoBlindAutobreak" }
    if ($AllowInfiniteNoRxWait) { $command += "-AllowInfiniteNoRxWait" }
    if ($PulseResetLinesFirst) { $command += "-PulseResetLinesFirst" }
    if ($SysRqRebootFirst) { $command += "-SysRqRebootFirst" }
    if ($SshRebootFirst) { $command += "-SshRebootFirst" }
    if ($ConsoleRebootAssist) { $command += "-ConsoleRebootAssist" }
    $childCommand = $command -join " "
    $childCommand | Set-Content -Encoding ascii -LiteralPath (Join-Path $OutputDir "child-command.ps1")
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($childCommand))
    $proc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded" `
        -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath -PassThru
    Write-F85Status "background_armed" "F85 flash watcher armed in background; power-cycle can now be caught" @{
        inputs = $inputs
        preflight_log = $preflightLog
        process_id = $proc.Id
        stdout = $StdoutPath
        stderr = $StderrPath
    }
    Write-Host "OMF85_FLASH_WRAPPER_BACKGROUND_ARMED=1 pid=$($proc.Id) status=$StatusPath"
    exit 0
}

Write-F85Status "running_foreground" "F85 flash watcher running in foreground" @{
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
if (-not $NoBlindAutobreak) { $q3Params.AllowBlindAutobreak = $true }
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
    Write-Host "OMF85_FLASH_WRAPPER_EXCEPTION=$($_.Exception.Message)"
    $failureReason = $_.Exception.Message
    $rc = 1
}
if ($rc -eq 0) {
    Write-F85Status "pass" "F85 flash completed and boot/SSH gate passed" @{
        inputs = $inputs
        preflight_log = $preflightLog
    }
} else {
    $failedState = "failed"
    $failedMessage = "F85 flash wrapper failed"
    if ($failureReason -match "UART_RX_SILENT_ZERO_BYTES") {
        $failedState = "uart_rx_zero"
        $failedMessage = "F85 flash wrapper aborted because UART RX stayed silent"
    }
    Write-F85Status $failedState $failedMessage @{
        inputs = $inputs
        preflight_log = $preflightLog
        exit_code = $rc
        failure_reason = $failureReason
    }
}
exit $rc









