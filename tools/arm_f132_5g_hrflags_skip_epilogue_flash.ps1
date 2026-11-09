[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "b168f55e",
    [ValidateRange(60, 21600)]
    [int]$BootWaitSeconds = 21600,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [ValidateRange(0, 300)]
    [int]$NoRxAbortSeconds = 60,
    [ValidateRange(0, 300)]
    [int]$BlindAtguAfterNoRxSeconds = 8,
    [switch]$PulseResetLinesFirst,
    [switch]$SysRqRebootFirst,
    [switch]$SshRebootFirst,
    [switch]$ConsoleRebootAssist,
    [switch]$AllowBlindAutobreak,
    [switch]$AllowNoRxRebootAssist,
    [switch]$KeepExistingTftp,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$BuildDir = Join-Path $Root "work\mission-state\q3-persistent-composite-f132-5g-hrflags-skip-epilogue-from-f129\build"
$Base = "openmitrastar-linux510-q3-persistent-f132-5g-hrflags-skip-epilogue-from-f129-LZMA-OFFLINE-NO-FLASH"
$Ack = "OPENMITRASTAR_Q3_F132_5G_HRFLAGS_SKIP_EPILOGUE_FROM_F129_MTD4_FLASH_8E4A13DB"
$ExpectedSha256 = "8e4a13db016a4caabe921d85351d693c51701520ee33bd4c3d01d1bde1d81a98"
$ExpectedBytes = "4373101"
$ExpectedCandidateCrc32 = "628125fb"
$ExpectedFullSlotCrc32 = "d11c5cbd"

if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\flash-watch\f132-5g-hrflags-skip-epilogue-from-f129-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StatusPath = Join-Path $OutputDir "status.json"

function Write-F132Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f132-auto-arm/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        execute = [bool]$Execute
        port = $Port
        server_ip = $ServerIp
        client_ip = $ClientIp
        host = $HostAddress
        current_live_crc32 = $CurrentLiveCrc32.ToLowerInvariant()
        ack = $Ack
        candidate = "f132-5g-hrflags-skip-epilogue-from-f129"
        candidate_sha256 = $ExpectedSha256
        candidate_crc32 = $ExpectedCandidateCrc32
        expected_full_slot_crc32 = $ExpectedFullSlotCrc32
        no_rx_abort_seconds = $NoRxAbortSeconds
        blind_atgu_after_no_rx_seconds = $BlindAtguAfterNoRxSeconds
    }
    foreach ($key in $Extra.Keys) { $payload[$key] = $Extra[$key] }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $StatusPath
}

$candidate = Join-Path $BuildDir ($Base + ".webformat.bin")
$contract = Join-Path $BuildDir "bootbase-contract.json"
$manifest = Join-Path $BuildDir "manifest.json"
$initramfs = Join-Path $BuildDir ($Base + ".decompressed.bin")
$kconfig = Join-Path $BuildDir ($Base + ".config")
foreach ($path in @($candidate, $contract, $manifest, $initramfs, $kconfig)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Write-F132Status "missing_input" "F132 input missing" @{ missing = $path }
        throw "missing F132 input: $path"
    }
}

$actualSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant()
$actualBytes = (Get-Item -LiteralPath $candidate).Length
if ($actualSha -ne $ExpectedSha256 -or [string]$actualBytes -ne $ExpectedBytes) {
    Write-F132Status "candidate_mismatch" "F132 candidate hash/size mismatch" @{
        actual_sha256 = $actualSha
        actual_bytes = $actualBytes
    }
    throw "F132 candidate hash/size mismatch"
}

$contractJson = Get-Content -Raw -LiteralPath $contract | ConvertFrom-Json
if ($contractJson.result -ne "PASS") {
    Write-F132Status "bootbase_contract_failed" "F132 Bootbase contract is not PASS" @{ bootbase_result = $contractJson.result }
    throw "F132 Bootbase contract is not PASS"
}

$env:OM_Q3_FLASH_ACK = $Ack
$env:OM_Q3_FLASH_BUILD_DIR = $BuildDir
$env:OM_Q3_FLASH_CANDIDATE = $candidate
$env:OM_Q3_FLASH_BOOTBASE_CONTRACT = $contract
$env:OM_Q3_FLASH_MANIFEST = $manifest
$env:OM_Q3_FLASH_INITRAMFS = $initramfs
$env:OM_Q3_FLASH_KCONFIG = $kconfig
$env:OM_Q3_FLASH_EXPECTED_SHA256 = $ExpectedSha256
$env:OM_Q3_FLASH_EXPECTED_BYTES = $ExpectedBytes
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $CurrentLiveCrc32.ToLowerInvariant()

$dryLog = Join-Path $OutputDir "dry-run.log"
$dry = python (Join-Path $Root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py") `
    --port $Port --server-ip $ServerIp --client-ip $ClientIp --host $HostAddress --timeout $FlashTimeoutSeconds 2>&1
$dry | Set-Content -Encoding utf8 -LiteralPath $dryLog
if ($LASTEXITCODE -ne 0 -or (($dry -join "`n") -notmatch "MTD4_FLASH_ONE_SHOT_DRY_RUN_PASS=1")) {
    Write-F132Status "dry_run_failed" "F132 dry-run failed" @{ dry_run_log = $dryLog }
    throw "F132 dry-run failed; see $dryLog"
}

if (-not $Execute) {
    Write-F132Status "dry_run_pass" "F132 dry-run passed; no router writes" @{ dry_run_log = $dryLog }
    Write-Host "OMF132_AUTO_ARM_DRY_RUN_PASS=1 status=$StatusPath"
    exit 0
}

Write-F132Status "executing_flash" "F132 flash helper running in foreground" @{ dry_run_log = $dryLog }
$args = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $Root "tools\q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1"),
    "-Execute",
    "-Ack", $Ack,
    "-Port", $Port,
    "-ServerIp", $ServerIp,
    "-ClientIp", $ClientIp,
    "-HostAddress", $HostAddress,
    "-CurrentLiveCrc32", $CurrentLiveCrc32.ToLowerInvariant(),
    "-BootWaitSeconds", "$BootWaitSeconds",
    "-FlashTimeoutSeconds", "$FlashTimeoutSeconds",
    "-NoRxAbortSeconds", "$NoRxAbortSeconds",
    "-BlindAtguAfterNoRxSeconds", "$BlindAtguAfterNoRxSeconds"
)
if ($PulseResetLinesFirst) { $args += "-PulseResetLinesFirst" }
if ($SysRqRebootFirst) {
    $args += "-SysRqRebootFirst"
    $args += "-SysRqRetrySeconds"
    $args += "5"
}
if ($SshRebootFirst) { $args += "-SshRebootFirst" }
if ($ConsoleRebootAssist) {
    $args += "-ConsoleRebootAssist"
    $args += "-ConsoleRebootRetrySeconds"
    $args += "5"
}
if ($AllowBlindAutobreak) { $args += "-AllowBlindAutobreak" }
if ($AllowNoRxRebootAssist) { $args += "-AllowNoRxRebootAssist" }
if ($KeepExistingTftp) { $args += "-KeepExistingTftp" }

$stdout = Join-Path $OutputDir "flash.stdout.log"
$stderr = Join-Path $OutputDir "flash.stderr.log"
$commandPath = Join-Path $OutputDir "flash-command.args.json"
@{
    executable = "powershell.exe"
    args = $args
    env = @{
        OM_Q3_FLASH_ACK = $Ack
        OM_Q3_FLASH_BUILD_DIR = $BuildDir
        OM_Q3_FLASH_CANDIDATE = $candidate
        OM_Q3_FLASH_BOOTBASE_CONTRACT = $contract
        OM_Q3_FLASH_MANIFEST = $manifest
        OM_Q3_FLASH_INITRAMFS = $initramfs
        OM_Q3_FLASH_KCONFIG = $kconfig
        OM_Q3_FLASH_EXPECTED_SHA256 = $ExpectedSha256
        OM_Q3_FLASH_EXPECTED_BYTES = $ExpectedBytes
        OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $CurrentLiveCrc32.ToLowerInvariant()
    }
} | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $commandPath

$nativeError = ""
try {
    & powershell.exe @args > $stdout 2> $stderr
    $rc = $LASTEXITCODE
} catch {
    $nativeError = $_.Exception.Message
    $rc = if ($LASTEXITCODE) { $LASTEXITCODE } else { 1 }
}
if ($rc -eq 0) {
    Write-F132Status "flash_pass" "F132 flash helper completed" @{
        stdout = $stdout
        stderr = $stderr
        command = $commandPath
    }
    Write-Host "OMF132_FLASH_PASS=1 status=$StatusPath stdout=$stdout"
    exit 0
}
$extra = @{
    stdout = $stdout
    stderr = $stderr
    command = $commandPath
    exit_code = $rc
}
if ($nativeError) { $extra["native_error"] = $nativeError }
Write-F132Status "flash_failed" "F132 flash helper failed" $extra
throw "F132 flash failed rc=$rc; see $stdout and $stderr"
