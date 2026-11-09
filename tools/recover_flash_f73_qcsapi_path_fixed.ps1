param(
    [switch]$Execute,
    [string]$Ack = "OPENMITRASTAR_Q3_F73_QCSAPI_PATH_FIXED_MTD4_FLASH_DD4B4291",
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
    [string]$CurrentLiveCrc32 = "9e4e61cb",
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
$Build = Join-Path $Root "work\mission-state\q3-persistent-composite-f73-5g-qcsapi-path-fixed\build"
$Base = "openmitrastar-linux510-q3-persistent-f73-5g-qcsapi-path-fixed-LZMA-OFFLINE-NO-FLASH"
$Candidate = Join-Path $Build "$Base.webformat.bin"
$ResultPath = Join-Path $Build "build-result.json"
$RequiredAck = "OPENMITRASTAR_Q3_F73_QCSAPI_PATH_FIXED_MTD4_FLASH_DD4B4291"

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
    & python (Join-Path $Root "tools\build_f73_qcsapi_path_fixed_from_f70.py")
    if ($LASTEXITCODE -ne 0) { throw "F73 build failed" }
}

Require-File $ResultPath
Require-File $Candidate
$result = Get-Content -LiteralPath $ResultPath -Raw | ConvertFrom-Json
if ($result.status -ne "PASS") { throw "F73 build-result is not PASS" }
if ($result.candidate_sha256 -ne "dd4b4291674ac9e0c8fb0f3841deb6c44f3d6dac10b27447ba1d7072a41c9cd7") { throw "F73 candidate SHA drift" }
if ([long]$result.candidate_bytes -ne 5612205) { throw "F73 candidate size drift" }
if ($result.candidate_crc32 -ne "5f3ff30b") { throw "F73 candidate CRC drift" }
if ($result.full_slot_crc32 -ne "484fd8c6") { throw "F73 full-slot CRC drift" }
if ($result.full_slot_sha256 -ne "cc46ec6400ec065baab03812748647875523553a8f09aa808b27723aeb52990f") { throw "F73 full-slot SHA drift" }
if ((Get-Sha256Hex $Candidate) -ne $result.candidate_sha256) { throw "F73 candidate file hash mismatch" }
if ([int]$result.patch.delta_bytes -ne 0) { throw "F73 fixed-offset patch drift" }

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
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = "3a90cb33b1d71a83119f29ff9afbc4eab2f30711fde9fb562bf8993996f991bf"

if (-not $Execute) {
    Write-Host "OMF73_RECOVERY_READY=1"
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
