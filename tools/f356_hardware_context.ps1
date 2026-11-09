Set-StrictMode -Version Latest
function Assert-F356Context {
    $c=$env:OM_F356_CONTEXT|ConvertFrom-Json
    if($c.schema -cne 'openmitrastar.f356-observe-context/v1' -or $c.purpose -cne 'ram-readonly-identification' -or
       $c.baseline_sha256 -cne '211c503a237107669ba8268529cd50b098022aac30c65c2683a5f7c8b823e2fa' -or
       $c.loader_sha256 -cne '8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6' -or
       $c.loader_runtime_path -cne '/usr/sbin/ram-insmod-qtn' -or $c.allow_program -isnot [bool] -or $c.allow_program -or
       $c.uart_port -cne 'COM3' -or $c.uart_pnp_device_id -ine 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -or
       $c.initial_boot_id -cnotmatch '^[0-9a-f-]{36}$' -or $c.binding.NonceObserved -isnot [bool] -or -not $c.binding.NonceObserved -or
       $c.binding.RouterHost -cne '192.168.1.90' -or $c.binding.Port -cne 'COM3' -or $c.binding.PnpDeviceId -ine $c.uart_pnp_device_id -or
       $c.binding.ExpectedVersion -cne 'lyoko-foundation-6.9.6-f340-watchdog-baseline-device'){throw 'F356_CONTEXT_SCOPE'}
    $issued=[DateTimeOffset]::Parse($c.created_at_utc);$expiry=[DateTimeOffset]::Parse($c.expires_at_utc)
    if($issued -gt [DateTimeOffset]::UtcNow -or $expiry -le [DateTimeOffset]::UtcNow -or ($expiry-$issued).TotalSeconds -ne 3600){throw 'F356_CONTEXT_EXPIRED'}
    if((Get-FileHash -LiteralPath $c.plan_path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $c.plan_sha256){throw 'F356_PLAN_DRIFT'}
    $p=Get-Content -LiteralPath $c.plan_path -Raw|ConvertFrom-Json
    if($p.schema -cne 'openmitrastar.f356-observe-plan/v1' -or $p.status -cne 'PASS_OFFLINE_OBSERVE_GATE' -or
       $p.allow_program -isnot [bool] -or $p.allow_program -or ($p.observation_commands -join '|') -cne 'observe' -or
       $p.provider.module_name -cne 'qtn_f356_journal' -or $p.kernel.kernel_version -cne '#350 @1790006400' -or
       [IO.Path]::GetFullPath($p.evidence_root) -ine '/workspace/OpenMitraStar\f356-evidence' -or
       $c.kernel_sha256 -cne $p.kernel.sha256 -or $c.provider_sha256 -cne $p.provider.sha256 -or
       $c.supervisor_ram_sha256 -cne $p.supervisor_ram.sha256 -or $c.cli_sha256 -cne $p.cli.sha256){throw 'F356_COMPONENT_SCOPE'}
    [void](Get-F319SerialDevice -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
    [void](Assert-F319HardwareLease -PhysicalLockDir $c.physical_lock_dir -OwnerPid $c.owner_pid -OwnerStartTicks $c.owner_start_ticks -LeaseToken $c.lease_token -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
    return $c
}
