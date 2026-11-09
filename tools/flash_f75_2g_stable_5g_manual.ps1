[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [switch]$Background,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "67228a88",
    [ValidateRange(60, 21600)]
    [int]$BootWaitSeconds = 21600,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [ValidateRange(0, 21600)]
    [int]$NoRxAbortSeconds = 300,
    [switch]$NoBlindAutobreak,
    [switch]$PulseResetLinesFirst,
    [switch]$SysRqRebootFirst,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$BuildDir = Join-Path $Root "work\mission-state\q3-persistent-composite-f75-2g-stable-5g-manual\build"
$BuildResultPath = Join-Path $BuildDir "build-result.json"
$RequiredAck = "OPENMITRASTAR_Q3_F75_2G_STABLE_5G_MANUAL_MTD4_FLASH_97929CCA"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
if (-not $OutputDir) {
    $OutputDir = Join-Path $Root "outputs\flash-watch\f75-2g-stable-5g-manual-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StatusPath = Join-Path $OutputDir "status.json"
$StdoutPath = Join-Path $OutputDir "stdout.log"
$StderrPath = Join-Path $OutputDir "stderr.log"

function Write-F75Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f75-flash-wrapper/v1"
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
                ($_.Name -eq 'powershell.exe' -and $_.CommandLine -match 'flash_f75_2g_stable_5g_manual' -and $_.CommandLine -match '-Execute')
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

function Set-F75FlashEnvironment([object]$BuildResult) {
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
            throw "missing F75 flash input: $path"
        }
    }
    if ((Get-Sha256Hex $candidate) -ne [string]$BuildResult.candidate_sha256) {
        throw "F75 candidate hash mismatch"
    }
    if ((Get-Item -LiteralPath $candidate).Length -ne [long]$BuildResult.candidate_bytes) {
        throw "F75 candidate size mismatch"
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

function Invoke-F75Preflight([object]$Inputs) {
    $preflightLog = Join-Path $OutputDir "preflight.log"
    $output = & python (Join-Path $Root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py") `
        --port $Port `
        --server-ip $ServerIp `
        --client-ip $ClientIp `
        --host $HostAddress `
        --timeout $FlashTimeoutSeconds 2>&1
    $rc = $LASTEXITCODE
    $output | Set-Content -Encoding utf8 -LiteralPath $preflightLog
    if ($rc -ne 0 -or (($output -join "`n") -notmatch "MTD4_FLASH_ONE_SHOT_DRY_RUN_PASS=1")) {
        throw "F75 backend dry-run preflight failed; see $preflightLog"
    }
    return $preflightLog
}

if (-not (Test-Path -LiteralPath $BuildResultPath -PathType Leaf)) {
    Write-F75Status "missing_build" "F75 build-result.json not found"
    throw "F75 build-result.json not found: $BuildResultPath"
}

$buildResult = Get-Content -LiteralPath $BuildResultPath -Raw | ConvertFrom-Json
if ([string]$buildResult.status -ne "PASS") {
    Write-F75Status "build_not_pass" "F75 build-result.json is not PASS"
    throw "F75 build-result.json is not PASS"
}
$inputs = Set-F75FlashEnvironment $buildResult
$preflightLog = Invoke-F75Preflight $inputs

if (-not $Execute) {
    Write-F75Status "dry_run_pass" "F75 local flash preflight passed; no router writes" @{
        inputs = $inputs
        preflight_log = $preflightLog
    }
    Write-Host "OMF75_FLASH_WRAPPER_DRY_RUN_PASS=1 status=$StatusPath"
    exit 0
}

if ($Ack -ne $RequiredAck) {
    Write-F75Status "ack_required" "Execute requires exact F75 acknowledgement" @{
        inputs = $inputs
        preflight_log = $preflightLog
    }
    throw "Execute requires exact Ack: $RequiredAck"
}

$owners = @(Get-FlashOwners)
if ($owners.Count -gt 0) {
    Write-F75Status "busy_com3" "Another COM3/flash/UART owner is active" @{
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
    if ($PulseResetLinesFirst) { $command += "-PulseResetLinesFirst" }
    if ($SysRqRebootFirst) { $command += "-SysRqRebootFirst" }
    $childCommand = $command -join " "
    $childCommand | Set-Content -Encoding ascii -LiteralPath (Join-Path $OutputDir "child-command.ps1")
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($childCommand))
    $argumentLine = "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded"
    $proc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList $argumentLine -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath -PassThru
    Write-F75Status "background_armed" "F75 flash watcher armed in background; power-cycle can now be caught" @{
        inputs = $inputs
        preflight_log = $preflightLog
        process_id = $proc.Id
        stdout = $StdoutPath
        stderr = $StderrPath
    }
    Write-Host "OMF75_FLASH_WRAPPER_BACKGROUND_ARMED=1 pid=$($proc.Id) status=$StatusPath"
    exit 0
}

Write-F75Status "running_foreground" "F75 flash watcher running in foreground" @{
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

$rc = 1
try {
    & (Join-Path $Root "tools\q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1") @q3Params
    $rc = [int]$LASTEXITCODE
} catch {
    Write-Host "OMF75_FLASH_WRAPPER_EXCEPTION=$($_.Exception.Message)"
    $rc = 1
}
if ($rc -eq 0) {
    Write-F75Status "pass" "F75 flash completed and boot/SSH gate passed" @{
        inputs = $inputs
        preflight_log = $preflightLog
    }
} else {
    Write-F75Status "failed" "F75 flash wrapper failed" @{
        inputs = $inputs
        preflight_log = $preflightLog
        exit_code = $rc
    }
}
exit $rc
