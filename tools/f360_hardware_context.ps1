Set-StrictMode -Version Latest
function Assert-F360Context {
 $c=$env:OM_F360_CONTEXT|ConvertFrom-Json
 if($c.schema -cne 'openmitrastar.f360-save-context/v1' -or $c.purpose -cne 'f358-first-config-save' -or
    $c.baseline_sha256 -cne 'fe2ff28a8b083a72a089e8180d973727cea033673348a767a73595b440099e6f' -or
    $c.provider_sha256 -cne 'ab88ec603c18cd013f0de1d79eed1ea9c696ca97d2b589e0e8b9aaa8f9251cd4' -or
    $c.supervisor_sha256 -cne '015d16cafef7e13e008fa451dbc25d5887f4e6935e695c2e2cbca90f2ed74904' -or
    $c.payload_sha256 -cne '073747246e193ebca532b2de35b78a27a1930a908e0717f5706a682fa44457a9' -or $c.allow_program -isnot [bool] -or -not $c.allow_program -or $c.uart_port -cne 'COM3' -or
    $c.uart_pnp_device_id -ine 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -or
    $c.binding.NonceObserved -isnot [bool] -or -not $c.binding.NonceObserved -or
    $c.binding.RouterHost -cne '192.168.1.90' -or $c.binding.Port -cne 'COM3' -or $c.binding.PnpDeviceId -ine $c.uart_pnp_device_id -or
    $c.binding.ExpectedVersion -cne 'lyoko-foundation-6.9.8-f358-config-backend-device' -or $c.initial_boot_id -cnotmatch '^[0-9a-f-]{36}$'){throw 'F360_CONTEXT_SCOPE'}
 $issued=[DateTimeOffset]::Parse($c.created_at_utc);$expires=[DateTimeOffset]::Parse($c.expires_at_utc)
 if($issued -gt [DateTimeOffset]::UtcNow -or $expires -le [DateTimeOffset]::UtcNow -or ($expires-$issued).TotalSeconds -ne 3600){throw 'F360_CONTEXT_LIFETIME'}
 if((Get-FileHash -LiteralPath $c.plan_path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $c.plan_sha256){throw 'F360_PLAN_DRIFT'}
 $p=Get-Content -LiteralPath $c.plan_path -Raw|ConvertFrom-Json
 if($p.schema -cne 'openmitrastar.f360-save-plan/v1' -or $p.allow_program -isnot [bool] -or -not $p.allow_program -or
    ($p.operations -join '|') -cne 'save|load' -or $p.save_calls -ne 1 -or $p.rollback_erase_allowed -isnot [bool] -or $p.rollback_erase_allowed -or $p.payload.sha256 -cne $c.payload_sha256 -or $p.images.f358.kernel_build -cne '#358' -or
    [IO.Path]::GetFullPath($p.evidence_root) -ine '/workspace/OpenMitraStar\f360-evidence'){throw 'F360_PLAN_SCOPE'}
 [void](Get-F319SerialDevice -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
 [void](Assert-F319HardwareLease -PhysicalLockDir $c.physical_lock_dir -OwnerPid $c.owner_pid -OwnerStartTicks $c.owner_start_ticks -LeaseToken $c.lease_token -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
 return $c
}
