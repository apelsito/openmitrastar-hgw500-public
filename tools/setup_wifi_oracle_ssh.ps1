[CmdletBinding()]
param(
    [string]$ControllerIp = '192.168.1.43',
    [string]$PublicKeyPath = "$PSScriptRoot\oracle_ed25519.pub"
)

$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated PowerShell window.'
}
if (-not (Test-Path -LiteralPath $PublicKeyPath)) {
    throw "Public key not found: $PublicKeyPath"
}

$capability = Get-WindowsCapability -Online | Where-Object {
    $_.Name -like 'OpenSSH.Server*'
} | Select-Object -First 1
if (-not $capability) { throw 'OpenSSH.Server capability is unavailable.' }
if ($capability.State -ne 'Installed') {
    Add-WindowsCapability -Online -Name $capability.Name | Out-Null
}

Set-Service -Name sshd -StartupType Automatic
Start-Service -Name sshd

$ruleName = 'OpenMitraStar WiFi Oracle SSH'
Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort 22 -RemoteAddress $ControllerIp -Profile Any | Out-Null

$isAdministrator = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdministrator) {
    $authorizedKeys = Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
    New-Item -ItemType Directory -Force -Path (Split-Path $authorizedKeys) | Out-Null
} else {
    $authorizedKeys = Join-Path $HOME '.ssh\authorized_keys'
    New-Item -ItemType Directory -Force -Path (Split-Path $authorizedKeys) | Out-Null
}

$publicKey = (Get-Content -LiteralPath $PublicKeyPath -Raw).Trim()
$existing = if (Test-Path -LiteralPath $authorizedKeys) {
    Get-Content -LiteralPath $authorizedKeys -Raw
} else { '' }
if ($existing -notmatch [regex]::Escape($publicKey)) {
    Add-Content -LiteralPath $authorizedKeys -Value $publicKey -Encoding ascii
}

if ($isAdministrator) {
    icacls.exe $authorizedKeys /inheritance:r /grant '*S-1-5-32-544:F' /grant 'SYSTEM:F' | Out-Null
}

$adapters = Get-NetAdapter -Physical | Select-Object Name, InterfaceDescription, Status, MacAddress
$addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '169.254.*' } |
    Select-Object InterfaceAlias, IPAddress, PrefixLength

[pscustomobject]@{
    schema = 'openmitrastar.wifi-oracle-ssh-setup/v1'
    sshd = (Get-Service sshd).Status.ToString()
    controller_ip = $ControllerIp
    username = $env:USERNAME
    hostname = $env:COMPUTERNAME
    authorized_keys = $authorizedKeys
    adapters = @($adapters)
    ipv4 = @($addresses)
} | ConvertTo-Json -Depth 5
