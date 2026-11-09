Set-StrictMode -Version Latest
function Assert-F358Context {
 $c=$env:OM_F358_CONTEXT|ConvertFrom-Json
 if($c.schema -cne 'openmitrastar.f358-install-context/v1' -or $c.purpose -cne 'f358-install-conditional-f340-return' -or
    $c.rollback_sha256 -cne '211c503a237107669ba8268529cd50b098022aac30c65c2683a5f7c8b823e2fa' -or
    $c.prefix_bytes -ne 0x5e0000 -or $c.uart_port -cne 'COM3' -or $c.uart_pnp_device_id -ine 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -or
    $c.binding.NonceObserved -isnot [bool] -or -not $c.binding.NonceObserved -or $c.binding.RouterHost -cne '192.168.1.90' -or
    $c.binding.Port -cne 'COM3' -or $c.binding.PnpDeviceId -ine $c.uart_pnp_device_id -or
    $c.binding.ExpectedVersion -cne 'lyoko-foundation-6.9.6-f340-watchdog-baseline-device' -or $c.initial_boot_id -cnotmatch '^[0-9a-f-]{36}$'){throw 'F358_CONTEXT_SCOPE'}
 $issued=[DateTimeOffset]::Parse($c.created_at_utc);$expires=[DateTimeOffset]::Parse($c.expires_at_utc)
 if($issued -gt [DateTimeOffset]::UtcNow -or $expires -le [DateTimeOffset]::UtcNow -or ($expires-$issued).TotalSeconds -ne 5400){throw 'F358_CONTEXT_LIFETIME'}
 if((Get-FileHash -LiteralPath $c.plan_path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $c.plan_sha256){throw 'F358_CONTEXT_PLAN'}
 $p=Get-Content -LiteralPath $c.plan_path -Raw|ConvertFrom-Json
 if($p.schema -cne 'openmitrastar.f358-install-plan/v1' -or $p.images.f358.kernel_build -cne '#358' -or
    $p.images.f340.kernel_build -cne '#340' -or $c.candidate_sha256 -cne $p.images.f358.sha256 -or
    $c.rollback_sha256 -cne $p.images.f340.sha256 -or [IO.Path]::GetFullPath($p.evidence_root) -ine '/workspace/OpenMitraStar\f358-evidence'){throw 'F358_IMAGE_PROFILE'}
 [void](Get-F319SerialDevice -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
 [void](Assert-F319HardwareLease -PhysicalLockDir $c.physical_lock_dir -OwnerPid $c.owner_pid -OwnerStartTicks $c.owner_start_ticks -LeaseToken $c.lease_token -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
 return $c
}
