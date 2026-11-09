param([Parameter(Mandatory=$true)][string]$Config,
 [Parameter(Mandatory=$true)][string]$Output,[switch]$Execute,[string]$BaselineBoot='',[switch]$AttachReceiver,[switch]$WaitPowerCycle)
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$taskConfig=[IO.Path]::GetFullPath($Config)
$taskOutput=[IO.Path]::GetFullPath($Output)
& python (Join-Path $PSScriptRoot 'executor.py') --config $taskConfig --output $taskOutput
if ($LASTEXITCODE -ne 0) {throw 'RAM preflight refused'}
if (-not $Execute) {return}
& python (Join-Path $PSScriptRoot 'test_executor.py')
if ($LASTEXITCODE -ne 0) {throw 'Executor simulation did not pass'}
# Owner explicitly authorized full port testing including necessary resets.
# Verify exact artifact/dependencies, preserve a record of that trusted authority.
$taskPins=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'SOURCE_PINS.json') -Raw | ConvertFrom-Json
foreach ($taskPin in $taskPins.PSObject.Properties) {
 if ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $taskRoot $taskPin.Name)).Hash.ToLowerInvariant() -cne $taskPin.Value) {throw 'RAM executor source drift'}
}
. (Join-Path $taskRoot 'tools/f319_uart_guard.ps1')
$taskLock=Join-Path $taskRoot 'work/hardware-lock/basic73-ag41w2bl'
$taskGuard=$null;$taskProcess=$null
try {
 $taskGuard=Enter-F319HardwareGuard -Port COM4 -ExpectedPnpDeviceId 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -PhysicalLockDir $taskLock -Owner 'ETH73-RAM-owner-authorized' -EvidenceDir $taskOutput
 $taskStart=[Diagnostics.ProcessStartInfo]::new()
 $taskStart.FileName=(Get-Command python).Source;$taskStart.UseShellExecute=$false;$taskStart.CreateNoWindow=$true
 $taskStart.Environment['PYTHONUNBUFFERED']='1'
 foreach ($taskArg in @((Join-Path $PSScriptRoot 'executor.py'),'--execute','--config',$taskConfig,'--output',$taskOutput,
 '--lock',$taskLock,'--owner-pid',[string]$taskGuard.OwnerPid,'--owner-ticks',[string]$taskGuard.OwnerStartTicks,'--lease-token',$taskGuard.LeaseToken,'--baseline-boot',$BaselineBoot)) {$taskStart.ArgumentList.Add($taskArg)}
 if ($AttachReceiver) {$taskStart.ArgumentList.Add('--attach-receiver')}
 if ($WaitPowerCycle) {$taskStart.ArgumentList.Add('--wait-power-cycle')}
 $taskProcess=[Diagnostics.Process]::new();$taskProcess.StartInfo=$taskStart
 if (-not $taskProcess.Start()) {throw 'RAM trial child did not start'}
 $taskDeadline=[DateTime]::UtcNow.AddMinutes(28)
 while (-not $taskProcess.WaitForExit(1000)) {
  [void](Assert-F319HardwareLease -PhysicalLockDir $taskLock -OwnerPid $taskGuard.OwnerPid -OwnerStartTicks $taskGuard.OwnerStartTicks -LeaseToken $taskGuard.LeaseToken -Port COM4 -ExpectedPnpDeviceId $taskGuard.PnpDeviceId)
  if ([DateTime]::UtcNow -gt $taskDeadline) {throw 'RAM trial absolute deadline'}
 }
 if ($taskProcess.ExitCode -ne 0) {throw 'RAM trial stopped; inspect exact receipt before a new action'}
} finally {
 if ($taskProcess) {if (-not $taskProcess.HasExited) {$taskProcess.Kill($true);[void]$taskProcess.WaitForExit(3000)};$taskProcess.Dispose()}
 Exit-F319HardwareGuard -Guard $taskGuard
}
