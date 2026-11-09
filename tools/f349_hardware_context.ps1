Set-StrictMode -Version Latest
function Assert-F349Context {
    $c=$env:OM_F349_CONTEXT|ConvertFrom-Json
    if($c.schema -cne 'openmitrastar.f349-passive-context/v1' -or $c.purpose -cne 'one-passive-spi-control-read' -or
       $c.probe_sha256 -cne '6ec075b4875890d5f366ff568932b591b59cc15231282274d77bb868a768a06a' -or
       $c.baseline_sha256 -cne '211c503a237107669ba8268529cd50b098022aac30c65c2683a5f7c8b823e2fa' -or
       $c.uart_port -cne 'COM3' -or $c.uart_pnp_device_id -ine 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -or
       $c.initial_boot_id -cnotmatch '^[0-9a-f-]{36}$' -or $c.binding.NonceObserved -isnot [bool] -or -not $c.binding.NonceObserved -or
       $c.binding.RouterHost -cne '192.168.1.90' -or $c.binding.Port -cne 'COM3' -or $c.binding.PnpDeviceId -ine $c.uart_pnp_device_id -or
       $c.binding.ExpectedVersion -cne 'lyoko-foundation-6.9.6-f340-watchdog-baseline-device'){throw 'F349_CONTEXT_SCOPE'}
    $issued=[DateTimeOffset]::Parse($c.created_at_utc);$expiry=[DateTimeOffset]::Parse($c.expires_at_utc)
    if($issued -gt [DateTimeOffset]::UtcNow -or $expiry -le [DateTimeOffset]::UtcNow -or ($expiry-$issued).TotalSeconds -ne 1800){throw 'F349_CONTEXT_EXPIRED'}
    if((Get-FileHash -LiteralPath $c.plan_path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $c.plan_sha256){throw 'F349_PLAN_DRIFT'}
    [void](Get-F319SerialDevice -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
    [void](Assert-F319HardwareLease -PhysicalLockDir $c.physical_lock_dir -OwnerPid $c.owner_pid -OwnerStartTicks $c.owner_start_ticks -LeaseToken $c.lease_token -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
    return $c
}
