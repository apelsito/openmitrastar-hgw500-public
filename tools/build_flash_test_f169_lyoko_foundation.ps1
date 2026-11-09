[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [switch]$SkipBuild,
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$RouterHost = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "468bf351",
    [ValidateSet("auto", "tftp", "uart-ymodem")]
    [string]$Transport = "auto"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $root "work\mission-state\q3-persistent-composite-f169-lyoko-foundation\build"
$base = "openmitrastar-linux510-q3-persistent-f169-lyoko-foundation-LZMA-OFFLINE-NO-FLASH"

if (-not $SkipBuild) {
    & python (Join-Path $root "tools\build_f169_lyoko_foundation_from_f167.py")
    if ($LASTEXITCODE -ne 0) { throw "F169 build failed" }
}

& python -m pytest -q `
    (Join-Path $root "versions\lyoko-foundation-1.0\tests\test_foundation.py") `
    (Join-Path $root "tools\test_f167_emac_ownership_fix.py") `
    (Join-Path $root "tools\test_uart_ymodem_f165_pipeline.py")
if ($LASTEXITCODE -ne 0) { throw "F169 tests failed" }

$manifestPath = Join-Path $build "manifest.json"
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$candidate = Join-Path $build $manifest.artifacts.webformat.file
$sha = [string]$manifest.artifacts.webformat.sha256
$bytes = [long]$manifest.artifacts.webformat.bytes
$ack = "OPENMITRASTAR_Q3_F169_LYOKO_FOUNDATION_FLASH_$($sha.Substring(0,8).ToUpperInvariant())"

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
    transport = $Transport
    tftp_policy = "preferred when Bootbase reaches $ServerIp; UART/YMODEM fallback before erase only"
} | ConvertTo-Json -Depth 4

$runner = Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py"
$preflightTransport = if ($Transport -eq "uart-ymodem") { "uart-ymodem" } else { "tftp" }
if (-not $Execute) {
    & python $runner --port $Port --server-ip $ServerIp --client-ip $RouterHost `
        --host $RouterHost --transport $preflightTransport --timeout 1800
    exit $LASTEXITCODE
}

$common = @(
    "--execute", "--ack", $ack, "--port", $Port,
    "--server-ip", $ServerIp, "--client-ip", $RouterHost,
    "--host", $RouterHost, "--skip-reboot", "--timeout", "1800"
)
$flashed = $false

if ($Transport -in @("auto", "tftp")) {
    $topazLog = Join-Path $root ("outputs\uart-live\f169-auto-topaz-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\reboot_to_topaz_prompt_sysrq.ps1") -Port $Port -LogPath $topazLog -TimeoutSeconds 240
    if ($LASTEXITCODE -ne 0) { throw "could not acquire topaz prompt for TFTP attempt" }
    & python $runner @common --transport tftp
    if ($LASTEXITCODE -eq 0) {
        $flashed = $true
    } elseif ($Transport -eq "tftp") {
        throw "TFTP transport failed"
    } else {
        $latest = Get-ChildItem -LiteralPath $build -Directory -Filter "flash-one-shot-*" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        $transcript = if ($latest) { Join-Path $latest.FullName "bootbase-flash-uart.log" } else { "" }
        if ($transcript -and (Test-Path -LiteralPath $transcript) -and (Select-String -LiteralPath $transcript -SimpleMatch "spi_flash erase" -Quiet)) {
            throw "TFTP failed after erase began; automatic UART fallback refused"
        }
        Write-Host "OMLYOKO_TFTP_UNAVAILABLE_FALLBACK=uart-ymodem flash_writes=0"
        & python $runner @common --transport uart-ymodem --uart-attach-topaz
        if ($LASTEXITCODE -ne 0) { throw "UART/YMODEM fallback failed" }
        $flashed = $true
    }
} else {
    & python $runner @common --transport uart-ymodem
    if ($LASTEXITCODE -ne 0) { throw "UART/YMODEM transport failed" }
    $flashed = $true
}

if (-not $flashed) { throw "F169 was not materialized" }
$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
& python (Join-Path $root "tools\post_flash_f164_squashfs_gate.py") `
    --host $RouterHost --wait-seconds 300 --expected-rootfs-size 00620000 `
    --output-dir (Join-Path $root "outputs\postflash\f169-lyoko-foundation-$stamp")
if ($LASTEXITCODE -ne 0) { throw "F169 post-flash base gate failed" }
