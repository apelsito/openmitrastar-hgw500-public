param([Parameter(Mandatory=$true)][string]$ResultPath)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f360_hardware_context.ps1')
$script:Calls=0
function Get-F319SerialDevice {param($Port,$ExpectedPnpDeviceId);$script:Calls++;return @{} }
function Assert-F319HardwareLease {param($PhysicalLockDir,$OwnerPid,$OwnerStartTicks,$LeaseToken,$Port,$ExpectedPnpDeviceId);$script:Calls++;return @{} }
$file=[IO.Path]::GetTempFileName();$old=$env:OM_F360_CONTEXT;$passed=0
try {
 $plan=@{schema='openmitrastar.f360-save-plan/v1';allow_program=$true;operations=@('save','load');save_calls=1;rollback_erase_allowed=$false;payload=@{sha256='073747246e193ebca532b2de35b78a27a1930a908e0717f5706a682fa44457a9'};images=@{f358=@{kernel_build='#358'}};evidence_root='/workspace/OpenMitraStar\f360-evidence'}
 [IO.File]::WriteAllText($file,($plan|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false));$now=[DateTimeOffset]::UtcNow
 $value=@{schema='openmitrastar.f360-save-context/v1';purpose='f358-first-config-save';baseline_sha256='fe2ff28a8b083a72a089e8180d973727cea033673348a767a73595b440099e6f';provider_sha256='ab88ec603c18cd013f0de1d79eed1ea9c696ca97d2b589e0e8b9aaa8f9251cd4';supervisor_sha256='015d16cafef7e13e008fa451dbc25d5887f4e6935e695c2e2cbca90f2ed74904';allow_program=$true;payload_sha256='073747246e193ebca532b2de35b78a27a1930a908e0717f5706a682fa44457a9';uart_port='COM3';uart_pnp_device_id='FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000';initial_boot_id='01234567-89ab-cdef-0123-456789abcdef';created_at_utc=$now.ToString('o');expires_at_utc=$now.AddMinutes(60).ToString('o');plan_path=$file;plan_sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant();physical_lock_dir='fixture';owner_pid=1;owner_start_ticks=2;lease_token=('a'*32);binding=@{NonceObserved=$true;RouterHost='192.168.1.90';Port='COM3';PnpDeviceId='FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000';ExpectedVersion='lyoko-foundation-6.9.8-f358-config-backend-device'}}
 $json=$value|ConvertTo-Json -Depth 10 -Compress;$env:OM_F360_CONTEXT=$json;[void](Assert-F360Context);if($script:Calls -ne 2){throw 'MISSING_GUARDS'};$passed++
 foreach($change in @({param($v)$v.allow_program=$false},{param($v)$v.binding.ExpectedVersion='lyoko-foundation-6.9.6-f340-watchdog-baseline-device'},{param($v)$v.supervisor_sha256=('0'*64)})){
  $v=$json|ConvertFrom-Json;& $change $v;$env:OM_F360_CONTEXT=$v|ConvertTo-Json -Depth 10 -Compress;$script:Calls=0;$failed=$false;try{[void](Assert-F360Context)}catch{$failed=$true};if(-not $failed -or $script:Calls){throw 'PROFILE_NOT_REJECTED'};$passed++
 }
 $result=@{passed=$true;tests=$passed;hardware_actions=$false;historical_battery_rerun=$false};[IO.File]::WriteAllText([IO.Path]::GetFullPath($ResultPath),($result|ConvertTo-Json),[Text.UTF8Encoding]::new($false));$result|ConvertTo-Json
}finally{$env:OM_F360_CONTEXT=$old;[IO.File]::Delete($file)}
