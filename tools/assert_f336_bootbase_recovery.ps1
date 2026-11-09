$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
$c=$env:OM_F336_BOOTBASE_RECOVERY | ConvertFrom-Json
if($c.schema -cne 'openmitrastar.f336-bootbase-recovery-context/v1' -or $c.purpose -cne 'direct-f321-return-no-ssh' -or $c.origin_run -cne 'f336-ram-20260921T132233Z-03826f49' -or $c.fresh_ssh_binding -ne $false -or $c.uart_pnp_device_id -ine 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000'){throw 'RECOVERY_CONTEXT_SCOPE'}
if([DateTimeOffset]::Parse($c.expires_at_utc) -le [DateTimeOffset]::UtcNow){throw 'RECOVERY_CONTEXT_EXPIRED'}
if((Get-FileHash -LiteralPath $c.plan_path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $c.plan_sha256){throw 'RECOVERY_PLAN_CHANGED'}
[void](Get-F319SerialDevice -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
[void](Assert-F319HardwareLease -PhysicalLockDir $c.physical_lock_dir -OwnerPid $c.owner_pid -OwnerStartTicks $c.owner_start_ticks -LeaseToken $c.lease_token -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
'PASS_F336_BOOTBASE_RECOVERY_CONTEXT'
