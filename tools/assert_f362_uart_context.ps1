param([switch]$CheckNetwork)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
$c=$env:OM_F362_UART_CONTEXT|ConvertFrom-Json
if($c.schema -cne 'openmitrastar.f362-uart-context/v1' -or $c.purpose -cne 'single-serial-sysrq-reboot' -or $c.uart_port -cne 'COM3' -or $c.uart_pnp_device_id -ine 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -or $c.binding.NonceObserved -isnot [bool] -or -not $c.binding.NonceObserved -or $c.binding.ExpectedVersion -cne 'lyoko-foundation-6.9.9-f361-config-persistence-device' -or $c.initial_boot_id -cnotmatch '^[0-9a-f-]{36}$'){throw 'F362_UART_SCOPE'}
if([DateTimeOffset]::Parse($c.expires_at_utc) -le [DateTimeOffset]::UtcNow -or [DateTimeOffset]::Parse($c.created_at_utc) -gt [DateTimeOffset]::UtcNow){throw 'F362_UART_EXPIRED'}
if((Get-FileHash -LiteralPath $c.plan_path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $c.plan_sha256){throw 'F362_UART_PLAN'}
[void](Get-F319SerialDevice -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
[void](Assert-F319HardwareLease -PhysicalLockDir $c.physical_lock_dir -OwnerPid $c.owner_pid -OwnerStartTicks $c.owner_start_ticks -LeaseToken $c.lease_token -Port COM3 -ExpectedPnpDeviceId $c.uart_pnp_device_id)
if($CheckNetwork){. (Join-Path $PSScriptRoot 'f336_host_network.ps1');$p=Get-Content -LiteralPath $c.plan_path -Raw|ConvertFrom-Json;Assert-F336HostNetwork -Plan $p}
'PASS_F362_UART_CONTEXT'
