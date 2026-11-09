param([switch]$CheckNetwork,[switch]$CheckTransfer)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
. (Join-Path $PSScriptRoot 'f356_hardware_context.ps1')
$c=Assert-F356Context
if($CheckNetwork -or $CheckTransfer){
 . (Join-Path $PSScriptRoot 'f336_host_network.ps1')
 $p=Get-Content -LiteralPath $c.plan_path -Raw|ConvertFrom-Json
 Assert-F336HostNetwork -Plan $p
 if($CheckTransfer){. (Join-Path $PSScriptRoot 'f325_existing_firewall.ps1');[void](Assert-F325ExistingPermission -Plan $p)}
}
'PASS_F356_OBSERVE_CONTEXT'
