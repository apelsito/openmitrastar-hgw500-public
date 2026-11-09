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
    Filename = 'linux510-w2-2g-parity-tx16-mgmt-reply-split-v1-RAM-TEST-NO-FLASH.bin'
    ExpectedSha256 = '51d2616cb1a54f337fdefce8540ae4d019c9fdd4fc9c20a464377163a133fa5d'
    ExpectedBytes = 4333461
    ExpectedClassification = 'RAM-ONLY-W2-2G-PARITY-TX16-MGMT-REPLY-SPLIT-NO-FLASH'
    ManifestRelativePath = 'work\mission-state\w2-2g-parity-tx16-mgmt-reply-split-v1\build\manifest.json'
    Variant = 'TX16_MGMT_REPLY_SPLIT'
    AckValue = 'OPENMITRASTAR_TX16_RAM_BOOT_ONLY_NO_FLASH'
    Label = 'TX16'
    MarkerPrefix = 'OMTX16'
}
if ($UseSshReboot) { $Params.UseSshReboot = $true }
& $Base @Params
