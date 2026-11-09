param([Parameter(Mandatory=$true)][string]$ResultPath)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f346_hardware_context.ps1')
$script:PnpCalls=0;$script:LeaseCalls=0
# These test-only substitutes never enumerate/open a device or inspect a lease.
function Get-F319SerialDevice {param($Port,$ExpectedPnpDeviceId);$script:PnpCalls++;return @{} }
function Assert-F319HardwareLease {param($PhysicalLockDir,$OwnerPid,$OwnerStartTicks,$LeaseToken,$Port,$ExpectedPnpDeviceId);$script:LeaseCalls++;return @{} }
$file=[IO.FileInfo]::new([IO.Path]::GetTempFileName());$saved=$env:OM_F346_CONTEXT;$passed=0
try {
    [IO.File]::WriteAllText($file.FullName,'{}',[Text.UTF8Encoding]::new($false))
    $hash=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant();$now=[DateTimeOffset]::UtcNow
    $valid=[ordered]@{schema='openmitrastar.f346-install-context/v1';purpose='f340-install-conditional-f321-return';candidate_sha256='211c503a237107669ba8268529cd50b098022aac30c65c2683a5f7c8b823e2fa';rollback_sha256='eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18';prefix_bytes=0x5e0000;uart_port='COM3';uart_pnp_device_id='FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000';initial_boot_id='01234567-89ab-cdef-0123-456789abcdef';created_at_utc=$now.ToString('o');expires_at_utc=$now.AddMinutes(90).ToString('o');plan_path=$file.FullName;plan_sha256=$hash;physical_lock_dir='fixture';owner_pid=100;owner_start_ticks=100;lease_token=('a'*32);binding=@{NonceObserved=$true;RouterHost='192.168.1.90';Port='COM3';PnpDeviceId='FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000';ExpectedVersion='lyoko-foundation-6.8.5-f321-classic-ui-f314-device'}}
    $json=$valid|ConvertTo-Json -Depth 10 -Compress
    $env:OM_F346_CONTEXT=$json;[void](Assert-F346Context)
    if($script:PnpCalls -ne 1 -or $script:LeaseCalls -ne 1){throw 'VALID_CONTEXT_DID_NOT_REQUIRE_BOTH_GUARDS'};$passed++
    $cases=@(
      {param($v)$v.schema='openmitrastar.f325-physical-context/v1'},
      {param($v)$v.purpose='promote'},
      {param($v)$v.candidate_sha256='e18b221dda9a61bd1066c155c0cd7b44aef0d0fe06b1a1752a7e759e7730c7ec'},
      {param($v)$v.rollback_sha256=('0'*64)},
      {param($v)$v.prefix_bytes=0x7a0000},
      {param($v)$v.uart_port='COM4'},
      {param($v)$v.uart_pnp_device_id='OTHER'},
      {param($v)$v.binding.NonceObserved=$false},
      {param($v)$v.binding.Port='COM4'},
      {param($v)$v.binding.PnpDeviceId='OTHER'},
      {param($v)$v.binding.ExpectedVersion='F334'},
      {param($v)$v.initial_boot_id=''},
      {param($v)$v.expires_at_utc=[DateTimeOffset]::UtcNow.AddSeconds(-1).ToString('o')},
      {param($v)$v.created_at_utc=[DateTimeOffset]::UtcNow.AddMinutes(1).ToString('o')},
      {param($v)$v.plan_sha256=('0'*64)}
    )
    foreach($change in $cases){
        $v=$json|ConvertFrom-Json;& $change $v;$env:OM_F346_CONTEXT=$v|ConvertTo-Json -Depth 10 -Compress
        $script:PnpCalls=0;$script:LeaseCalls=0;$rejected=$false
        try{[void](Assert-F346Context)}catch{$rejected=$true}
        if(-not $rejected -or $script:PnpCalls -ne 0 -or $script:LeaseCalls -ne 0){throw 'BAD_CONTEXT_REACHED_LIVE_GUARDS'};$passed++
    }
    $result=[ordered]@{tests=$passed;passed=$true;hardware_actions=$false;live_helpers_replaced_by_test_functions=$true}
    [IO.File]::WriteAllText([IO.Path]::GetFullPath($ResultPath),($result|ConvertTo-Json),[Text.UTF8Encoding]::new($false));$result|ConvertTo-Json
} finally {$env:OM_F346_CONTEXT=$saved;[IO.File]::Delete($file.FullName)}
