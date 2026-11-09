[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [ValidateRange(600, 1800)][int]$FlashTimeoutSeconds = 1800
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f217-device-bound"
$base = "openmitrastar-linux510-f217-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
$candidate = Join-Path $build ($base + ".webformat.bin")
$manifestPath = Join-Path $build "manifest.json"
$ack = "OPENMITRASTAR_Q3_F217_BOOT_SERVICES_FIX_FLASH_2EB8B7BE"
$expectedSha256 = "2eb8b7be3e978e093a9168b45284acb8516edd464a7c0fca13ffc3475746b270"
$expectedBytes = 5201920
$currentF215FullSlotSha256 = "447301a7225a204b14596cce2dca92dee3649d9a66966a095b84d32b1b272ec5"
$currentF215FullSlotCrc32 = "71bcfa11"

if (-not ([IO.Ports.SerialPort]::GetPortNames() -contains $Port)) { throw "UART port $Port is not present" }
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant() -ne $expectedSha256 -or
    (Get-Item -LiteralPath $candidate).Length -ne $expectedBytes -or
    $manifest.contracts.bootbase -ne "PASS" -or
    $manifest.boot_fixes.web_credential -notmatch "normalized") {
    throw "F217 candidate contract mismatch"
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
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $currentF215FullSlotCrc32
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = $currentF215FullSlotSha256

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$runDir = Join-Path $root "outputs\flash-watch\f217-direct-$stamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
[ordered]@{
    schema = "openmitrastar.f217-direct-promotion/v1"
    state = "preflight-pass"
    candidate = $candidate
    candidate_sha256 = $expectedSha256
    candidate_bytes = $expectedBytes
    current_mtd4_crc32 = $currentF215FullSlotCrc32
    expected_mtd4_crc32 = [string]$manifest.artifacts.full_slot.crc32
    target = "mtd4/linux_live"
    erase_bytes = "0x005e0000"
    preserved_store_bytes = "0x001c0000"
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDir "status.json") -Encoding ascii

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    (Join-Path $root "tools\reboot_to_topaz_prompt_sysrq.ps1") `
    -Port $Port -LogPath (Join-Path $runDir "uart-to-topaz.log") -TimeoutSeconds 240
if ($LASTEXITCODE -ne 0) { throw "F217 could not acquire topaz prompt" }

& python (Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py") `
    --execute --ack $ack --port $Port --client-ip $RouterHost --host $RouterHost `
    --transport uart-ymodem --uart-attach-topaz --skip-reboot --timeout $FlashTimeoutSeconds `
    --erase-bytes 0x5e0000
if ($LASTEXITCODE -ne 0) { throw "F217 mtd4 flash failed" }

$gateDir = Join-Path $root "outputs\postflash\f217-device-$stamp"
& python (Join-Path $root "tools\post_flash_f214_device_gate.py") `
    --host $RouterHost --wait-seconds 360 --output-dir $gateDir --device-dir $build `
    --expected-version lyoko-foundation-3.2-f217-device --known-hosts-name known_hosts.f217
if ($LASTEXITCODE -ne 0) { throw "F217 booted but post-flash gate failed: $gateDir" }

[ordered]@{
    schema = "openmitrastar.f217-direct-promotion/v1"
    state = "PASS"
    target = "mtd4/linux_live"
    postflash = $gateDir
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDir "status.json") -Encoding ascii
Write-Output "OMF217_MTD4_FLASH_AND_GATE_PASS=1 status=$(Join-Path $runDir 'status.json')"
