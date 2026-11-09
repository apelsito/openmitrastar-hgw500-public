param(
    [string]$Port = 'COM3',
    [string]$ServerIp = '192.168.1.43',
    [string]$BootClientIp = '192.168.1.200',
    [string]$SshHost = '192.168.1.90',
    [switch]$UseSshReboot,
    [switch]$Execute,
    [string]$AckRamOnly = ''
)

$ErrorActionPreference = 'Stop'
$Base = Join-Path $PSScriptRoot 'run_w2_tx12_ram_boot.ps1'
$Params = @{
    Port = $Port
    ServerIp = $ServerIp
    BootClientIp = $BootClientIp
    SshHost = $SshHost
    Execute = $Execute
    AckRamOnly = $AckRamOnly
    Filename = 'linux510-w2-2g-parity-tx13-lossless-mgmt-trace-v1-RAM-TEST-NO-FLASH.bin'
    ExpectedSha256 = '66f9efe41c08c4fecac2b60521b6ec7d37b1390502862dd8cd6e493b6d8239c3'
    ExpectedBytes = 4334366
    ExpectedClassification = 'RAM-ONLY-W2-2G-PARITY-TX13-LOSSLESS-MGMT-TRACE-NO-FLASH'
    ManifestRelativePath = 'work\mission-state\w2-2g-parity-tx13-lossless-mgmt-trace-v1\build\manifest.json'
    Variant = 'TX13_LOSSLESS_MGMT_TRACE'
    AckValue = 'OPENMITRASTAR_TX13_RAM_BOOT_ONLY_NO_FLASH'
    Label = 'TX13'
    MarkerPrefix = 'OMTX13'
}
if ($UseSshReboot) { $Params.UseSshReboot = $true }
& $Base @Params
