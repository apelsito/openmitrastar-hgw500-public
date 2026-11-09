[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [switch]$SkipBuild,
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "5123431d"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $root "work\mission-state\q3-persistent-composite-f166-emac-cause-telemetry\build"
$base = "openmitrastar-linux510-q3-persistent-f166-emac-cause-telemetry-LZMA-OFFLINE-NO-FLASH"

if (-not $SkipBuild) {
    & python (Join-Path $root "tools\prepare_f166_emac_telemetry_assets.py")
    if ($LASTEXITCODE -ne 0) { throw "F166 asset build failed" }
    & python (Join-Path $root "tools\compose_f166_emac_telemetry.py")
    if ($LASTEXITCODE -ne 0) { throw "F166 image composition failed" }
}

& python -m pytest -q `
    (Join-Path $root "tools\test_f164_squashfs_product.py") `
    (Join-Path $root "tools\test_f165_squashfs_exact_mtd.py") `
    (Join-Path $root "tools\test_f166_emac_telemetry.py") `
    (Join-Path $root "tools\test_uart_ymodem_f165_pipeline.py")
if ($LASTEXITCODE -ne 0) { throw "F166 tests failed" }

$manifestPath = Join-Path $build "manifest.json"
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$candidate = Join-Path $build $manifest.artifacts.webformat.file
$sha = [string]$manifest.artifacts.webformat.sha256
$bytes = [long]$manifest.artifacts.webformat.bytes
$ack = "OPENMITRASTAR_Q3_F166_EMAC_TELEMETRY_FLASH_$($sha.Substring(0,8).ToUpperInvariant())"

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

[ordered]@{
    mode = if ($Execute) { "execute" } else { "dry-run" }
    candidate = $candidate
    bytes = $bytes
    sha256 = $sha
    candidate_crc32 = $manifest.artifacts.webformat.crc32
    full_slot_crc32 = $manifest.artifacts.full_slot.crc32
    target = "mtd4/linux_live"
    transport = "uart-ymodem"
    behavior_change = "none; read-only EMAC telemetry only"
} | ConvertTo-Json -Depth 4

$arguments = @(
    (Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py"),
    "--port", $Port,
    "--client-ip", $RouterHost,
    "--host", $RouterHost,
    "--transport", "uart-ymodem",
    "--timeout", "1800"
)
if ($Execute) {
    $arguments += @("--execute", "--ack", $ack, "--skip-reboot")
}
& python @arguments
if ($LASTEXITCODE -ne 0) { throw "F166 UART flash pipeline failed" }

if ($Execute) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    & python (Join-Path $root "tools\post_flash_f164_squashfs_gate.py") `
        --host $RouterHost --wait-seconds 300 --expected-rootfs-size 00620000 `
        --output-dir (Join-Path $root "outputs\postflash\f166-emac-telemetry-$stamp")
    if ($LASTEXITCODE -ne 0) { throw "F166 post-flash gate failed" }
}
