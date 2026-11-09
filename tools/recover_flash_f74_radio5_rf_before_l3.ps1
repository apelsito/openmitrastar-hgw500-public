param(
    [switch]$Execute,
    [string]$Ack = "OPENMITRASTAR_Q3_F74_RADIO5_RF_BEFORE_L3_MTD4_FLASH_56962C97",
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [ValidateRange(60, 21600)]
    [int]$BootWaitSeconds = 900,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [ValidateRange(0, 21600)]
    [int]$NoRxAbortSeconds = 300,
    [string]$CurrentLiveCrc32 = "484fd8c6",
    [switch]$SshRebootFirst,
    [switch]$SysRqRebootFirst,
    [switch]$ConsoleRebootAssist,
    [switch]$PulseResetLinesFirst,
    [switch]$AllowBlindAutobreak,
    [switch]$KeepExistingTftp
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Build = Join-Path $Root "work\mission-state\q3-persistent-composite-f74-5g-rf-before-l3\build"
$Base = "openmitrastar-linux510-q3-persistent-f74-5g-rf-before-l3-LZMA-OFFLINE-NO-FLASH"
$Candidate = Join-Path $Build "$Base.webformat.bin"
$ResultPath = Join-Path $Build "build-result.json"
$RequiredAck = "OPENMITRASTAR_Q3_F74_RADIO5_RF_BEFORE_L3_MTD4_FLASH_56962C97"

function Require-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing required file: $Path"
    }
}

function Get-Sha256Hex([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    try {
        $sha = [Security.Cryptography.SHA256]::Create()
        try {
            return -join ($sha.ComputeHash($stream) | ForEach-Object { $_.ToString("x2") })
        } finally {
            $sha.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

if (-not (Test-Path -LiteralPath $ResultPath -PathType Leaf)) {
    & python (Join-Path $Root "tools\build_f74_radio5_rf_before_l3_from_f73.py")
    if ($LASTEXITCODE -ne 0) { throw "F74 build failed" }
}

Require-File $ResultPath
Require-File $Candidate
$result = Get-Content -LiteralPath $ResultPath -Raw | ConvertFrom-Json
if ($result.status -ne "PASS") { throw "F74 build-result is not PASS" }
if ($result.candidate_sha256 -ne "56962c97dbb59b136f0a2cc71a4be7d32c40b345f15b34bac0c99c23ee5ee009") { throw "F74 candidate SHA drift" }
if ([long]$result.candidate_bytes -ne 5612368) { throw "F74 candidate size drift" }
if ($result.candidate_crc32 -ne "33b885e7") { throw "F74 candidate CRC drift" }
if ($result.full_slot_crc32 -ne "67228a88") { throw "F74 full-slot CRC drift" }
if ($result.full_slot_sha256 -ne "7117d274de544459c3bd4bc2d60c6cd0afaf6281dcf82ab3d7fc43a41edaa268") { throw "F74 full-slot SHA drift" }
if ((Get-Sha256Hex $Candidate) -ne $result.candidate_sha256) { throw "F74 candidate file hash mismatch" }
if ([int]$result.patch.delta_bytes -ne 0) { throw "F74 fixed-offset patch drift" }
if ($result.patch.fix -ne "open qdrv RF before ifconfig wifi0 192.168.77.1 ... up") { throw "F74 patch fix drift" }

$env:OM_Q3_FLASH_BUILD_DIR = $Build
$env:OM_Q3_FLASH_CANDIDATE = $Candidate
$env:OM_Q3_FLASH_BOOTBASE_CONTRACT = Join-Path $Build "bootbase-contract.json"
$env:OM_Q3_FLASH_MANIFEST = Join-Path $Build "manifest.json"
$env:OM_Q3_FLASH_INITRAMFS = Join-Path $Build "$Base.decompressed.bin"
$env:OM_Q3_FLASH_KCONFIG = Join-Path $Build "$Base.config"
$env:OM_Q3_FLASH_EXPECTED_SHA256 = $result.candidate_sha256
$env:OM_Q3_FLASH_EXPECTED_BYTES = [string]$result.candidate_bytes
$env:OM_Q3_FLASH_ACK = $RequiredAck
$env:OM_Q3_FLASH_SSH_KEY = Join-Path $Root ".codex_tmp\openmitrastar_ramssh_client_ed25519"
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $CurrentLiveCrc32.ToLowerInvariant()
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = "cc46ec6400ec065baab03812748647875523553a8f09aa808b27723aeb52990f"

if (-not $Execute) {
    Write-Host "OMF74_RECOVERY_READY=1"
    Write-Host "candidate=$Candidate"
    Write-Host "candidate_sha256=$($result.candidate_sha256)"
    Write-Host "candidate_crc32=$($result.candidate_crc32)"
    Write-Host "full_slot_crc32=$($result.full_slot_crc32)"
    Write-Host "current_live_crc32_expected=$CurrentLiveCrc32"
    Write-Host "patch_delta_bytes=$($result.patch.delta_bytes)"
    Write-Host "flash=0 reason=missing_-Execute"
    exit 0
}
if ($Ack -ne $RequiredAck) {
    throw "Exact acknowledgement required: $RequiredAck"
}

$flashScript = Join-Path $Root "tools\q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1"
$args = @{
    Execute = $true
    Ack = $RequiredAck
    Port = $Port
    ServerIp = $ServerIp
    ClientIp = $ClientIp
    HostAddress = $HostAddress
    CurrentLiveCrc32 = $CurrentLiveCrc32
    BootWaitSeconds = $BootWaitSeconds
    FlashTimeoutSeconds = $FlashTimeoutSeconds
    NoRxAbortSeconds = $NoRxAbortSeconds
    AllowNoRxRebootAssist = $true
}
if ($SshRebootFirst) { $args.SshRebootFirst = $true }
if ($SysRqRebootFirst) { $args.SysRqRebootFirst = $true }
if ($ConsoleRebootAssist) { $args.ConsoleRebootAssist = $true }
if ($PulseResetLinesFirst) { $args.PulseResetLinesFirst = $true }
if ($AllowBlindAutobreak) { $args.AllowBlindAutobreak = $true }
if ($KeepExistingTftp) { $args.KeepExistingTftp = $true }
& $flashScript @args
exit $LASTEXITCODE
