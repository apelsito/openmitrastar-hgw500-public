[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "fa2a5be1",
    [ValidateRange(600, 21600)]
    [int]$BootWaitSeconds = 21600,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [ValidateRange(0, 300)]
    [int]$NoRxAbortSeconds = 0,
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
$BuildDir = Join-Path $Root "work\mission-state\q3-persistent-composite-f129-5g-oem-region-txpower-from-f128\build"
$Base = "openmitrastar-linux510-q3-persistent-f129-5g-oem-region-txpower-from-f128-LZMA-OFFLINE-NO-FLASH"
$Ack = "OPENMITRASTAR_Q3_F129_5G_OEM_REGION_TXPOWER_FROM_F128_MTD4_FLASH_0FD2EDC2"
$ExpectedSha256 = "0fd2edc274d13801b6e3c1af4732812c1d9dc9f8064f330a3d9e5650e97e21f0"
$ExpectedBytes = "4373785"
$ExpectedCandidateCrc32 = "c314002c"
$ExpectedFullSlotCrc32 = "d48200d4"

if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\flash-watch\f129-5g-oem-region-txpower-from-f128-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StatusPath = Join-Path $OutputDir "status.json"

function Write-F129Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f129-auto-arm/v1"
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
        candidate = "f129-5g-oem-region-txpower-from-f128"
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
        Write-F129Status "missing_input" "F129 input missing" @{ missing = $path }
        throw "missing F129 input: $path"
    }
}

$actualSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant()
$actualBytes = (Get-Item -LiteralPath $candidate).Length
if ($actualSha -ne $ExpectedSha256 -or [string]$actualBytes -ne $ExpectedBytes) {
    Write-F129Status "candidate_mismatch" "F129 candidate hash/size mismatch" @{
        actual_sha256 = $actualSha
        actual_bytes = $actualBytes
    }
    throw "F129 candidate hash/size mismatch"
}

$contractJson = Get-Content -Raw -LiteralPath $contract | ConvertFrom-Json
if ($contractJson.result -ne "PASS") {
    Write-F129Status "bootbase_contract_failed" "F129 Bootbase contract is not PASS" @{ bootbase_result = $contractJson.result }
    throw "F129 Bootbase contract is not PASS"
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
    Write-F129Status "dry_run_failed" "F129 dry-run failed" @{ dry_run_log = $dryLog }
    throw "F129 dry-run failed; see $dryLog"
}

if (-not $Execute) {
    Write-F129Status "dry_run_pass" "F129 dry-run passed; no router writes" @{ dry_run_log = $dryLog }
    Write-Host "OMF129_AUTO_ARM_DRY_RUN_PASS=1 status=$StatusPath"
    exit 0
}

Write-F129Status "executing_flash" "F129 flash helper running in foreground" @{ dry_run_log = $dryLog }
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

& powershell.exe @args > $stdout 2> $stderr
$rc = $LASTEXITCODE
if ($rc -eq 0) {
    Write-F129Status "flash_pass" "F129 flash helper completed" @{
        stdout = $stdout
        stderr = $stderr
        command = $commandPath
    }
    Write-Host "OMF129_FLASH_PASS=1 status=$StatusPath stdout=$stdout"
    exit 0
}
Write-F129Status "flash_failed" "F129 flash helper failed" @{
    stdout = $stdout
    stderr = $stderr
    command = $commandPath
    exit_code = $rc
}
throw "F129 flash failed rc=$rc; see $stdout and $stderr"
