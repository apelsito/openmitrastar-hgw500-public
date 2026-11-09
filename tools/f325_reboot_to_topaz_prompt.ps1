[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Port = 'COM3',
    [string]$ExpectedPnpDeviceId = 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000',
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$CandidateSha256,
    [Parameter(Mandatory=$true)][ValidateSet('promote','rollback','fallback')][string]$Direction,
    [Parameter(Mandatory=$true)][string]$LogPath,
    [ValidateRange(10,240)][int]$TimeoutSeconds = 180
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
. (Join-Path $PSScriptRoot 'f325_hardware_context.ps1')
if ($Port -ine 'COM3' -or $ExpectedPnpDeviceId -ine 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000') {
    throw 'F325 reboot target identity mismatch'
}
[void](Assert-F325InheritedPhysicalContext -CandidateSha256 $CandidateSha256 -Direction $Direction)
function Get-F325RebootSource {
    param([string]$SourcePath = (Join-Path $PSScriptRoot 'reboot_to_topaz_prompt_sysrq.ps1'))
    $bytes = [IO.File]::ReadAllBytes($SourcePath)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = -join ($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) }
    finally { $sha.Dispose() }
    if ($hash -cne '4be0f7fec581f3cebdd64d6e428f73363b0a1662f5ade8953580be29c5efc724') {
        throw 'Pinned reboot helper changed; a new review is required'
    }
    $source = [Text.Encoding]::UTF8.GetString($bytes)
    $anchor = "(Join-Path `$PSScriptRoot 'f319_uart_guard.ps1')"
    if ([regex]::Matches($source, [regex]::Escape($anchor)).Count -ne 1) { throw 'Reboot helper context anchor drift' }
    $guardPath = (Join-Path (Split-Path -Parent $SourcePath) 'f319_uart_guard.ps1').Replace("'", "''")
    return $source.Replace($anchor, ("'" + $guardPath + "'"))
}
# Same checked behavior with an explicit guard path, never reset-line pulses.
. ([scriptblock]::Create((Get-F325RebootSource))) -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId -LogPath $LogPath -TimeoutSeconds $TimeoutSeconds
