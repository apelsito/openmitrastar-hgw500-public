Set-StrictMode -Version Latest
function Assert-F367Context {
 $c=$env:OM_F367_CONTEXT|ConvertFrom-Json
 if($c.schema -cne 'openmitrastar.f367-campaign-context/v1' -or $c.purpose -cne 'f367-campaign-always-f365-return' -or
    $c.rollback_sha256 -cne '43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355' -or
    $c.prefix_bytes -ne 0x5e0000 -or $c.uart_port -cne 'COM3' -or $c.uart_pnp_device_id -ine 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -or
    $c.binding.NonceObserved -isnot [bool] -or -not $c.binding.NonceObserved -or $c.binding.RouterHost -cne '192.168.1.90' -or
    $c.binding.Port -cne 'COM3' -or $c.binding.PnpDeviceId -ine $c.uart_pnp_device_id -or
    $c.binding.ExpectedVersion -cne 'lyoko-foundation-6.9.13-f365-temperature-data-device' -or $c.initial_boot_id -cnotmatch '^[0-9a-f-]{36}$'){throw 'F367_CONTEXT_SCOPE'}
 $issued=[DateTimeOffset]::Parse($c.created_at_utc);$expires=[DateTimeOffset]::Parse($c.expires_at_utc)
 if($issued -gt [DateTimeOffset]::UtcNow -or $expires -le [DateTimeOffset]::UtcNow -or ($expires-$issued).TotalSeconds -ne 7800){throw 'F367_CONTEXT_LIFETIME'}
 if((Get-FileHash -LiteralPath $c.plan_path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $c.plan_sha256){throw 'F367_CONTEXT_PLAN'}
 $p=Get-Content -LiteralPath $c.plan_path -Raw|ConvertFrom-Json
 if($p.callback_authority -ne 1 -or $p.dfs_primary -ne 52 -or $p.dfs_bandwidth -ne 20 -or $p.watchdog_session_ms -ne 5400000 -or $p.outer_timeout_seconds -ne 7500 -or $p.context_ttl_seconds -ne 7800 -or $p.always_restore_f365 -isnot [bool] -or -not $p.always_restore_f365){throw 'F367_CONTEXT_DIAGNOSTIC_SCOPE'}
 if($p.schema -cne 'openmitrastar.f367-campaign-plan/v1' -or $p.images.f365.kernel_build -cne '#358' -or
    $c.candidate_sha256 -cne $p.images.f367.sha256 -or $c.rollback_sha256 -cne $p.images.f365.sha256 -or
    $c.store_sha256 -cne $p.store.sha256 -or $p.store.bytes -ne 0x1c0000 -or
    [IO.Path]::GetFullPath($p.evidence_root) -ine '/workspace/OpenMitraStar\f367-campaign'){throw 'F367_IMAGE_STORE_PROFILE'}
 [void](Get-F319SerialDevice -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
 [void](Assert-F319HardwareLease -PhysicalLockDir $c.physical_lock_dir -OwnerPid $c.owner_pid -OwnerStartTicks $c.owner_start_ticks -LeaseToken $c.lease_token -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
 return $c
}
