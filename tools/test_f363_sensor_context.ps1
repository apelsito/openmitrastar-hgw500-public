param([Parameter(Mandatory=$true)][string]$ResultPath)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f363_sensor_context.ps1')
$script:Calls=0
function Get-F319SerialDevice {param($Port,$ExpectedPnpDeviceId);$script:Calls++;return @{} }
function Assert-F319HardwareLease {param($PhysicalLockDir,$OwnerPid,$OwnerStartTicks,$LeaseToken,$Port,$ExpectedPnpDeviceId);$script:Calls++;return @{} }
$file=[IO.Path]::GetTempFileName();$old=$env:OM_F363_SENSOR_CONTEXT;$passed=0
try{
 $p=@{schema='openmitrastar.f363-sensor-plan/v1';evidence_root='/workspace/OpenMitraStar\f363-temperature-activation';flash_writes=$false;autoboot_intercept=$false;activation_attempts=1;sample_pairs=3;images=@{f363=@{sha256=('a'*64);kernel_build='#358'}};sensor_module=@{sha256=('b'*64)};supervisor=@{sha256='015d16cafef7e13e008fa451dbc25d5887f4e6935e695c2e2cbca90f2ed74904'}}
 [IO.File]::WriteAllText($file,($p|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false));$now=[DateTimeOffset]::UtcNow
 $v=@{schema='openmitrastar.f363-sensor-context/v1';purpose='f363-sensor-activation-once';baseline_sha256=('a'*64);sensor_sha256=('b'*64);supervisor_sha256=$p.supervisor.sha256;flash_writes=$false;uart_port='COM3';uart_pnp_device_id='FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000';binding=@{NonceObserved=$true;RouterHost='192.168.1.90';Port='COM3';PnpDeviceId='FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000';ExpectedVersion='lyoko-foundation-6.9.11-f363r2-temperature-owner-device'};initial_boot_id='01234567-89ab-cdef-0123-456789abcdef';created_at_utc=$now.ToString('o');expires_at_utc=$now.AddMinutes(60).ToString('o');plan_path=$file;plan_sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant();physical_lock_dir='fixture';owner_pid=1;owner_start_ticks=2;lease_token=('a'*32)}
 $json=$v|ConvertTo-Json -Depth 10 -Compress;$env:OM_F363_SENSOR_CONTEXT=$json;[void](Assert-F363_SENSORContext);if($script:Calls -ne 2){throw 'MISSING_GUARDS'};$passed++
 foreach($change in @({param($c)$c.sensor_sha256=('0'*64)},{param($c)$c.flash_writes=$true},{param($c)$c.binding.NonceObserved=$false})){
  $c=$json|ConvertFrom-Json;& $change $c;$env:OM_F363_SENSOR_CONTEXT=$c|ConvertTo-Json -Depth 10 -Compress;$script:Calls=0;$rejected=$false;try{[void](Assert-F363_SENSORContext)}catch{$rejected=$true};if(-not $rejected -or $script:Calls){throw 'WRONG_SENSOR_CONTEXT_ACCEPTED'};$passed++
 }
 $result=@{passed=$true;tests=$passed;hardware_actions=$false};[IO.File]::WriteAllText([IO.Path]::GetFullPath($ResultPath),($result|ConvertTo-Json),[Text.UTF8Encoding]::new($false));$result|ConvertTo-Json
}finally{$env:OM_F363_SENSOR_CONTEXT=$old;[IO.File]::Delete($file)}
