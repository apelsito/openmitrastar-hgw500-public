Set-StrictMode -Version Latest
function Assert-F336Context {
    $c=$env:OM_F336_RAM_CONTEXT | ConvertFrom-Json
    if($c.schema -cne 'openmitrastar.f336-ram-context/v1' -or $c.purpose -cne 'ram-watchdog' -or
       $c.candidate_sha256 -cne 'c200f12bf38a7e94235817e208601cd6c2b42e2e11d846c0e24da9e0b8a8c675' -or
       $c.flash_allowed -isnot [bool] -or $c.flash_allowed -or $c.uart_port -cne 'COM3' -or
       $c.uart_pnp_device_id -ine 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -or
       $c.binding.NonceObserved -isnot [bool] -or -not $c.binding.NonceObserved -or
       $c.binding.RouterHost -cne '192.168.1.90' -or $c.binding.Port -cne 'COM3' -or
       $c.binding.PnpDeviceId -ine $c.uart_pnp_device_id -or
       $c.binding.ExpectedVersion -cne 'lyoko-foundation-6.8.5-f321-classic-ui-f314-device') {throw 'F336_CONTEXT_IDENTITY'}
    $issued=[DateTimeOffset]::Parse($c.created_at_utc);$expires=[DateTimeOffset]::Parse($c.expires_at_utc)
    if($issued -gt [DateTimeOffset]::UtcNow -or $expires -le [DateTimeOffset]::UtcNow -or ($expires-$issued).TotalSeconds -ne 1800){throw 'F336_CONTEXT_EXPIRED'}
    [void](Get-F319SerialDevice -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
    [void](Assert-F319HardwareLease -PhysicalLockDir $c.physical_lock_dir -OwnerPid $c.owner_pid -OwnerStartTicks $c.owner_start_ticks -LeaseToken $c.lease_token -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
    return $c
}
