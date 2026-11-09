Set-StrictMode -Version Latest
function Assert-F363_SENSORContext {
 $c=$env:OM_F363_SENSOR_CONTEXT|ConvertFrom-Json
 if($c.schema -cne 'openmitrastar.f363-sensor-context/v1' -or $c.purpose -cne 'f363-sensor-activation-once' -or
    $c.supervisor_sha256 -cne '015d16cafef7e13e008fa451dbc25d5887f4e6935e695c2e2cbca90f2ed74904' -or
    $c.flash_writes -isnot [bool] -or $c.flash_writes -or $c.uart_port -cne 'COM3' -or
    $c.uart_pnp_device_id -ine 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -or
    $c.binding.NonceObserved -isnot [bool] -or -not $c.binding.NonceObserved -or
    $c.binding.RouterHost -cne '192.168.1.90' -or $c.binding.Port -cne 'COM3' -or $c.binding.PnpDeviceId -ine $c.uart_pnp_device_id -or
    $c.binding.ExpectedVersion -cne 'lyoko-foundation-6.9.11-f363r2-temperature-owner-device' -or $c.initial_boot_id -cnotmatch '^[0-9a-f-]{36}$'){throw 'F363_SENSOR_CONTEXT_SCOPE'}
 $issued=[DateTimeOffset]::Parse($c.created_at_utc);$expires=[DateTimeOffset]::Parse($c.expires_at_utc)
 if($issued -gt [DateTimeOffset]::UtcNow -or $expires -le [DateTimeOffset]::UtcNow -or ($expires-$issued).TotalSeconds -ne 3600){throw 'F363_SENSOR_CONTEXT_LIFETIME'}
 if((Get-FileHash -LiteralPath $c.plan_path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $c.plan_sha256){throw 'F363_SENSOR_PLAN_DRIFT'}
 $p=Get-Content -LiteralPath $c.plan_path -Raw|ConvertFrom-Json
 if($p.schema -cne 'openmitrastar.f363-sensor-plan/v1' -or $p.flash_writes -isnot [bool] -or $p.flash_writes -or
    $p.activation_attempts -ne 1 -or $p.sample_pairs -ne 3 -or $p.autoboot_intercept -or $p.images.f363.kernel_build -cne '#358' -or
    $c.baseline_sha256 -cne $p.images.f363.sha256 -or $c.sensor_sha256 -cne $p.sensor_module.sha256 -or $c.supervisor_sha256 -cne $p.supervisor.sha256 -or
    [IO.Path]::GetFullPath($p.evidence_root) -ine '/workspace/OpenMitraStar\f363-temperature-activation'){throw 'F363_SENSOR_PLAN_SCOPE'}
 [void](Get-F319SerialDevice -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
 [void](Assert-F319HardwareLease -PhysicalLockDir $c.physical_lock_dir -OwnerPid $c.owner_pid -OwnerStartTicks $c.owner_start_ticks -LeaseToken $c.lease_token -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
 return $c
}
