param([Parameter(Mandatory=$true)][string]$ResultPath)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f358_hardware_context.ps1')
$script:GuardCalls=0
function Get-F319SerialDevice {param($Port,$ExpectedPnpDeviceId);$script:GuardCalls++;return @{} }
function Assert-F319HardwareLease {param($PhysicalLockDir,$OwnerPid,$OwnerStartTicks,$LeaseToken,$Port,$ExpectedPnpDeviceId);$script:GuardCalls++;return @{} }
$file=[IO.Path]::GetTempFileName();$old=$env:OM_F358_CONTEXT;$passed=0
try {
 $p=@{schema='openmitrastar.f358-install-plan/v1';evidence_root='/workspace/OpenMitraStar\f358-evidence';images=@{f358=@{sha256=('a'*64);kernel_build='#358'};f340=@{sha256='211c503a237107669ba8268529cd50b098022aac30c65c2683a5f7c8b823e2fa';kernel_build='#340'}}}
 [IO.File]::WriteAllText($file,($p|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false));$now=[DateTimeOffset]::UtcNow
 $valid=@{schema='openmitrastar.f358-install-context/v1';purpose='f358-install-conditional-f340-return';candidate_sha256=('a'*64);rollback_sha256=$p.images.f340.sha256;prefix_bytes=0x5e0000;uart_port='COM3';uart_pnp_device_id='FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000';initial_boot_id='01234567-89ab-cdef-0123-456789abcdef';created_at_utc=$now.ToString('o');expires_at_utc=$now.AddMinutes(90).ToString('o');plan_path=$file;plan_sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant();physical_lock_dir='fixture';owner_pid=100;owner_start_ticks=100;lease_token=('a'*32);binding=@{NonceObserved=$true;RouterHost='192.168.1.90';Port='COM3';PnpDeviceId='FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000';ExpectedVersion='lyoko-foundation-6.9.6-f340-watchdog-baseline-device'}}
 $json=$valid|ConvertTo-Json -Depth 10 -Compress;$env:OM_F358_CONTEXT=$json;[void](Assert-F358Context);if($script:GuardCalls -ne 2){throw 'VALID_PROFILE_SKIPPED_GUARDS'};$passed++
 $cases=@(
 {param($v)$v.candidate_sha256=('0'*64)},
 {param($v)$v.rollback_sha256='eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18'},
 {param($v)$v.prefix_bytes=0x7a0000},
 {param($v)$v.binding.ExpectedVersion='lyoko-foundation-6.8.5-f321-classic-ui-f314-device'},
 {param($v)$v.schema='openmitrastar.f346-install-context/v1'},
 {param($v)$v.binding.NonceObserved=$false}
 )
 foreach($change in $cases){
  $v=$json|ConvertFrom-Json;& $change $v;$env:OM_F358_CONTEXT=$v|ConvertTo-Json -Depth 10 -Compress;$script:GuardCalls=0;$rejected=$false
  try{[void](Assert-F358Context)}catch{$rejected=$true}
  if(-not $rejected -or $script:GuardCalls){throw 'WRONG_PROFILE_REACHED_GUARDS'};$passed++
 }
 $result=@{passed=$true;tests=$passed;hardware_actions=$false;scope='F358 candidate and F340 fallback adaptation'}
 [IO.File]::WriteAllText([IO.Path]::GetFullPath($ResultPath),($result|ConvertTo-Json),[Text.UTF8Encoding]::new($false));$result|ConvertTo-Json
}finally{$env:OM_F358_CONTEXT=$old;[IO.File]::Delete($file)}
