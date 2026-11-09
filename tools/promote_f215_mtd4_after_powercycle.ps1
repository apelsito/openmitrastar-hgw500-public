[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [ValidateRange(60, 21600)][int]$BootWaitSeconds = 1800,
    [ValidateRange(600, 1800)][int]$FlashTimeoutSeconds = 1800
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f215-device-bound"
$base = "openmitrastar-linux510-f215-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
$candidate = Join-Path $build ($base + ".webformat.bin")
$manifestPath = Join-Path $build "manifest.json"
$ack = "OPENMITRASTAR_Q3_F215_SPI_PROBE_DISABLED_FLASH_2F660934"
$expectedSha256 = "2f660934f258810642c605244b7d93fd9c0736f3c47f143b7b08431b013e3c6a"
$expectedBytes = 5201920
$currentF214FullSlotSha256 = "e046f606e9d833acb28c0f17b9aff711fc82d030809025a390866c9e0db2d819"
$currentF214FullSlotCrc32 = "7c9a60f2"

if (-not ([IO.Ports.SerialPort]::GetPortNames() -contains $Port)) {
    throw "UART port $Port is not present"
}
foreach ($path in @($candidate, $manifestPath, (Join-Path $build "bootbase-contract.json"))) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing F215 input: $path" }
}
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant() -ne $expectedSha256 -or
    (Get-Item -LiteralPath $candidate).Length -ne $expectedBytes -or
    $manifest.contracts.bootbase -ne "PASS" -or
    $manifest.spi_probe.boot_state -ne "disabled") {
    throw "F215 candidate contract mismatch"
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
$env:OM_Q3_FLASH_EXPECTED_SHA256 = $expectedSha256
$env:OM_Q3_FLASH_EXPECTED_BYTES = [string]$expectedBytes
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $currentF214FullSlotCrc32
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = $currentF214FullSlotSha256

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$watchDir = Join-Path $root "outputs\flash-watch\f215-after-f214-$stamp"
New-Item -ItemType Directory -Force -Path $watchDir | Out-Null
$statusPath = Join-Path $watchDir "status.json"
[ordered]@{
    schema = "openmitrastar.f215-powercycle-promotion/v1"
    state = "armed_waiting_for_powercycle"
    candidate = $candidate
    candidate_sha256 = $expectedSha256
    candidate_bytes = $expectedBytes
    current_mtd4_crc32 = $currentF214FullSlotCrc32
    expected_mtd4_crc32 = [string]$manifest.artifacts.full_slot.crc32
    write_target = "mtd4/linux_live"
    erase_bytes = "0x005e0000"
    preserved_store_bytes = "0x001c0000"
    transport = "UART/YMODEM"
    protected = @("mtd0", "mtd1", "mtd2", "mtd3", "mtd5")
    output_dir = $watchDir
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statusPath -Encoding ascii

Write-Output "OMF215_WAIT_POWER_CYCLE_ARMED=1 status=$statusPath"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    (Join-Path $root "tools\reboot_to_topaz_prompt_sysrq.ps1") `
    -Port $Port -LogPath (Join-Path $watchDir "uart-to-topaz.log") `
    -TimeoutSeconds $BootWaitSeconds -NoReboot
if ($LASTEXITCODE -ne 0) { throw "F215 did not acquire topaz prompt" }

[ordered]@{
    schema = "openmitrastar.f215-powercycle-promotion/v1"
    state = "topaz-acquired"
    output_dir = $watchDir
} | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $statusPath -Encoding ascii

& python (Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py") `
    --execute --ack $ack --port $Port --client-ip $RouterHost --host $RouterHost `
    --transport uart-ymodem --uart-attach-topaz --skip-reboot --timeout $FlashTimeoutSeconds `
    --erase-bytes 0x5e0000
if ($LASTEXITCODE -ne 0) { throw "F215 mtd4 flash failed" }

$gateDir = Join-Path $root "outputs\postflash\f215-device-$stamp"
& python (Join-Path $root "tools\post_flash_f214_device_gate.py") `
    --host $RouterHost --wait-seconds 360 --output-dir $gateDir --device-dir $build `
    --expected-version lyoko-foundation-3.1-f215-device
if ($LASTEXITCODE -ne 0) { throw "F215 booted but post-flash gate failed: $gateDir" }

[ordered]@{
    schema = "openmitrastar.f215-powercycle-promotion/v1"
    state = "PASS"
    write_target = "mtd4/linux_live"
    flash_evidence = $build
    postflash = $gateDir
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statusPath -Encoding ascii
Write-Output "OMF215_MTD4_FLASH_AND_GATE_PASS=1 status=$statusPath"
