param([Parameter(Mandatory=$true)][string]$Config,[Parameter(Mandatory=$true)][string]$Output,
 [int]$Windows=15,[int]$Port=0,[switch]$PrepareEth1,[switch]$Observe,[switch]$Reopen)
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$taskOutput=[IO.Path]::GetFullPath($Output)
. (Join-Path $taskRoot 'tools/f319_uart_guard.ps1')
$taskGuard=$null;$taskProcess=$null
try {
 $taskLock=Join-Path $taskRoot 'work/hardware-lock/basic73-ag41w2bl'
 $taskGuard=Enter-F319HardwareGuard -Port COM4 -ExpectedPnpDeviceId 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -PhysicalLockDir $taskLock -Owner 'ETH73-authorized-traffic-lifecycle' -EvidenceDir $taskOutput
 $taskStart=[Diagnostics.ProcessStartInfo]::new()
 $taskStart.FileName=(Get-Command python).Source;$taskStart.UseShellExecute=$false;$taskStart.CreateNoWindow=$true
 $taskStart.Environment['PYTHONUNBUFFERED']='1'
 foreach($taskArg in @((Join-Path $PSScriptRoot 'soak.py'),'--config',[IO.Path]::GetFullPath($Config),'--output',$taskOutput,'--windows',[string]$Windows,'--port',[string]$Port,
 '--lock',$taskLock,'--owner-pid',[string]$taskGuard.OwnerPid,'--owner-ticks',[string]$taskGuard.OwnerStartTicks,'--lease-token',$taskGuard.LeaseToken)) {$taskStart.ArgumentList.Add($taskArg)}
 if($PrepareEth1){$taskStart.ArgumentList.Add('--prepare-eth1')}
 if($Observe){$taskStart.ArgumentList.Add('--observe')}
 if($Reopen){$taskStart.ArgumentList.Add('--reopen')}
 $taskProcess=[Diagnostics.Process]::new();$taskProcess.StartInfo=$taskStart
 if(-not $taskProcess.Start()){throw 'Traffic child not started'}
 $taskDeadline=[DateTime]::UtcNow.AddMinutes(12)
 while(-not $taskProcess.WaitForExit(1000)){
  [void](Assert-F319HardwareLease -PhysicalLockDir $taskLock -OwnerPid $taskGuard.OwnerPid -OwnerStartTicks $taskGuard.OwnerStartTicks -LeaseToken $taskGuard.LeaseToken -Port COM4 -ExpectedPnpDeviceId $taskGuard.PnpDeviceId)
  if([DateTime]::UtcNow -gt $taskDeadline){throw 'Traffic deadline'}
 }
 if($taskProcess.ExitCode -ne 0){throw 'Traffic campaign STOP; see receipt'}
}finally{
 if($taskProcess){if(-not $taskProcess.HasExited){$taskProcess.Kill($true);[void]$taskProcess.WaitForExit(3000)};$taskProcess.Dispose()}
 Exit-F319HardwareGuard -Guard $taskGuard
}
