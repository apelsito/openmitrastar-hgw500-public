[CmdletBinding()]
param([ValidateSet('prepare','activate','inspect','stop')][string]$Mode='prepare')
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
if($PSVersionTable.PSEdition -cne 'Desktop'){throw 'WINDOWS_POWERSHELL51_REQUIRED'}
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
$package=Join-Path $root 'outputs\rea\arc700-20261021-r2\f365-ram-activation\r3'
$packageHash='7fe2dc8082392d27c0d84f58e00de1dd432b56f296bc2dc0b17f426ea2b90393'
if((Get-FileHash -LiteralPath (Join-Path $package 'package.tar') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $packageHash){throw 'PACKAGE_CHANGED'}
$parent=Join-Path $root 'outputs\locks\f301-physical-radio.lock'
$parentOwner=Join-Path $parent 'owner.json'
$parentHash=(Get-FileHash -LiteralPath $parentOwner -Algorithm SHA256).Hash.ToLowerInvariant()
if($parentHash -cne '37c47a29576b1da2743057d974e1ec3850965c98eef956ba04ff2973e21b1b48'){throw 'PARENT_QUARANTINE_CHANGED'}
$oldOwner=Get-Content -LiteralPath $parentOwner -Raw|ConvertFrom-Json
$oldProcess=Get-Process -Id $oldOwner.pid -ErrorAction SilentlyContinue
if($oldProcess -and $oldProcess.StartTime.ToUniversalTime().Ticks -eq $oldOwner.process_start_ticks){throw 'PRIOR_OWNER_RUNNING'}
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$out=Join-Path $root ('outputs\rea\arc700-20261021-r2\physical-'+$Mode+'-'+$stamp)
$child=Join-Path $parent ('f365-ram-'+$Mode+'-'+$stamp+'.lock')
$guard=$null;$stream=$null;$exit=1
$previous=$env:OM_F365_RAM_CHILD_CONTEXT
try{
 $stream=[IO.File]::Open($parentOwner,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
 $guard=Enter-F319HardwareGuard -Port COM4 -ExpectedPnpDeviceId 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -PhysicalLockDir $child -Owner ('F365_RAM_NONDFS_'+$Mode) -EvidenceDir $out
 if($Mode -eq 'prepare'){
  $known=Join-Path $env:USERPROFILE '.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f367r9-f365-transition-observation-device-bound\known_hosts.f367'
  $binding=Assert-F319UartBinding -Port COM4 -ExpectedPnpDeviceId $guard.PnpDeviceId -RouterHost '192.168.1.90' -KnownHosts $known -ExpectedVersion 'lyoko-foundation-6.11.8-f367r9-transition-observation-device' -HardwareLease $guard
  if(-not $binding.NonceObserved){throw 'UART_BINDING_FAILED'}
 }
 $context=@{boot_id='5f513265-a294-4366-9567-e1d8af704b6b';package_sha256=$packageHash;port='COM4';parent_owner_sha256=$parentHash;owner_pid=$guard.OwnerPid;owner_start_ticks=$guard.OwnerStartTicks;lease_token=$guard.LeaseToken;physical_lock_dir=$child}
 $env:OM_F365_RAM_CHILD_CONTEXT=$context|ConvertTo-Json -Compress
 & '/workspace/user-home\AppData\Local\Programs\Python\Python312\python.exe' (Join-Path $PSScriptRoot 'f365_ram_execute.py') --package-dir $package --output $out --mode $Mode
 $exit=$LASTEXITCODE
 if((Get-FileHash -LiteralPath $parentOwner -Algorithm SHA256).Hash.ToLowerInvariant() -cne $parentHash){throw 'PARENT_QUARANTINE_MUTATED'}
}finally{
 $env:OM_F365_RAM_CHILD_CONTEXT=$previous
 if($guard){Exit-F319HardwareGuard -Guard $guard}
 if($stream){$stream.Dispose()}
}
exit $exit
