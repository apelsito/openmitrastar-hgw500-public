[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [switch]$AlreadyAtTopaz,
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [ValidateRange(600, 1800)][int]$FlashTimeoutSeconds = 1800
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f222-device-bound"
$base = "openmitrastar-linux510-f222-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
$candidate = Join-Path $build ($base + ".webformat.bin")
$manifestPath = Join-Path $build "manifest.json"
$requiredAck = "OPENMITRASTAR_RESTORE_F222_FROM_F247_AB8F8727"
$expectedSha256 = "ab8f8727f3b1c29a312eddb21f1aa5bc9f474d7be91569f57c9230aaf1fc1c21"
$expectedBytes = 5206016
$currentF247FullSlotSha256 = "ca5a30d69b95425fb834910e964745273e88ba4f5ce33c48b0c72964ed9abeac"
$currentF247FullSlotCrc32 = "71280f5a"

$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant() -ne $expectedSha256 -or
    (Get-Item -LiteralPath $candidate).Length -ne $expectedBytes -or
    $manifest.contracts.bootbase -ne "PASS" -or
    $manifest.package_runtime_fix.signature_verified_before_write -ne $true) {
    throw "known-good F222 rollback artifact mismatch"
}

[ordered]@{
    schema = "openmitrastar.f247-to-f222-rollback-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    from = "F247 full-slot verified image"
    to = "F222 hardware-proven baseline"
    target = "mtd4/linux_live"
    candidate_sha256 = $expectedSha256
    expected_current_full_slot_sha256 = $currentF247FullSlotSha256
    transport = "UART/YMODEM"
    already_at_topaz = $AlreadyAtTopaz.IsPresent
    protected = @("mtd0", "mtd1", "mtd2", "mtd3/linux_safety", "mtd5")
} | ConvertTo-Json -Depth 5

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing rollback: exact -Ack is required" }
if (-not ([IO.Ports.SerialPort]::GetPortNames() -contains $Port)) { throw "UART port $Port is not present" }

$env:OM_Q3_FLASH_ACK = $requiredAck
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
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $currentF247FullSlotCrc32
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = $currentF247FullSlotSha256

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$runDir = Join-Path $root "outputs\recovery\f247-to-f222-$stamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
if (-not $AlreadyAtTopaz) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\reboot_to_topaz_prompt_sysrq.ps1") -Port $Port -LogPath (Join-Path $runDir "uart-to-topaz.log") -TimeoutSeconds 240
    if ($LASTEXITCODE -ne 0) { throw "could not acquire Topaz for F222 rollback" }
}

& python (Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py") --execute --ack $requiredAck --port $Port --client-ip $RouterHost --host $RouterHost --transport uart-ymodem --uart-attach-topaz --skip-reboot --timeout $FlashTimeoutSeconds --erase-bytes 0x5e0000
if ($LASTEXITCODE -ne 0) { throw "F222 rollback flash failed" }

$platformGate = Join-Path $root "outputs\postflash\f222-rollback-$stamp"
& python (Join-Path $root "tools\post_flash_f214_device_gate.py") --host $RouterHost --wait-seconds 360 --output-dir $platformGate --device-dir $build --expected-version lyoko-foundation-3.7-f222-device --known-hosts-name known_hosts.f222
if ($LASTEXITCODE -ne 0) { throw "F222 rollback platform gate failed: $platformGate" }

[ordered]@{
    schema = "openmitrastar.f247-to-f222-rollback/v1"
    status = "PASS"
    target = "mtd4/linux_live"
    restored_sha256 = $expectedSha256
    platform_gate = $platformGate
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDir "status.json") -Encoding ascii
Write-Output "OMF247_ROLLBACK_F222_PASS=1 status=$(Join-Path $runDir 'status.json')"
