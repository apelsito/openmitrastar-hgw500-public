[CmdletBinding()]
param(
    [string]$PublicKeyUrl = 'http://192.168.1.43:8081/oracle_ed25519.pub'
)

$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script in an elevated PowerShell window.'
}

$publicKey = (Invoke-RestMethod -Uri $PublicKeyUrl).Trim()
if ($publicKey -notmatch '^ssh-(ed25519|rsa)\s+') { throw 'Downloaded public key is invalid.' }

$path = Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
[IO.File]::WriteAllText($path, $publicKey + "`r`n", [Text.Encoding]::ASCII)

$admins = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
$system = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$acl = [Security.AccessControl.FileSecurity]::new()
$acl.SetAccessRuleProtection($true, $false)
$acl.SetOwner($admins)
$acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
    $admins, [Security.AccessControl.FileSystemRights]::FullControl,
    [Security.AccessControl.AccessControlType]::Allow))
$acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
    $system, [Security.AccessControl.FileSystemRights]::FullControl,
    [Security.AccessControl.AccessControlType]::Allow))
Set-Acl -LiteralPath $path -AclObject $acl

$config = Join-Path $env:ProgramData 'ssh\sshd_config'
if (-not (Test-Path -LiteralPath $config)) { throw "Missing sshd_config: $config" }
$configText = Get-Content -LiteralPath $config -Raw
if ($configText -notmatch '(?im)^Match\s+Group\s+administrators\s*$') {
    Add-Content -LiteralPath $config -Encoding ascii -Value @"

Match Group administrators
       AuthorizedKeysFile __PROGRAMDATA__/ssh/administrators_authorized_keys
"@
}

& "$env:WINDIR\System32\OpenSSH\sshd.exe" -t
if ($LASTEXITCODE -ne 0) { throw 'sshd_config validation failed.' }
Restart-Service sshd

[pscustomobject]@{
    schema = 'openmitrastar.wifi-oracle-key-fix/v1'
    username = $env:USERNAME
    hostname = $env:COMPUTERNAME
    sshd = (Get-Service sshd).Status.ToString()
    authorized_keys = $path
    owner = (Get-Acl -LiteralPath $path).Owner
} | ConvertTo-Json
