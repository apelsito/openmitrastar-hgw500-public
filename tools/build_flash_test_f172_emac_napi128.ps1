[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [switch]$SkipBuild,
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "d77c9c82"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $root "work\mission-state\q3-persistent-composite-f172-emac-napi128-from-f171\build"
$base = "openmitrastar-linux510-q3-persistent-f172-emac-napi128-from-f171-LZMA-OFFLINE-NO-FLASH"

if (-not $SkipBuild) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\build_f172_emac_napi128.ps1")
    if ($LASTEXITCODE -ne 0) { throw "F172 build failed" }
}

& python -m pytest -q `
    (Join-Path $root "tools\test_f164_squashfs_product.py") `
    (Join-Path $root "tools\test_f165_squashfs_exact_mtd.py") `
    (Join-Path $root "tools\test_f166_emac_telemetry.py") `
    (Join-Path $root "tools\test_f167_emac_ownership_fix.py") `
    (Join-Path $root "tools\test_f170_lyoko_foundation_runtime_fix.py") `
    (Join-Path $root "tools\test_f171_lyoko_foundation_health_fix.py") `
    (Join-Path $root "tools\test_f172_emac_napi128.py") `
    (Join-Path $root "tools\test_uart_ymodem_f165_pipeline.py")
if ($LASTEXITCODE -ne 0) { throw "F172 tests failed" }

$manifestPath = Join-Path $build "manifest.json"
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$candidate = Join-Path $build $manifest.artifacts.webformat.file
$sha = [string]$manifest.artifacts.webformat.sha256
$bytes = [long]$manifest.artifacts.webformat.bytes
$ack = "OPENMITRASTAR_Q3_F172_EMAC_NAPI128_FLASH_$($sha.Substring(0,8).ToUpperInvariant())"

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
    single_variable = $manifest.change_scope.single_variable
    transport = "UART/YMODEM after automated Bootbase acquisition"
    physical_improvement_claimed = $false
} | ConvertTo-Json -Depth 4

if (-not $Execute) { exit 0 }

$topazLog = Join-Path $root ("outputs\uart-live\f172-uart-topaz-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\reboot_to_topaz_prompt_sysrq.ps1") `
    -Port $Port -LogPath $topazLog -TimeoutSeconds 240
if ($LASTEXITCODE -ne 0) { throw "F172 could not acquire topaz prompt" }

$runner = Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py"
$common = @(
    "--execute", "--ack", $ack, "--port", $Port,
    "--client-ip", $RouterHost, "--host", $RouterHost,
    "--skip-reboot", "--timeout", "1800"
)
& python $runner @common --transport uart-ymodem --uart-attach-topaz
if ($LASTEXITCODE -ne 0) { throw "F172 UART/YMODEM transport failed" }

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
& python (Join-Path $root "tools\post_flash_f171_foundation_gate.py") `
    --host $RouterHost --wait-seconds 300 --expected-rootfs-size 00620000 `
    --expected-version lyoko-foundation-1.0-f171 `
    --output-dir (Join-Path $root "outputs\postflash\f172-emac-napi128-$stamp")
if ($LASTEXITCODE -ne 0) { throw "F172 post-flash Foundation gate failed" }

Write-Output "OMF172_BASE_GATE_PASS=1"
Write-Output "OMF172_PHYSICAL_PERFORMANCE=NOT_RUN"
