[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$CandidateSha256,
    [Parameter(Mandatory=$true)][ValidateSet('promote','rollback','fallback')][string]$Direction
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
. (Join-Path $PSScriptRoot 'f325_hardware_context.ps1')
[void](Assert-F325InheritedPhysicalContext -CandidateSha256 $CandidateSha256 -Direction $Direction)
Write-Output 'PASS_F325_INHERITED_PHYSICAL_CONTEXT'
