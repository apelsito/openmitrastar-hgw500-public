[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [ValidateRange(600, 1800)][int]$FlashTimeoutSeconds = 1800
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f220-device-bound"
$base = "openmitrastar-linux510-f220-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
$candidate = Join-Path $build ($base + ".webformat.bin")
$manifestPath = Join-Path $build "manifest.json"
$ack = "OPENMITRASTAR_Q3_F220_PKGBOX_WC_FLASH_ED110858"
$expectedSha256 = "ed11085896453b031153f092a1188de7e9cbd6e977b45ede0e3d53c974998e78"
$expectedBytes = 5201920
$currentF219FullSlotSha256 = "6b16c18888c31efcb19f44b91e0c38c51212b40e717d38c22ce2f382e6cbaed2"
$currentF219FullSlotCrc32 = "18399a03"

if (-not ([IO.Ports.SerialPort]::GetPortNames() -contains $Port)) { throw "UART port $Port is not present" }
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant() -ne $expectedSha256 -or
    (Get-Item -LiteralPath $candidate).Length -ne $expectedBytes -or
    $manifest.contracts.bootbase -ne "PASS" -or
    $manifest.package_runtime_fix.added_applet -ne "wc") {
    throw "F220 candidate contract mismatch"
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
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $currentF219FullSlotCrc32
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = $currentF219FullSlotSha256

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$runDir = Join-Path $root "outputs\flash-watch\f220-direct-$stamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    (Join-Path $root "tools\reboot_to_topaz_prompt_sysrq.ps1") `
    -Port $Port -LogPath (Join-Path $runDir "uart-to-topaz.log") -TimeoutSeconds 240
if ($LASTEXITCODE -ne 0) { throw "F220 could not acquire topaz prompt" }

& python (Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py") `
    --execute --ack $ack --port $Port --client-ip $RouterHost --host $RouterHost `
    --transport uart-ymodem --uart-attach-topaz --skip-reboot --timeout $FlashTimeoutSeconds `
    --erase-bytes 0x5e0000
if ($LASTEXITCODE -ne 0) { throw "F220 mtd4 flash failed" }

$platformGate = Join-Path $root "outputs\postflash\f220-device-$stamp"
& python (Join-Path $root "tools\post_flash_f214_device_gate.py") `
    --host $RouterHost --wait-seconds 360 --output-dir $platformGate --device-dir $build `
    --expected-version lyoko-foundation-3.5-f220-device --known-hosts-name known_hosts.f220
if ($LASTEXITCODE -ne 0) { throw "F220 platform gate failed: $platformGate" }

$packageGate = Join-Path $root "outputs\postflash\f220-packages-$stamp"
& python (Join-Path $root "tools\post_flash_f219_package_gate.py") `
    --host $RouterHost --output-dir $packageGate --known-hosts (Join-Path $build "known_hosts.f220") `
    --expected-version lyoko-foundation-3.5-f220-device
if ($LASTEXITCODE -ne 0) { throw "F220 package gate failed: $packageGate" }

[ordered]@{
    schema = "openmitrastar.f220-direct-promotion/v1"
    state = "PASS"
    target = "mtd4/linux_live"
    candidate_sha256 = $expectedSha256
    full_slot_crc32 = [string]$manifest.artifacts.full_slot.crc32
    erase_bytes = "0x005e0000"
    preserved_store_bytes = "0x001c0000"
    platform_gate = $platformGate
    package_gate = $packageGate
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDir "status.json") -Encoding ascii
Write-Output "OMF220_MTD4_FLASH_AND_GATES_PASS=1 status=$(Join-Path $runDir 'status.json')"
