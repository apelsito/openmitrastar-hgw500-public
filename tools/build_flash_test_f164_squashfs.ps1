[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [switch]$SkipBuild,
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$RouterHost = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "de140318"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $root "work\mission-state\q3-persistent-composite-f164-squashfs-product\build"
$base = "openmitrastar-linux510-q3-persistent-f164-squashfs-product-LZMA-OFFLINE-NO-FLASH"

if (-not $SkipBuild) {
    & python (Join-Path $root "tools\prepare_f164_squashfs_assets.py")
    if ($LASTEXITCODE -ne 0) { throw "F164 asset build failed" }
    & python (Join-Path $root "tools\compose_f164_squashfs_product.py")
    if ($LASTEXITCODE -ne 0) { throw "F164 image composition failed" }
}
& python -m pytest -q (Join-Path $root "tools\test_f164_squashfs_product.py")
if ($LASTEXITCODE -ne 0) { throw "F164 offline tests failed" }

$manifestPath = Join-Path $build "manifest.json"
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$candidate = Join-Path $build $manifest.artifacts.webformat.file
$sha = [string]$manifest.artifacts.webformat.sha256
$bytes = [long]$manifest.artifacts.webformat.bytes
$ack = "OPENMITRASTAR_Q3_F164_SQUASHFS_MTD4_FLASH_$($sha.Substring(0,8).ToUpperInvariant())"
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant() -ne $sha) { throw "F164 candidate hash mismatch" }
if ((Get-Item -LiteralPath $candidate).Length -ne $bytes) { throw "F164 candidate size mismatch" }
if ($manifest.contracts.bootbase -ne "PASS" -or -not $manifest.contracts.slot_fit) { throw "F164 contracts are not ready" }

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

$summary = [ordered]@{
    mode = if ($Execute) { "execute" } else { "dry-run" }
    candidate = $candidate
    bytes = $bytes
    sha256 = $sha
    current_live_crc32 = $CurrentLiveCrc32
    target = "mtd4/linux_live"
    rollback = "mtd3/linux_safety via UART ATGO"
    rootfs = "SquashFS-XZ read-only at slot offset 0x180000"
}
$summary | ConvertTo-Json -Depth 4
if (-not $Execute) {
    & python (Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py") `
        --port $Port --server-ip $ServerIp --client-ip $RouterHost `
        --host $RouterHost --timeout 900
    exit $LASTEXITCODE
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File (Join-Path $root "tools\q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1") `
    -Execute -Ack $ack -Port $Port -ServerIp $ServerIp -ClientIp $RouterHost `
    -HostAddress $RouterHost -CurrentLiveCrc32 $CurrentLiveCrc32 `
    -BootWaitSeconds 600 -FlashTimeoutSeconds 900 -SshRebootFirst `
    -ConsoleRebootAssist -AllowBlindAutobreak -NoRxAbortSeconds 60 `
    -BlindAtguAfterNoRxSeconds 8
if ($LASTEXITCODE -ne 0) { throw "F164 flash or initial boot failed; use preserved mtd3 rollback" }

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
& python (Join-Path $root "tools\post_flash_f164_squashfs_gate.py") `
    --host $RouterHost --wait-seconds 240 `
    --output-dir (Join-Path $root "outputs\postflash\f164-squashfs-$stamp")
exit $LASTEXITCODE
