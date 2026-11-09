param([Parameter(Mandatory=$true)][string]$PhysicalLockDir,
 [Parameter(Mandatory=$true)][int]$OwnerPid,[Parameter(Mandatory=$true)][long]$OwnerStartTicks,
 [Parameter(Mandatory=$true)][string]$LeaseToken)
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
. (Join-Path $taskRoot 'tools/f319_uart_guard.ps1')
[void](Assert-F319HardwareLease -PhysicalLockDir $PhysicalLockDir -OwnerPid $OwnerPid -OwnerStartTicks $OwnerStartTicks -LeaseToken $LeaseToken -Port COM4 -ExpectedPnpDeviceId 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000')
[void](Get-F319SerialDevice -Port COM4 -ExpectedPnpDeviceId 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000')
Write-Output 'BASIC73_LEASE_PASS'
