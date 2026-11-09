Set-StrictMode -Version Latest
function Assert-F363Context {
 $c=$env:OM_F363_CONTEXT|ConvertFrom-Json
 if($c.schema -cne 'openmitrastar.f363-install-context/v1' -or $c.purpose -cne 'f363-install-conditional-f362-return' -or
    $c.rollback_sha256 -cne '9582b92f1c68ec192ee14c55ba9ab69015749cc69ecde392bd6ad3392d105f2b' -or
    $c.prefix_bytes -ne 0x5e0000 -or $c.uart_port -cne 'COM3' -or $c.uart_pnp_device_id -ine 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -or
    $c.binding.NonceObserved -isnot [bool] -or -not $c.binding.NonceObserved -or $c.binding.RouterHost -cne '192.168.1.90' -or
    $c.binding.Port -cne 'COM3' -or $c.binding.PnpDeviceId -ine $c.uart_pnp_device_id -or
    $c.binding.ExpectedVersion -cne 'lyoko-foundation-6.9.10-f362-dual-ethernet-device' -or $c.initial_boot_id -cnotmatch '^[0-9a-f-]{36}$'){throw 'F363_CONTEXT_SCOPE'}
 $issued=[DateTimeOffset]::Parse($c.created_at_utc);$expires=[DateTimeOffset]::Parse($c.expires_at_utc)
 if($issued -gt [DateTimeOffset]::UtcNow -or $expires -le [DateTimeOffset]::UtcNow -or ($expires-$issued).TotalSeconds -ne 5400){throw 'F363_CONTEXT_LIFETIME'}
 if((Get-FileHash -LiteralPath $c.plan_path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $c.plan_sha256){throw 'F363_CONTEXT_PLAN'}
 $p=Get-Content -LiteralPath $c.plan_path -Raw|ConvertFrom-Json
 if($p.schema -cne 'openmitrastar.f363-install-plan/v1' -or $p.images.f362.kernel_build -cne '#358' -or
    $c.candidate_sha256 -cne $p.images.f363.sha256 -or $c.rollback_sha256 -cne $p.images.f362.sha256 -or
    $c.store_sha256 -cne $p.store.sha256 -or $p.store.bytes -ne 0x1c0000 -or
    [IO.Path]::GetFullPath($p.evidence_root) -ine '/workspace/OpenMitraStar\f363-evidence'){throw 'F363_IMAGE_STORE_PROFILE'}
 [void](Get-F319SerialDevice -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
 [void](Assert-F319HardwareLease -PhysicalLockDir $c.physical_lock_dir -OwnerPid $c.owner_pid -OwnerStartTicks $c.owner_start_ticks -LeaseToken $c.lease_token -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
 return $c
}
