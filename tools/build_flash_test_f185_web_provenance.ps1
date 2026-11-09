[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [switch]$SkipBuild,
    [switch]$RunWifiCampaign,
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "d77c9c82"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $root "work\mission-state\q3-persistent-composite-f185-web-provenance-from-f184\build"
$base = "openmitrastar-linux510-q3-persistent-f185-web-provenance-from-f184-LZMA-OFFLINE-NO-FLASH"

if (-not $SkipBuild) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\build_f185_web_provenance.ps1")
    if ($LASTEXITCODE -ne 0) { throw "F185 build failed" }
}

$manifestPath = Join-Path $build "manifest.json"
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$candidate = Join-Path $build $manifest.artifacts.webformat.file
$sha = [string]$manifest.artifacts.webformat.sha256
$bytes = [long]$manifest.artifacts.webformat.bytes
$ack = "OPENMITRASTAR_Q3_F185_WEB_PROVENANCE_FLASH_$($sha.Substring(0,8).ToUpperInvariant())"

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
    acknowledgement = $ack
    candidate_crc32 = $manifest.artifacts.webformat.crc32
    full_slot_crc32 = $manifest.artifacts.full_slot.crc32
    current_live_crc32 = $CurrentLiveCrc32.ToLowerInvariant()
    target = "mtd4/linux_live"
    transport = "UART/YMODEM after automated Bootbase acquisition"
    postflash = "Foundation 1.5 identity + accessibility + F184 integrated gate"
    wifi_campaign = $RunWifiCampaign.IsPresent
} | ConvertTo-Json -Depth 4

if (-not $Execute) { exit 0 }

$topazLog = Join-Path $root ("outputs\uart-live\f185-uart-topaz-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\reboot_to_topaz_prompt_sysrq.ps1") `
    -Port $Port -LogPath $topazLog -TimeoutSeconds 240
if ($LASTEXITCODE -ne 0) { throw "F185 could not acquire topaz prompt" }

$runner = Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py"
$common = @(
    "--execute", "--ack", $ack, "--port", $Port,
    "--client-ip", $RouterHost, "--host", $RouterHost,
    "--skip-reboot", "--timeout", "1800"
)
& python $runner @common --transport uart-ymodem --uart-attach-topaz
if ($LASTEXITCODE -ne 0) { throw "F185 UART/YMODEM flash failed" }

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$gateDir = Join-Path $root "outputs\postflash\f185-web-provenance-$stamp"
& python (Join-Path $root "tools\post_flash_f185_web_provenance_gate.py") `
    --host $RouterHost --wait-seconds 300 --output-dir $gateDir
if ($LASTEXITCODE -ne 0) { throw "F185 post-flash web provenance gate failed" }

if ($RunWifiCampaign) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\run_f172_physical_campaign.ps1") `
        -Execute -Ack OPENMITRASTAR_F172_PHYSICAL_CAMPAIGN -RouterHost $RouterHost
    if ($LASTEXITCODE -ne 0) { throw "F185 physical Wi-Fi campaign failed" }
}

Write-Output "OMF185_FLASH_AND_GATE_PASS=1 output=$gateDir"
