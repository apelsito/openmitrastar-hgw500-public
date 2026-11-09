# Reuse the reviewed F321 backend byte-for-byte except its exact image table.
param(
    [switch]$Execute, [string]$Ack = '',
    [Parameter(Mandatory=$true)][string]$Candidate,
    [Parameter(Mandatory=$true)][string]$ExpectedSha256,
    [Parameter(Mandatory=$true)][long]$ExpectedBytes,
    [string]$Port = 'COM3', [string]$ServerIp = '192.168.1.43',
    [string]$ClientIp = '192.168.1.90', [string]$HostAddress = '192.168.1.90',
    [Parameter(Mandatory=$true)][string]$Transcript,
    [Parameter(Mandatory=$true)][string]$RollbackSha256,
    [Parameter(Mandatory=$true)][string]$ProtectedMtd0Sha256,
    [Parameter(Mandatory=$true)][string]$ProtectedMtd1Sha256,
    [Parameter(Mandatory=$true)][string]$ProtectedMtd2Sha256,
    [Parameter(Mandatory=$true)][string]$ProtectedMtd5Sha256,
    [Parameter(Mandatory=$true)][string]$ProtectedMtd0Crc32,
    [Parameter(Mandatory=$true)][string]$ProtectedMtd1Crc32,
    [Parameter(Mandatory=$true)][string]$ProtectedMtd2Crc32,
    [Parameter(Mandatory=$true)][string]$ProtectedMtd5Crc32,
    [Parameter(Mandatory=$true)][string]$RollbackCrc32,
    [Parameter(Mandatory=$true)][string]$CurrentLiveCrc32,
    [Parameter(Mandatory=$true)][string]$ExpectedCandidateCrc32,
    [Parameter(Mandatory=$true)][string]$ExpectedFullSlotSha256,
    [Parameter(Mandatory=$true)][string]$ExpectedFullSlotCrc32,
    [long]$EraseBytes = 0x007a0000,
    [ValidateRange(600,1800)][int]$TimeoutSeconds = 900,
    [switch]$SkipReboot, [switch]$SkipNetworkTransfer, [switch]$SkipBootbasePing,
    [switch]$RequireProductReady,
    [ValidatePattern('^(|[0-9a-f]{32})$')][string]$AttemptId = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-F322BackendSource {
    param([string]$SourcePath = (Join-Path $PSScriptRoot 'f321_mtd4_bootbase_flash.ps1'))
    # Hash and transform the same byte buffer; never read it again after checking.
    $bytes = [IO.File]::ReadAllBytes($SourcePath)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = -join ($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) }
    finally { $sha.Dispose() }
    if ($hash -cne '017032af5357afc7798d49d77529ef599a645f1f1b6aa54a94e1740907a8345f') {
        throw 'Corrected F321 backend source drift; F322 requires a new reviewed adapter'
    }
    $source = [Text.Encoding]::UTF8.GetString($bytes).Replace("`r`n", "`n")
    $old = @'
$allowed = @{
    'eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18' = @('OPENMITRASTAR_F321_MTD4_EB8E23AC',5337088,'d6b13baa','6ed8e483')
    'a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11' = @('OPENMITRASTAR_F321_ROLLBACK_TO_F314_A0C7350A',5292032,'6ed8e483','d6b13baa')
}
'@
    $new = @'
$allowed = @{
    '55145f55f904beb342dd67b39578a79fbc8a4d0bc68bae944402cab80e5f7f1a' = @('OPENMITRASTAR_F322_MTD4_55145F55_UNARMED',5320704,'6ed8e483','1f34e4df')
    'eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18' = @('OPENMITRASTAR_F322_RESTORE_F321_EB8E23AC',5337088,'1f34e4df','6ed8e483')
    'a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11' = @('OPENMITRASTAR_F322_FALLBACK_F314_A0C7350A',5292032,'1f34e4df','d6b13baa')
}
'@
    $old = $old.Replace("`r`n", "`n"); $new = $new.Replace("`r`n", "`n")
    if ([regex]::Matches($source, [regex]::Escape($old)).Count -ne 1) { throw 'Exact F321 image table not found once' }
    return $source.Replace($old, $new)
}

if ($env:OM_Q3_FLASH_EXPECTED_SHA256 -cne $ExpectedSha256 -or
    [string]$env:OM_Q3_FLASH_EXPECTED_BYTES -cne [string]$ExpectedBytes -or
    ($Execute -and $env:OM_Q3_FLASH_ACK -cne $Ack)) {
    throw 'F322 environment and explicitly supplied image/ACK differ'
}
$source = Get-F322BackendSource
# dot-source preserves the script's PSScriptRoot for the unchanged backend.
. ([scriptblock]::Create($source)) @PSBoundParameters
