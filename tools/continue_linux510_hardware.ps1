param(
    [string]$Port = "COM3",
    [string]$Image = "linux510-emac-ddr-sysrq-webformat.bin"
)

$ErrorActionPreference = "Stop"
$tools = $PSScriptRoot
& (Join-Path $tools "recover_to_oem_safety.ps1") -Port $Port -TimeoutSeconds 300 -NoBoot
& (Join-Path $tools "boot_linux510_tftp.ps1") -Port $Port -Filename $Image -VerifySsh
