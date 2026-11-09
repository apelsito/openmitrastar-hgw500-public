[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [ValidateRange(600, 1800)][int]$FlashTimeoutSeconds = 1800
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f223-device-bound"
$base = "openmitrastar-linux510-f223-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
$candidate = Join-Path $build ($base + ".webformat.bin")
$manifestPath = Join-Path $build "manifest.json"
$requiredAck = "OPENMITRASTAR_F223_RXRING256_A63CCCE6"
$expectedSha256 = "a63ccce69776732269ac4c08f29062c74b93eda945c88778ab63efd9215be2bc"
$expectedBytes = 5206016
$currentF222FullSlotSha256 = "b173f3876adf3e82a4b0c9606db202b4db0f8b98bcc2bfff13dfacfec23464c0"
$currentF222FullSlotCrc32 = "82479333"

$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant() -ne $expectedSha256 -or
    (Get-Item -LiteralPath $candidate).Length -ne $expectedBytes -or
    $manifest.schema -ne "openmitrastar.f223-emac-rxring256-from-f222/v1" -or
    $manifest.contracts.bootbase -ne "PASS" -or
    $manifest.binary_contract.result -ne "PASS" -or
    $manifest.binary_contract.rx_ring_descriptors -ne 256 -or
    $manifest.binary_contract.napi_weight -ne 128) {
    throw "F223 candidate contract mismatch"
}

[ordered]@{
    mode = if ($Execute) { "execute" } else { "dry-run" }
    target = "mtd4/linux_live"
    candidate = $candidate
    bytes = $expectedBytes
    sha256 = $expectedSha256
    full_slot_crc32 = $manifest.artifacts.full_slot.crc32
    erase_bytes = "0x005e0000"
    preserved_store_bytes = "0x001c0000"
    single_variable = $manifest.change_scope.single_variable
} | ConvertTo-Json -Depth 4

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing flash: exact -Ack is required" }
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
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $currentF222FullSlotCrc32
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = $currentF222FullSlotSha256

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$runDir = Join-Path $root "outputs\flash-watch\f223-direct-$stamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\reboot_to_topaz_prompt_sysrq.ps1") `
    -Port $Port -LogPath (Join-Path $runDir "uart-to-topaz.log") -TimeoutSeconds 240
if ($LASTEXITCODE -ne 0) { throw "F223 could not acquire topaz prompt" }

& python (Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py") `
    --execute --ack $requiredAck --port $Port --client-ip $RouterHost --host $RouterHost `
    --transport uart-ymodem --uart-attach-topaz --skip-reboot --timeout $FlashTimeoutSeconds `
    --erase-bytes 0x5e0000
if ($LASTEXITCODE -ne 0) { throw "F223 mtd4 flash failed" }

$platformGate = Join-Path $root "outputs\postflash\f223-device-$stamp"
& python (Join-Path $root "tools\post_flash_f214_device_gate.py") `
    --host $RouterHost --wait-seconds 360 --output-dir $platformGate --device-dir $build `
    --expected-version lyoko-foundation-3.7-f222-device --known-hosts-name known_hosts.f223
if ($LASTEXITCODE -ne 0) { throw "F223 platform gate failed: $platformGate" }

$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$probe = & $ssh -i "$env:USERPROFILE\.ssh\id_ed25519" -o IdentitiesOnly=yes -o BatchMode=yes `
    -o ConnectTimeout=8 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$(Join-Path $build 'known_hosts.f223')" -o LogLevel=ERROR `
    "root@$RouterHost" 'grep "^napi_weight=128$" /sys/bus/platform/devices/e8000000.ethernet/lyoko_emac_stats; dmesg | grep "descriptor DDR" | tail -1'
if ($LASTEXITCODE -ne 0 -or ($probe -notcontains "napi_weight=128") -or -not ($probe -match "tx=1024 rx=4096")) {
    throw "F223 live RX-ring contract failed"
}

[ordered]@{
    schema = "openmitrastar.f223-direct-promotion/v1"
    status = "PASS"
    target = "mtd4/linux_live"
    candidate_sha256 = $expectedSha256
    full_slot_crc32 = [string]$manifest.artifacts.full_slot.crc32
    erase_bytes = "0x005e0000"
    preserved_store_bytes = "0x001c0000"
    platform_gate = $platformGate
    physical_campaign = "NOT_RUN"
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDir "status.json") -Encoding ascii

Write-Output "OMF223_MTD4_FLASH_GATE_PASS=1 status=$(Join-Path $runDir 'status.json')"
