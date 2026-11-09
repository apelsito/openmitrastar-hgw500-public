[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [switch]$SkipBuild,
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "7018e327"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $root "work\mission-state\q3-persistent-composite-f182-spi-probe-boot\build"
$base = "openmitrastar-linux510-q3-persistent-f182-spi-probe-boot-LZMA-OFFLINE-NO-FLASH"

if (-not $SkipBuild) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\build_f182_spi_probe_boot.ps1")
    if ($LASTEXITCODE -ne 0) { throw "F182 build failed" }
}

$manifestPath = Join-Path $build "manifest.json"
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$candidate = Join-Path $build $manifest.artifacts.webformat.file
$sha = [string]$manifest.artifacts.webformat.sha256
$bytes = [long]$manifest.artifacts.webformat.bytes
$ack = "OPENMITRASTAR_Q3_F182_SPI_READONLY_FLASH_$($sha.Substring(0,8).ToUpperInvariant())"

[ordered]@{
    mode = if ($Execute) { "execute" } else { "dry-run" }
    required_current_firmware = "F179"
    expected_current_full_slot_crc32 = $CurrentLiveCrc32
    candidate = $candidate
    bytes = $bytes
    sha256 = $sha
    candidate_crc32 = $manifest.artifacts.webformat.crc32
    full_slot_crc32 = $manifest.artifacts.full_slot.crc32
    target = "mtd4/linux_live"
    store = "read-only/unmounted"
    transport = "UART/YMODEM"
} | ConvertTo-Json -Depth 4

if (-not $Execute) { exit 0 }

$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$mtd = & $ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 `
    -i "$env:USERPROFILE\.ssh\id_ed25519" "root@$RouterHost" "cat /proc/mtd; sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release"
if ($LASTEXITCODE -ne 0) { throw "F182 preflight SSH failed" }
if ($mtd -match '"lyoko_store"') {
    throw "F182 full-slot flash refused: lyoko_store already exists; prefix-preserving flasher is required"
}
if ($mtd -notmatch 'lyoko-foundation-1\.3-f179') {
    throw "F182 staged promotion requires currently booted F179"
}

$env:OM_Q3_FLASH_ACK = $ack
$env:OM_Q3_FLASH_BUILD_DIR = $build
$env:OM_Q3_FLASH_CANDIDATE = $candidate
$env:OM_Q3_FLASH_BOOTBASE_CONTRACT = Join-Path $build "bootbase-contract.json"
$env:OM_Q3_FLASH_MANIFEST = $manifestPath
$env:OM_Q3_FLASH_INITRAMFS = Join-Path $build ($base + ".kernel.raw.bin")
$env:OM_Q3_FLASH_KCONFIG = Join-Path $build ($base + ".config")
$env:OM_Q3_FLASH_LAYOUT_MODE = "squashfs-split"
$env:OM_Q3_FLASH_ROOTFS_IMAGE = Join-Path $build ($base + ".rootfs.squashfs")
$env:OM_Q3_FLASH_DTB = Join-Path $build ($base + ".dtb")
$env:OM_Q3_FLASH_ROOTFS_OFFSET = "0x180000"
$env:OM_Q3_FLASH_EXPECTED_SHA256 = $sha
$env:OM_Q3_FLASH_EXPECTED_BYTES = [string]$bytes
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $CurrentLiveCrc32.ToLowerInvariant()

$topazLog = Join-Path $root ("outputs\uart-live\f182-uart-topaz-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\reboot_to_topaz_prompt_sysrq.ps1") `
    -Port $Port -LogPath $topazLog -TimeoutSeconds 240
if ($LASTEXITCODE -ne 0) { throw "F182 could not acquire topaz prompt" }

$runner = Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py"
$common = @(
    "--execute", "--ack", $ack, "--port", $Port,
    "--client-ip", $RouterHost, "--host", $RouterHost,
    "--skip-reboot", "--timeout", "1800"
)
& python $runner @common --transport uart-ymodem --uart-attach-topaz
if ($LASTEXITCODE -ne 0) { throw "F182 UART/YMODEM flash failed" }

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$gateDir = Join-Path $root "outputs\postflash\f182-spi-readonly-$stamp"
& python (Join-Path $root "tools\post_flash_f182_spi_probe_gate.py") `
    --host $RouterHost --wait-seconds 300 --output-dir $gateDir
if ($LASTEXITCODE -ne 0) { throw "F182 post-flash SPI gate failed" }
Write-Output "OMF182_FLASH_AND_READONLY_GATE_PASS=1 output=$gateDir"
