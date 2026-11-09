param([Parameter(Mandatory=$true)][string]$ResultPath)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f362_hardware_context.ps1')
$script:Calls=0
function Get-F319SerialDevice {param($Port,$ExpectedPnpDeviceId);$script:Calls++;return @{} }
function Assert-F319HardwareLease {param($PhysicalLockDir,$OwnerPid,$OwnerStartTicks,$LeaseToken,$Port,$ExpectedPnpDeviceId);$script:Calls++;return @{} }
$file=[IO.Path]::GetTempFileName();$old=$env:OM_F362_CONTEXT;$passed=0
try{
 $p=@{schema='openmitrastar.f362-install-plan/v1';evidence_root='/workspace/OpenMitraStar\f362-evidence';store=@{sha256=('c'*64);bytes=0x1c0000};images=@{f362=@{sha256=('a'*64)};f361=@{sha256='0c46aa0232129694097adf7b5e761bf2f633b4dd877787525d15610461b302af';kernel_build='#358'}}}
 [IO.File]::WriteAllText($file,($p|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false));$now=[DateTimeOffset]::UtcNow
 $v=@{schema='openmitrastar.f362-install-context/v1';purpose='f362-install-conditional-f361-return';candidate_sha256=('a'*64);rollback_sha256=$p.images.f361.sha256;store_sha256=('c'*64);prefix_bytes=0x5e0000;uart_port='COM3';uart_pnp_device_id='FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000';binding=@{NonceObserved=$true;RouterHost='192.168.1.90';Port='COM3';PnpDeviceId='FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000';ExpectedVersion='lyoko-foundation-6.9.9-f361-config-persistence-device'};initial_boot_id='01234567-89ab-cdef-0123-456789abcdef';created_at_utc=$now.ToString('o');expires_at_utc=$now.AddMinutes(90).ToString('o');plan_path=$file;plan_sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant();physical_lock_dir='fixture';owner_pid=1;owner_start_ticks=2;lease_token=('a'*32)}
 $json=$v|ConvertTo-Json -Depth 10 -Compress;$env:OM_F362_CONTEXT=$json;[void](Assert-F362Context);if($script:Calls -ne 2){throw 'MISSING_GUARDS'};$passed++
 foreach($change in @({param($c)$c.store_sha256=('0'*64)},{param($c)$c.prefix_bytes=0x7a0000},{param($c)$c.rollback_sha256=('0'*64)})){
  $c=$json|ConvertFrom-Json;& $change $c;$env:OM_F362_CONTEXT=$c|ConvertTo-Json -Depth 10 -Compress;$script:Calls=0;$rejected=$false;try{[void](Assert-F362Context)}catch{$rejected=$true};if(-not $rejected -or $script:Calls){throw 'WRONG_STORE_PROFILE_ACCEPTED'};$passed++
 }
 $result=@{passed=$true;tests=$passed;hardware_actions=$false};[IO.File]::WriteAllText([IO.Path]::GetFullPath($ResultPath),($result|ConvertTo-Json),[Text.UTF8Encoding]::new($false));$result|ConvertTo-Json
}finally{$env:OM_F362_CONTEXT=$old;[IO.File]::Delete($file)}
