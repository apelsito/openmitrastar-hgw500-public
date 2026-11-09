[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "4046c935",
    [ValidateRange(60, 21600)]
    [int]$BootWaitSeconds = 600,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $root "work\mission-state\q3-persistent-composite-f152-5g-inactivity-trace-from-f151\build"
$base = "openmitrastar-linux510-q3-persistent-f152-5g-inactivity-trace-from-f151-LZMA-OFFLINE-NO-FLASH"
$ack = "OPENMITRASTAR_Q3_F152_5G_INACTIVITY_TRACE_FROM_F151_MTD4_FLASH_6CD3496C"
$expectedSha256 = "6cd3496cc2d8148396f7a143516eceb65b6480c544f9f770d7ad616292466612"
$expectedBytes = 4375104

$candidate = Join-Path $build ($base + ".webformat.bin")
$env:OM_Q3_FLASH_ACK = $ack
$env:OM_Q3_FLASH_BUILD_DIR = $build
$env:OM_Q3_FLASH_CANDIDATE = $candidate
$env:OM_Q3_FLASH_BOOTBASE_CONTRACT = Join-Path $build "bootbase-contract.json"
$env:OM_Q3_FLASH_MANIFEST = Join-Path $build "manifest.json"
$env:OM_Q3_FLASH_INITRAMFS = Join-Path $build ($base + ".decompressed.bin")
$env:OM_Q3_FLASH_KCONFIG = Join-Path $build ($base + ".config")
$env:OM_Q3_FLASH_EXPECTED_SHA256 = $expectedSha256
$env:OM_Q3_FLASH_EXPECTED_BYTES = [string]$expectedBytes
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $CurrentLiveCrc32.ToLowerInvariant()

if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "Missing F152 candidate: $candidate" }
$actualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant()
$actualBytes = (Get-Item -LiteralPath $candidate).Length
if ($actualSha256 -ne $expectedSha256 -or $actualBytes -ne $expectedBytes) {
    throw "F152 candidate hash/size mismatch"
}

if (-not $Execute) {
    & python (Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py") `
        --port $Port --server-ip $ServerIp --client-ip $ClientIp `
        --host $HostAddress --timeout $FlashTimeoutSeconds
    exit $LASTEXITCODE
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File (Join-Path $root "tools\q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1") `
    -Execute -Ack $ack -Port $Port -ServerIp $ServerIp -ClientIp $ClientIp `
    -HostAddress $HostAddress -CurrentLiveCrc32 $CurrentLiveCrc32 `
    -BootWaitSeconds $BootWaitSeconds -FlashTimeoutSeconds $FlashTimeoutSeconds `
    -SshRebootFirst -ConsoleRebootAssist -AllowBlindAutobreak `
    -NoRxAbortSeconds 60 -BlindAtguAfterNoRxSeconds 8
exit $LASTEXITCODE
