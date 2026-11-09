param(
    [switch]$Execute,
    [string]$Ack = "OPENMITRASTAR_Q3_F72_QCSAPI_EXEC_LOADER_MTD4_FLASH_E1B04D8B",
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
    [string]$CurrentLiveCrc32 = "e0a77144",
    [switch]$AllowBlindAutobreak,
    [switch]$KeepExistingTftp
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Build = Join-Path $Root "work\mission-state\q3-persistent-composite-f72-5g-qcsapi-exec-loader\build"
$Base = "openmitrastar-linux510-q3-persistent-f72-5g-qcsapi-exec-loader-LZMA-OFFLINE-NO-FLASH"
$Candidate = Join-Path $Build "$Base.webformat.bin"
$ResultPath = Join-Path $Build "build-result.json"
$RequiredAck = "OPENMITRASTAR_Q3_F72_QCSAPI_EXEC_LOADER_MTD4_FLASH_E1B04D8B"

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
    & python (Join-Path $Root "tools\build_f72_qcsapi_exec_loader_from_f70.py")
    if ($LASTEXITCODE -ne 0) { throw "F72 build failed" }
}

Require-File $ResultPath
Require-File $Candidate
$result = Get-Content -LiteralPath $ResultPath -Raw | ConvertFrom-Json
if ($result.status -ne "PASS") { throw "F72 build-result is not PASS" }
if ($result.candidate_sha256 -ne "e1b04d8b2e6c609b453524d8109a30fa60e7a93b88114a77050cc28e6b70d0a0") { throw "F72 candidate SHA drift" }
if ([long]$result.candidate_bytes -ne 5612681) { throw "F72 candidate size drift" }
if ($result.candidate_crc32 -ne "35859eb1") { throw "F72 candidate CRC drift" }
if ($result.full_slot_crc32 -ne "1a3f9be6") { throw "F72 full-slot CRC drift" }
if ($result.full_slot_sha256 -ne "7b333b5e26b87ad55f048dd9021b34ff9f66983cff44a3bc30391260e0db03a7") { throw "F72 full-slot SHA drift" }

$observed = Get-Sha256Hex $Candidate
if ($observed -ne $result.candidate_sha256) { throw "F72 candidate file hash mismatch" }

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
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = "340e8d5e4a35871ab9c18bd4e1fdb29eb8a4221baa1b6cf1d58eb9fde781a2a5"

if (-not $Execute) {
    Write-Host "OMF72_RECOVERY_READY=1"
    Write-Host "candidate=$Candidate"
    Write-Host "candidate_sha256=$($result.candidate_sha256)"
    Write-Host "current_live_crc32_expected=$CurrentLiveCrc32"
    Write-Host "flash=0 reason=missing_-Execute"
    exit 0
}
if ($Ack -ne $RequiredAck) {
    throw "Exact acknowledgement required: $RequiredAck"
}

$flashScript = Join-Path $Root "tools\q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1"
if ($AllowBlindAutobreak -and $KeepExistingTftp) {
    & $flashScript -Execute -Ack $RequiredAck -Port $Port -ServerIp $ServerIp -ClientIp $ClientIp -HostAddress $HostAddress -CurrentLiveCrc32 $CurrentLiveCrc32 -BootWaitSeconds $BootWaitSeconds -FlashTimeoutSeconds $FlashTimeoutSeconds -NoRxAbortSeconds $NoRxAbortSeconds -AllowNoRxRebootAssist -AllowBlindAutobreak -KeepExistingTftp
} elseif ($AllowBlindAutobreak) {
    & $flashScript -Execute -Ack $RequiredAck -Port $Port -ServerIp $ServerIp -ClientIp $ClientIp -HostAddress $HostAddress -CurrentLiveCrc32 $CurrentLiveCrc32 -BootWaitSeconds $BootWaitSeconds -FlashTimeoutSeconds $FlashTimeoutSeconds -NoRxAbortSeconds $NoRxAbortSeconds -AllowNoRxRebootAssist -AllowBlindAutobreak
} elseif ($KeepExistingTftp) {
    & $flashScript -Execute -Ack $RequiredAck -Port $Port -ServerIp $ServerIp -ClientIp $ClientIp -HostAddress $HostAddress -CurrentLiveCrc32 $CurrentLiveCrc32 -BootWaitSeconds $BootWaitSeconds -FlashTimeoutSeconds $FlashTimeoutSeconds -NoRxAbortSeconds $NoRxAbortSeconds -AllowNoRxRebootAssist -KeepExistingTftp
} else {
    & $flashScript -Execute -Ack $RequiredAck -Port $Port -ServerIp $ServerIp -ClientIp $ClientIp -HostAddress $HostAddress -CurrentLiveCrc32 $CurrentLiveCrc32 -BootWaitSeconds $BootWaitSeconds -FlashTimeoutSeconds $FlashTimeoutSeconds -NoRxAbortSeconds $NoRxAbortSeconds -AllowNoRxRebootAssist
}
exit $LASTEXITCODE
