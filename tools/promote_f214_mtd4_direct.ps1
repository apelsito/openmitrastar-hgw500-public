[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$RouterHost = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "d77c9c82",
    [ValidateRange(60, 21600)][int]$BootWaitSeconds = 600,
    [ValidateRange(600, 1800)][int]$FlashTimeoutSeconds = 1800
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f214-device-bound"
$base = "openmitrastar-linux510-f214-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
$candidate = Join-Path $build ($base + ".webformat.bin")
$manifestPath = Join-Path $build "manifest.json"
$contractPath = Join-Path $build "bootbase-contract.json"
$expectedSha256 = "14c7daa540e0d9cb4107b36d4e860212e044e392c17746f674369ae847c167b3"
$expectedBytes = 5201920
$expectedCurrentLiveSha256 = "fc7723187b913a89100a21db1b4d4c03d3d489d563418067e66d9476ab8b69bc"
$ack = "OPENMITRASTAR_Q3_F214_DEVICE_FLASH_14C7DAA5"

foreach ($path in @($candidate, $manifestPath, $contractPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing F214 input: $path"
    }
}

$observedSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant()
$observedBytes = (Get-Item -LiteralPath $candidate).Length
if ($observedSha256 -ne $expectedSha256 -or $observedBytes -ne $expectedBytes) {
    throw "F214 candidate hash/size mismatch"
}

$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.artifacts.webformat.sha256 -ne $expectedSha256 -or
    [long]$manifest.artifacts.webformat.bytes -ne $expectedBytes -or
    $manifest.contracts.bootbase -ne "PASS" -or
    $manifest.candidate_eligible -ne $true -or
    $manifest.flash_supported -ne $true) {
    throw "F214 manifest does not authorize this exact candidate"
}

$env:OM_Q3_FLASH_ACK = $ack
$env:OM_Q3_FLASH_BUILD_DIR = $build
$env:OM_Q3_FLASH_CANDIDATE = $candidate
$env:OM_Q3_FLASH_BOOTBASE_CONTRACT = $contractPath
$env:OM_Q3_FLASH_MANIFEST = $manifestPath
$env:OM_Q3_FLASH_INITRAMFS = Join-Path $build ($base + ".kernel.raw.bin")
$env:OM_Q3_FLASH_KCONFIG = Join-Path $build ($base + ".config")
$env:OM_Q3_FLASH_LAYOUT_MODE = "squashfs-split"
$env:OM_Q3_FLASH_ROOTFS_IMAGE = Join-Path $build ($base + ".rootfs.squashfs")
$env:OM_Q3_FLASH_DTB = Join-Path $build ($base + ".dtb")
$env:OM_Q3_FLASH_ROOTFS_OFFSET = "0x180000"
$env:OM_Q3_FLASH_EXPECTED_SHA256 = $expectedSha256
$env:OM_Q3_FLASH_EXPECTED_BYTES = [string]$expectedBytes
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $CurrentLiveCrc32.ToLowerInvariant()
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = $expectedCurrentLiveSha256

$summary = [ordered]@{
    mode = if ($Execute) { "execute" } else { "dry-run" }
    candidate = $candidate
    bytes = $expectedBytes
    sha256 = $expectedSha256
    candidate_crc32 = [string]$manifest.artifacts.webformat.crc32
    full_slot_crc32 = [string]$manifest.artifacts.full_slot.crc32
    full_slot_sha256 = [string]$manifest.artifacts.full_slot.sha256
    current_live_crc32 = $CurrentLiveCrc32.ToLowerInvariant()
    target = "mtd4/linux_live"
    transport = "UART Bootbase + TFTP"
    protected = @("mtd0", "mtd1", "mtd2", "mtd3", "mtd5")
    recovery_dependency = "none; host-side F170 restore remains available"
}
$summary | ConvertTo-Json -Depth 4

$runner = Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py"
if (-not $Execute) {
    & python $runner --port $Port --server-ip $ServerIp --client-ip $RouterHost --host $RouterHost --timeout $FlashTimeoutSeconds
    exit $LASTEXITCODE
}

if (-not ([IO.Ports.SerialPort]::GetPortNames() -contains $Port)) {
    throw "UART port $Port is not present"
}
if (-not (Test-NetConnection -ComputerName $RouterHost -Port 22 -InformationLevel Quiet -WarningAction SilentlyContinue)) {
    throw "Router SSH is not reachable at $RouterHost before promotion"
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    (Join-Path $root "tools\q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1") `
    -Execute -Ack $ack -Port $Port -ServerIp $ServerIp -ClientIp $RouterHost -HostAddress $RouterHost `
    -CurrentLiveCrc32 $CurrentLiveCrc32 -BootWaitSeconds $BootWaitSeconds `
    -FlashTimeoutSeconds $FlashTimeoutSeconds -SshRebootFirst -ConsoleRebootAssist `
    -AllowBlindAutobreak -NoRxAbortSeconds 60 -BlindAtguAfterNoRxSeconds 8
if ($LASTEXITCODE -ne 0) { throw "F214 mtd4 flash failed" }

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$gateDir = Join-Path $root "outputs\postflash\f214-device-$stamp"
& python (Join-Path $root "tools\post_flash_f214_device_gate.py") `
    --host $RouterHost --wait-seconds 360 --output-dir $gateDir --device-dir $build
if ($LASTEXITCODE -ne 0) { throw "F214 booted but post-flash gate failed: $gateDir" }

Write-Output "OMF214_MTD4_FLASH_AND_GATE_PASS=1 output=$gateDir"
