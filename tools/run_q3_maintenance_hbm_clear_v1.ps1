param(
    [string]$Port = 'COM3',
    [string]$ServerIp = '192.168.1.43',
    [string]$BootClientIp = '192.168.1.200',
    [string]$SshHost = '192.168.1.90',
    [switch]$UseSshReboot,
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$lane = Join-Path $root 'work\mission-state\q3-maintenance-hbm-clear-v1'
$manifestPath = Join-Path $lane 'build\manifest.json'
$filename = 'linux510-q3-maintenance-hbm-clear-v1-RAM-TEST-NO-FLASH.bin'
$image = Join-Path $root "work\tftp\omvl\$filename"
$bootTool = Join-Path $root 'tools\reboot_boot_ramssh.ps1'
$loadAddress = '0x87000000'

if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Missing manifest: $manifestPath" }
if (-not (Test-Path -LiteralPath $image -PathType Leaf)) { throw "Missing image: $image" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$actual = (Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash.ToLowerInvariant()
$declared = [string]$manifest.artifacts.tftp_copy.sha256
$layout = $manifest.ram_layout
if ($actual -ne $declared) { throw "TFTP hash mismatch declared=$declared actual=$actual" }
if ($manifest.flash_supported -ne $false -or $manifest.hardware_actions -ne $false) {
    throw 'HBM clear probe must remain RAM-only/no-flash'
}
if ($layout.safe_offline -ne $true -or $layout.staging.start -ne $loadAddress -or
    $layout.non_overlap.staging_vs_decompressed -ne $true -or
    $layout.non_overlap.staging_vs_lzma_workspace -ne $true -or
    $layout.non_overlap.staging_vs_hbm -ne $true) {
    throw 'RAM layout does not prove staging/image/workspace/HBM separation'
}
$override = $manifest.ram_only_overrides.hbm_clear_probe
if (-not $override -or $override.sha256 -ne 'f3b8b78ffda138c5c8287c923086c51cd896e51539ff7a17caa394c0bc6cebb8') {
    throw 'Instrumented HBM module binding missing'
}

Write-Host "OMQ3_HBM_CLEAR_PREFLIGHT_PASS image_sha256=$actual load=$loadAddress hbm_sha256=$($override.sha256) flash=0"
if (-not $Execute) { exit 0 }

$arguments = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $bootTool,
    '-Port', $Port, '-Filename', $filename, '-ServerIp', $ServerIp,
    '-ClientIp', $BootClientIp, '-SshHost', $SshHost,
    '-LoadAddress', $loadAddress, '-AutonomousEntropy',
    '-ReadyPattern', 'OMSSH_READY port=22'
)
if ($UseSshReboot) { $arguments += '-UseSshReboot' }
& pwsh.exe @arguments
if ($LASTEXITCODE -ne 0) { throw "Q3 HBM-clear RAM boot failed rc=$LASTEXITCODE" }
Write-Host "OMQ3_HBM_CLEAR_RAM_BOOT_PASS image_sha256=$actual load=$loadAddress flash=0"
