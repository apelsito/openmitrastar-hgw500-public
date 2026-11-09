param([Parameter(Mandatory=$true)][string]$ResultPath)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f356_hardware_context.ps1')
$script:PnpCalls=0;$script:LeaseCalls=0
function Get-F319SerialDevice {param($Port,$ExpectedPnpDeviceId);$script:PnpCalls++;return @{} }
function Assert-F319HardwareLease {param($PhysicalLockDir,$OwnerPid,$OwnerStartTicks,$LeaseToken,$Port,$ExpectedPnpDeviceId);$script:LeaseCalls++;return @{} }
$file=[IO.Path]::GetTempFileName();$old=$env:OM_F356_CONTEXT;$passed=0
try {
 $plan=[ordered]@{schema='openmitrastar.f356-observe-plan/v1';status='PASS_OFFLINE_OBSERVE_GATE';allow_program=$false;observation_commands=@('observe');evidence_root='/workspace/OpenMitraStar\f356-evidence';kernel=@{kernel_version='#350 @1790006400';sha256=('a'*64)};provider=@{module_name='qtn_f356_journal';sha256=('b'*64)};supervisor_ram=@{sha256=('c'*64)};cli=@{sha256=('d'*64)}}
 $planJson=$plan|ConvertTo-Json -Depth 10 -Compress
 [IO.File]::WriteAllText($file,$planJson,[Text.UTF8Encoding]::new($false));$hash=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant();$now=[DateTimeOffset]::UtcNow
 $valid=[ordered]@{schema='openmitrastar.f356-observe-context/v1';purpose='ram-readonly-identification';baseline_sha256='211c503a237107669ba8268529cd50b098022aac30c65c2683a5f7c8b823e2fa';loader_sha256='8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6';loader_runtime_path='/usr/sbin/ram-insmod-qtn';allow_program=$false;kernel_sha256=('a'*64);provider_sha256=('b'*64);supervisor_ram_sha256=('c'*64);cli_sha256=('d'*64);uart_port='COM3';uart_pnp_device_id='FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000';initial_boot_id='01234567-89ab-cdef-0123-456789abcdef';created_at_utc=$now.ToString('o');expires_at_utc=$now.AddMinutes(60).ToString('o');plan_path=$file;plan_sha256=$hash;physical_lock_dir='fixture';owner_pid=100;owner_start_ticks=100;lease_token=('a'*32);binding=@{NonceObserved=$true;RouterHost='192.168.1.90';Port='COM3';PnpDeviceId='FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000';ExpectedVersion='lyoko-foundation-6.9.6-f340-watchdog-baseline-device'}}
 $json=$valid|ConvertTo-Json -Depth 10 -Compress;$env:OM_F356_CONTEXT=$json;[void](Assert-F356Context)
 if($script:PnpCalls -ne 1 -or $script:LeaseCalls -ne 1){throw 'VALID_CONTEXT_SKIPPED_GUARDS'};$passed++
 $cases=@(
 {param($v)$v.schema='openmitrastar.f354-passive-context/v1'},
 {param($v)$v.purpose='flash-write'},
 {param($v)$v.allow_program=$true},
 {param($v)$v.allow_program='false'},
 {param($v)$v.baseline_sha256=('0'*64)},
 {param($v)$v.loader_sha256=('0'*64)},
 {param($v)$v.loader_runtime_path='/bin/insmod'},
 {param($v)$v.kernel_sha256=('0'*64)},
 {param($v)$v.provider_sha256=('0'*64)},
 {param($v)$v.supervisor_ram_sha256=('0'*64)},
 {param($v)$v.cli_sha256=('0'*64)},
 {param($v)$v.uart_port='COM4'},
 {param($v)$v.uart_pnp_device_id='OTHER'},
 {param($v)$v.binding.NonceObserved=$false},
 {param($v)$v.binding.ExpectedVersion='F321'},
 {param($v)$v.initial_boot_id=''},
 {param($v)$v.expires_at_utc=[DateTimeOffset]::UtcNow.AddSeconds(-1).ToString('o')},
 {param($v)$v.plan_sha256=('0'*64)}
 )
 foreach($change in $cases){
  $v=$json|ConvertFrom-Json;& $change $v;$env:OM_F356_CONTEXT=$v|ConvertTo-Json -Depth 10 -Compress;$script:PnpCalls=0;$script:LeaseCalls=0;$rejected=$false
  try{[void](Assert-F356Context)}catch{$rejected=$true}
  if(-not $rejected -or $script:PnpCalls -ne 0 -or $script:LeaseCalls -ne 0){throw 'INVALID_CONTEXT_REACHED_LIVE_GUARDS'};$passed++
 }
 $planCases=@(
 {param($v)$v.kernel.kernel_version='#340 @1790006400'},
 {param($v)$v.provider.module_name='qtn_f350_journal'},
 {param($v)$v.observation_commands=@('save')},
 {param($v)$v.allow_program=$true},
 {param($v)$v.evidence_root='C:\temporary-evidence'}
 )
 foreach($change in $planCases){
  $changed=$planJson|ConvertFrom-Json;& $change $changed;[IO.File]::WriteAllText($file,($changed|ConvertTo-Json -Depth 10 -Compress),[Text.UTF8Encoding]::new($false))
  $v=$json|ConvertFrom-Json;$v.plan_sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant();$env:OM_F356_CONTEXT=$v|ConvertTo-Json -Depth 10 -Compress;$script:PnpCalls=0;$script:LeaseCalls=0;$rejected=$false
  try{[void](Assert-F356Context)}catch{$rejected=$true}
  if(-not $rejected -or $script:PnpCalls -ne 0 -or $script:LeaseCalls -ne 0){throw 'BAD_PLAN_REACHED_LIVE_GUARDS'};$passed++
 }
 $result=[ordered]@{tests=$passed;passed=$true;hardware_actions=$false;live_helpers_replaced_by_test_functions=$true}
 [IO.File]::WriteAllText([IO.Path]::GetFullPath($ResultPath),($result|ConvertTo-Json),[Text.UTF8Encoding]::new($false));$result|ConvertTo-Json
}finally{$env:OM_F356_CONTEXT=$old;[IO.File]::Delete($file)}
