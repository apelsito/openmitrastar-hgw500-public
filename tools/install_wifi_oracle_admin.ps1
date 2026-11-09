[CmdletBinding()]
param(
    [string]$PublicKeyUrl = 'http://192.168.1.43:8081/oracle_rsa.pub',
    [string]$UserName = 'omoracle'
)

$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script in an elevated PowerShell window.'
}

$publicKey = (Invoke-RestMethod -Uri $PublicKeyUrl).Trim()
if ($publicKey -notmatch '^ssh-rsa\s+') { throw 'Downloaded RSA public key is invalid.' }

$user = Get-LocalUser -Name $UserName -ErrorAction SilentlyContinue
if (-not $user) {
    $random = ([Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))) + 'Aa1!'
    $secure = ConvertTo-SecureString $random -AsPlainText -Force
    $user = New-LocalUser -Name $UserName -Password $secure -AccountNeverExpires `
        -UserMayNotChangePassword -Description 'OpenMitraStar administrator oracle'
    $random = $null
}
Enable-LocalUser -Name $UserName

$adminGroup = Get-LocalGroup -SID 'S-1-5-32-544'
if (-not (Get-LocalGroupMember -Group $adminGroup.Name -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "\\$([regex]::Escape($UserName))$" })) {
    Add-LocalGroupMember -Group $adminGroup.Name -Member $UserName
}

$keyPath = Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
[IO.File]::WriteAllText($keyPath, $publicKey + "`r`n", [Text.Encoding]::ASCII)
$adminsSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
$systemSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$acl = [Security.AccessControl.FileSecurity]::new()
$acl.SetAccessRuleProtection($true, $false)
$acl.SetOwner($adminsSid)
$acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
    $adminsSid, [Security.AccessControl.FileSystemRights]::FullControl,
    [Security.AccessControl.AccessControlType]::Allow))
$acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
    $systemSid, [Security.AccessControl.FileSystemRights]::FullControl,
    [Security.AccessControl.AccessControlType]::Allow))
Set-Acl -LiteralPath $keyPath -AclObject $acl

$config = Join-Path $env:ProgramData 'ssh\sshd_config'
$text = Get-Content -LiteralPath $config -Raw
$text = [regex]::Replace(
    $text,
    '(?ms)^# OPENMITRASTAR ORACLE BEGIN\r?\n.*?^# OPENMITRASTAR ORACLE END\r?\n?',
    ''
)
$block = @"

# OPENMITRASTAR ORACLE BEGIN
Match User $UserName
       PasswordAuthentication no
       AuthenticationMethods publickey
Match all
# OPENMITRASTAR ORACLE END
"@
[IO.File]::WriteAllText($config, $text.TrimEnd() + "`r`n" + $block, [Text.Encoding]::ASCII)

& "$env:WINDIR\System32\OpenSSH\sshd.exe" -t
if ($LASTEXITCODE -ne 0) { throw 'sshd_config validation failed.' }
Restart-Service sshd

[pscustomobject]@{
    schema = 'openmitrastar.wifi-oracle-admin/v1'
    hostname = $env:COMPUTERNAME
    username = $UserName
    administrators_group = $adminGroup.Name
    administrator = $true
    sshd = (Get-Service sshd).Status.ToString()
    authorized_keys = $keyPath
    password_authentication = $false
} | ConvertTo-Json

