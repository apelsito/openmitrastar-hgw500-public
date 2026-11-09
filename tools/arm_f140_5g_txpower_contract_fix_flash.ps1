[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "c551d363",
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
$BuildDir = Join-Path $Root "work\mission-state\q3-persistent-composite-f140-5g-txpower-contract-fix-from-f139\build"
$Base = "openmitrastar-linux510-q3-persistent-f140-5g-txpower-contract-fix-from-f139-LZMA-OFFLINE-NO-FLASH"
$Ack = "OPENMITRASTAR_Q3_F140_5G_TXPOWER_CONTRACT_FIX_FROM_F139_MTD4_FLASH_082186DF"
$ExpectedSha256 = "082186df27f2d1055f4ee619f980f637080b070d438ef060f912ac56ced6c9df"
$ExpectedBytes = "4373043"
$ExpectedCandidateCrc32 = "4e0a3b23"
$ExpectedFullSlotCrc32 = "256fab55"

if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\flash-watch\f140-5g-txpower-contract-fix-from-f139-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StatusPath = Join-Path $OutputDir "status.json"

function Write-F140Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f140-auto-arm/v1"
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
        candidate = "f140-5g-txpower-contract-fix-from-f139"
        candidate_sha256 = $ExpectedSha256
        candidate_crc32 = $ExpectedCandidateCrc32
        expected_full_slot_crc32 = $ExpectedFullSlotCrc32
        no_rx_abort_seconds = $NoRxAbortSeconds
        blind_atgu_after_no_rx_seconds = $BlindAtguAfterNoRxSeconds
    }
    foreach ($key in $Extra.Keys) { $payload[$key] = $Extra[$key] }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $StatusPath
}

function Get-FileSha256Hex([string]$Path) {
    if (Get-Command Get-FileHash -ErrorAction SilentlyContinue) {
        return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    }
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "").ToLowerInvariant()
    } finally {
        $sha.Dispose()
        $stream.Dispose()
    }
}

$candidate = Join-Path $BuildDir ($Base + ".webformat.bin")
$contract = Join-Path $BuildDir "bootbase-contract.json"
$manifest = Join-Path $BuildDir "manifest.json"
$initramfs = Join-Path $BuildDir ($Base + ".decompressed.bin")
$kconfig = Join-Path $BuildDir ($Base + ".config")
foreach ($path in @($candidate, $contract, $manifest, $initramfs, $kconfig)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Write-F140Status "missing_input" "F140 input missing" @{ missing = $path }
        throw "missing F140 input: $path"
    }
}

$actualSha = Get-FileSha256Hex $candidate
$actualBytes = (Get-Item -LiteralPath $candidate).Length
if ($actualSha -ne $ExpectedSha256 -or [string]$actualBytes -ne $ExpectedBytes) {
    Write-F140Status "candidate_mismatch" "F140 candidate hash/size mismatch" @{
        actual_sha256 = $actualSha
        actual_bytes = $actualBytes
    }
    throw "F140 candidate hash/size mismatch"
}

$contractJson = Get-Content -Raw -LiteralPath $contract | ConvertFrom-Json
if ($contractJson.result -ne "PASS") {
    Write-F140Status "bootbase_contract_failed" "F140 Bootbase contract is not PASS" @{ bootbase_result = $contractJson.result }
    throw "F140 Bootbase contract is not PASS"
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
    Write-F140Status "dry_run_failed" "F140 dry-run failed" @{ dry_run_log = $dryLog }
    throw "F140 dry-run failed; see $dryLog"
}

if (-not $Execute) {
    Write-F140Status "dry_run_pass" "F140 dry-run passed; no router writes" @{ dry_run_log = $dryLog }
    Write-Host "OMF140_AUTO_ARM_DRY_RUN_PASS=1 status=$StatusPath"
    exit 0
}

Write-F140Status "executing_flash" "F140 flash helper running in foreground" @{ dry_run_log = $dryLog }
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
    Write-F140Status "flash_pass" "F140 flash helper completed" @{
        stdout = $stdout
        stderr = $stderr
        command = $commandPath
    }
    Write-Host "OMF140_FLASH_PASS=1 status=$StatusPath stdout=$stdout"
    exit 0
}
$extra = @{
    stdout = $stdout
    stderr = $stderr
    command = $commandPath
    exit_code = $rc
}
if ($nativeError) { $extra.native_error = $nativeError }
Write-F140Status "flash_failed" "F140 flash helper failed" $extra
Write-Error "OMF140_FLASH_FAIL status=$StatusPath stdout=$stdout stderr=$stderr"
exit $rc
