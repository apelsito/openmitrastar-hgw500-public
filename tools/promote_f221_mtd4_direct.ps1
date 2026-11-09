[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [ValidateRange(600, 1800)][int]$FlashTimeoutSeconds = 1800
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f221-device-bound"
$base = "openmitrastar-linux510-f221-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
$candidate = Join-Path $build ($base + ".webformat.bin")
$manifestPath = Join-Path $build "manifest.json"
$ack = "OPENMITRASTAR_Q3_F221_PKGBOX_MULTICALL_FLASH_D2EE7241"
$expectedSha256 = "d2ee724161881375a6dfdbb991c3195d5548c0a2ff7a612ddb204c197be4b665"
$expectedBytes = 5206016
$currentF220FullSlotSha256 = "250b7febd07eeb8f329f4600b9f0f42553f8f0b97cce7f4cb29837865495f97d"
$currentF220FullSlotCrc32 = "c694ff31"

if (-not ([IO.Ports.SerialPort]::GetPortNames() -contains $Port)) { throw "UART port $Port is not present" }
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant() -ne $expectedSha256 -or
    (Get-Item -LiteralPath $candidate).Length -ne $expectedBytes -or
    $manifest.contracts.bootbase -ne "PASS" -or
    $manifest.package_runtime_fix.multicall_dispatcher -ne $true) {
    throw "F221 candidate contract mismatch"
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
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $currentF220FullSlotCrc32
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = $currentF220FullSlotSha256

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$runDir = Join-Path $root "outputs\flash-watch\f221-direct-$stamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    (Join-Path $root "tools\reboot_to_topaz_prompt_sysrq.ps1") `
    -Port $Port -LogPath (Join-Path $runDir "uart-to-topaz.log") -TimeoutSeconds 240
if ($LASTEXITCODE -ne 0) { throw "F221 could not acquire topaz prompt" }

& python (Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py") `
    --execute --ack $ack --port $Port --client-ip $RouterHost --host $RouterHost `
    --transport uart-ymodem --uart-attach-topaz --skip-reboot --timeout $FlashTimeoutSeconds `
    --erase-bytes 0x5e0000
if ($LASTEXITCODE -ne 0) { throw "F221 mtd4 flash failed" }

$deadline = (Get-Date).AddSeconds(240)
$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$knownHosts = Join-Path $build "known_hosts.f221"
do {
    Start-Sleep -Seconds 5
    $ready = & $ssh -i "$env:USERPROFILE\.ssh\id_ed25519" -o IdentitiesOnly=yes -o BatchMode=yes `
        -o ConnectTimeout=8 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$knownHosts" -o LogLevel=ERROR `
        "root@$RouterHost" 'printf "%s/%s" "$(cat /run/openmitrastar/boot-state 2>/dev/null)" "$(cat /run/openmitrastar/radio5g/state 2>/dev/null)"' 2>$null
} while (($ready -ne "ready/ready") -and (Get-Date -lt $deadline))
if ($ready -ne "ready/ready") { throw "F221 did not converge to ready/ready" }

$platformGate = Join-Path $root "outputs\postflash\f221-device-$stamp"
& python (Join-Path $root "tools\post_flash_f214_device_gate.py") `
    --host $RouterHost --wait-seconds 360 --output-dir $platformGate --device-dir $build `
    --expected-version lyoko-foundation-3.6-f221-device --known-hosts-name known_hosts.f221
if ($LASTEXITCODE -ne 0) { throw "F221 platform gate failed: $platformGate" }

$packageGate = Join-Path $root "outputs\postflash\f221-packages-$stamp"
& python (Join-Path $root "tools\post_flash_f219_package_gate.py") `
    --host $RouterHost --output-dir $packageGate --known-hosts (Join-Path $build "known_hosts.f221") `
    --expected-version lyoko-foundation-3.6-f221-device
if ($LASTEXITCODE -ne 0) { throw "F221 package gate failed: $packageGate" }

[ordered]@{
    schema = "openmitrastar.f221-direct-promotion/v1"
    state = "PASS"
    target = "mtd4/linux_live"
    candidate_sha256 = $expectedSha256
    full_slot_crc32 = [string]$manifest.artifacts.full_slot.crc32
    erase_bytes = "0x005e0000"
    preserved_store_bytes = "0x001c0000"
    platform_gate = $platformGate
    package_gate = $packageGate
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDir "status.json") -Encoding ascii
Write-Output "OMF221_MTD4_FLASH_AND_GATES_PASS=1 status=$(Join-Path $runDir 'status.json')"
