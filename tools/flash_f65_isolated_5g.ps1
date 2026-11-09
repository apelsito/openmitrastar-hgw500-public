param(
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [ValidateRange(60, 1200)]
    [int]$BootWaitSeconds = 600,
    [switch]$PulseResetLinesFirst,
    [switch]$ConsoleRebootAssist,
    [switch]$SysRqRebootFirst,
    [switch]$SshRebootFirst,
    [switch]$KeepExistingTftp
)

$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Build = Join-Path $Root "work\mission-state\q3-persistent-composite-f65\build"
$Candidate = Join-Path $Build "openmitrastar-linux510-q3-persistent-f65-isolated-5g-LZMA-OFFLINE-NO-FLASH.webformat.bin"
$ExpectedSha256 = "2f4d1ec8388058b11d8ce382731747af2b1a1988fcd5f035a051a0122bf965ad"
$ExpectedBytes = 5612989

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
    throw "Missing F65 candidate: $Candidate"
}
$candidateItem = Get-Item -LiteralPath $Candidate
if ($candidateItem.Length -ne $ExpectedBytes) {
    throw "F65 candidate size mismatch: expected=$ExpectedBytes actual=$($candidateItem.Length)"
}
$candidateSha = Get-Sha256Compat $Candidate
if ($candidateSha -ne $ExpectedSha256) {
    throw "F65 candidate SHA256 mismatch: expected=$ExpectedSha256 actual=$candidateSha"
}

$env:OM_Q3_FLASH_BUILD_DIR = $Build
$env:OM_Q3_FLASH_CANDIDATE = $Candidate
$env:OM_Q3_FLASH_BOOTBASE_CONTRACT = Join-Path $Build "bootbase-contract.json"
$env:OM_Q3_FLASH_MANIFEST = Join-Path $Build "manifest.json"
$env:OM_Q3_FLASH_INITRAMFS = Join-Path $Build "openmitrastar-linux510-q3-persistent-f65-isolated-5g-LZMA-OFFLINE-NO-FLASH.decompressed.bin"
$env:OM_Q3_FLASH_KCONFIG = Join-Path $Build "openmitrastar-linux510-q3-persistent-f65-isolated-5g-LZMA-OFFLINE-NO-FLASH.config"
$env:OM_Q3_FLASH_EXPECTED_SHA256 = $ExpectedSha256
$env:OM_Q3_FLASH_EXPECTED_BYTES = "$ExpectedBytes"
$env:OM_Q3_FLASH_ACK = "OPENMITRASTAR_Q3_F65_ISOLATED_5G_MTD4_FLASH_2F4D1EC8"
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = "b05e9b7b"
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = "303a2aaf43046eca8f0c461021a380537f7984867e390e828d23958666260809"

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
    "-FlashTimeoutSeconds", "900"
)
if ($PulseResetLinesFirst) { $args += "-PulseResetLinesFirst" }
if ($ConsoleRebootAssist) { $args += "-ConsoleRebootAssist" }
if ($SysRqRebootFirst) { $args += "-SysRqRebootFirst" }
if ($SshRebootFirst) { $args += "-SshRebootFirst" }
if ($KeepExistingTftp) { $args += "-KeepExistingTftp" }

& powershell @args
