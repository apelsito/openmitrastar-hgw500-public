param(
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [ValidateRange(60, 1200)]
    [int]$BootWaitSeconds = 600,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [ValidateRange(5, 300)]
    [int]$NoRxAbortSeconds = 30,
    [switch]$PulseResetLinesFirst,
    [switch]$ConsoleRebootAssist,
    [switch]$SysRqRebootFirst,
    [switch]$SshRebootFirst,
    [switch]$AllowBlindAutobreak,
    [switch]$AllowNoRxRebootAssist,
    [switch]$KeepExistingTftp,
    [string]$CurrentLiveCrc32 = "26523198"
)

$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Build = Join-Path $Root "work\mission-state\q3-persistent-composite-f66-2g-queue-guard\build"
$Base = "openmitrastar-linux510-q3-persistent-f66-2g-autorate-reclaim-LZMA-OFFLINE-NO-FLASH"
$Candidate = Join-Path $Build "$Base.webformat.bin"
$ExpectedSha256 = "021cd4896ee54db95addd3b3c4111eb811b2dcf77a69c87b28b94dd4bec4b341"
$ExpectedBytes = 5613197

function Get-Sha256Compat([string]$Path) {
    if (Get-Command Get-FileHash -ErrorAction SilentlyContinue) {
        return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    }
    $raw = & certutil.exe -hashfile $Path SHA256
    if ($LASTEXITCODE -ne 0) {
        throw "certutil SHA256 failed for $Path"
    }
    $hex = @($raw | Where-Object { $_ -match '^[0-9a-fA-F ]{32,}$' } | Select-Object -First 1)
    if (-not $hex) {
        throw "certutil SHA256 output parse failed for $Path"
    }
    return (($hex -replace '\s+', '').ToLowerInvariant())
}

if (-not (Test-Path -LiteralPath $Candidate)) {
    throw "Missing F66 candidate; run tools\build_f66_fixedsize_from_f65.py first: $Candidate"
}
$candidateItem = Get-Item -LiteralPath $Candidate
if ($candidateItem.Length -ne $ExpectedBytes) {
    throw "F66 candidate size mismatch: expected=$ExpectedBytes actual=$($candidateItem.Length)"
}
$candidateSha = Get-Sha256Compat $Candidate
if ($candidateSha -ne $ExpectedSha256) {
    throw "F66 candidate SHA256 mismatch: expected=$ExpectedSha256 actual=$candidateSha"
}

$preflightScript = Join-Path $PSScriptRoot "verify_f66_offline_preflight.py"
if (-not (Test-Path -LiteralPath $preflightScript -PathType Leaf)) {
    throw "Missing F66 offline preflight verifier: $preflightScript"
}
& python $preflightScript --current-live-crc32 $CurrentLiveCrc32
if ($LASTEXITCODE -ne 0) {
    throw "F66 offline preflight failed"
}

$env:OM_Q3_FLASH_BUILD_DIR = $Build
$env:OM_Q3_FLASH_CANDIDATE = $Candidate
$env:OM_Q3_FLASH_BOOTBASE_CONTRACT = Join-Path $Build "bootbase-contract.json"
$env:OM_Q3_FLASH_MANIFEST = Join-Path $Build "manifest.json"
$env:OM_Q3_FLASH_INITRAMFS = Join-Path $Build "$Base.decompressed.bin"
$env:OM_Q3_FLASH_KCONFIG = Join-Path $Build "$Base.config"
$env:OM_Q3_FLASH_EXPECTED_SHA256 = $ExpectedSha256
$env:OM_Q3_FLASH_EXPECTED_BYTES = "$ExpectedBytes"
$env:OM_Q3_FLASH_ACK = "OPENMITRASTAR_Q3_F66_2G_AUTORATE_RECLAIM_MTD4_FLASH_021CD489"
$env:OM_Q3_FLASH_SSH_KEY = Join-Path $Root ".codex_tmp\openmitrastar_ramssh_client_ed25519"
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $CurrentLiveCrc32
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = "f81e68041e8f5e1fa4c51c47330186096a9e51a51ccfd43b6905ebcb57b29fe8"

$args = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot "q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1"),
    "-Execute",
    "-Ack", $env:OM_Q3_FLASH_ACK,
    "-Port", $Port,
    "-ServerIp", $ServerIp,
    "-ClientIp", $ClientIp,
    "-HostAddress", $HostAddress,
    "-CurrentLiveCrc32", $env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32,
    "-BootWaitSeconds", "$BootWaitSeconds",
    "-FlashTimeoutSeconds", "$FlashTimeoutSeconds",
    "-NoRxAbortSeconds", "$NoRxAbortSeconds"
)
if ($PulseResetLinesFirst) { $args += "-PulseResetLinesFirst" }
if ($ConsoleRebootAssist) { $args += "-ConsoleRebootAssist" }
if ($SysRqRebootFirst) { $args += "-SysRqRebootFirst" }
if ($SshRebootFirst) { $args += "-SshRebootFirst" }
if ($AllowBlindAutobreak) { $args += "-AllowBlindAutobreak" }
if ($AllowNoRxRebootAssist) { $args += "-AllowNoRxRebootAssist" }
if ($KeepExistingTftp) { $args += "-KeepExistingTftp" }

& powershell @args
