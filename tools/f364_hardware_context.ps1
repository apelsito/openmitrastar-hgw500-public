Set-StrictMode -Version Latest
function Assert-F364Context {
 $c=$env:OM_F364_CONTEXT|ConvertFrom-Json
 if($c.schema -cne 'openmitrastar.f364-install-context/v1' -or $c.purpose -cne 'f364-install-conditional-f363-return' -or
    $c.rollback_sha256 -cne 'be5073c2e3fca5b4a214513f3c7aeee42b463b760b8213bf55c12a6ccbc2c075' -or
    $c.prefix_bytes -ne 0x5e0000 -or $c.uart_port -cne 'COM3' -or $c.uart_pnp_device_id -ine 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -or
    $c.binding.NonceObserved -isnot [bool] -or -not $c.binding.NonceObserved -or $c.binding.RouterHost -cne '192.168.1.90' -or
    $c.binding.Port -cne 'COM3' -or $c.binding.PnpDeviceId -ine $c.uart_pnp_device_id -or
    $c.binding.ExpectedVersion -cne 'lyoko-foundation-6.9.11-f363r2-temperature-owner-device' -or $c.initial_boot_id -cnotmatch '^[0-9a-f-]{36}$'){throw 'F364_CONTEXT_SCOPE'}
 $issued=[DateTimeOffset]::Parse($c.created_at_utc);$expires=[DateTimeOffset]::Parse($c.expires_at_utc)
 if($issued -gt [DateTimeOffset]::UtcNow -or $expires -le [DateTimeOffset]::UtcNow -or ($expires-$issued).TotalSeconds -ne 5400){throw 'F364_CONTEXT_LIFETIME'}
 if((Get-FileHash -LiteralPath $c.plan_path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $c.plan_sha256){throw 'F364_CONTEXT_PLAN'}
 $p=Get-Content -LiteralPath $c.plan_path -Raw|ConvertFrom-Json
 if($p.schema -cne 'openmitrastar.f364-install-plan/v1' -or $p.images.f363.kernel_build -cne '#358' -or
    $c.candidate_sha256 -cne $p.images.f364.sha256 -or $c.rollback_sha256 -cne $p.images.f363.sha256 -or
    $c.store_sha256 -cne $p.store.sha256 -or $p.store.bytes -ne 0x1c0000 -or
    [IO.Path]::GetFullPath($p.evidence_root) -ine '/workspace/OpenMitraStar\f364-evidence'){throw 'F364_IMAGE_STORE_PROFILE'}
 [void](Get-F319SerialDevice -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
 [void](Assert-F319HardwareLease -PhysicalLockDir $c.physical_lock_dir -OwnerPid $c.owner_pid -OwnerStartTicks $c.owner_start_ticks -LeaseToken $c.lease_token -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
 return $c
}
