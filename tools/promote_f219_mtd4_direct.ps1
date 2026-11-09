[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [ValidateRange(600, 1800)][int]$FlashTimeoutSeconds = 1800
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f219-device-bound"
$base = "openmitrastar-linux510-f219-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
$candidate = Join-Path $build ($base + ".webformat.bin")
$manifestPath = Join-Path $build "manifest.json"
$ack = "OPENMITRASTAR_Q3_F219_CGI_PERMISSIONS_FLASH_E8468C7D"
$expectedSha256 = "e8468c7dae8ab774355a8650ac9d4ac52faa54061220d918aba360b3f0928bb1"
$expectedBytes = 5201920
$currentF218FullSlotSha256 = "716c4187dd4858381df30c5bcb90afcc401392c39e4ba19e7210d520d98800ef"
$currentF218FullSlotCrc32 = "7f1c2e0c"

if (-not ([IO.Ports.SerialPort]::GetPortNames() -contains $Port)) { throw "UART port $Port is not present" }
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant() -ne $expectedSha256 -or
    (Get-Item -LiteralPath $candidate).Length -ne $expectedBytes -or
    $manifest.contracts.bootbase -ne "PASS" -or
    $manifest.web_security.top_level_cgi_mode -ne "0755") {
    throw "F219 candidate contract mismatch"
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
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $currentF218FullSlotCrc32
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = $currentF218FullSlotSha256

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$runDir = Join-Path $root "outputs\flash-watch\f219-direct-$stamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    (Join-Path $root "tools\reboot_to_topaz_prompt_sysrq.ps1") `
    -Port $Port -LogPath (Join-Path $runDir "uart-to-topaz.log") -TimeoutSeconds 240
if ($LASTEXITCODE -ne 0) { throw "F219 could not acquire topaz prompt" }

& python (Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py") `
    --execute --ack $ack --port $Port --client-ip $RouterHost --host $RouterHost `
    --transport uart-ymodem --uart-attach-topaz --skip-reboot --timeout $FlashTimeoutSeconds `
    --erase-bytes 0x5e0000
if ($LASTEXITCODE -ne 0) { throw "F219 mtd4 flash failed" }

$gateDir = Join-Path $root "outputs\postflash\f219-device-$stamp"
& python (Join-Path $root "tools\post_flash_f214_device_gate.py") `
    --host $RouterHost --wait-seconds 360 --output-dir $gateDir --device-dir $build `
    --expected-version lyoko-foundation-3.4-f219-device --known-hosts-name known_hosts.f219
if ($LASTEXITCODE -ne 0) { throw "F219 booted but post-flash gate failed: $gateDir" }

[ordered]@{
    schema = "openmitrastar.f219-direct-promotion/v1"
    state = "PASS"
    target = "mtd4/linux_live"
    candidate_sha256 = $expectedSha256
    full_slot_crc32 = [string]$manifest.artifacts.full_slot.crc32
    erase_bytes = "0x005e0000"
    preserved_store_bytes = "0x001c0000"
    postflash = $gateDir
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDir "status.json") -Encoding ascii
Write-Output "OMF219_MTD4_FLASH_AND_GATE_PASS=1 status=$(Join-Path $runDir 'status.json')"
