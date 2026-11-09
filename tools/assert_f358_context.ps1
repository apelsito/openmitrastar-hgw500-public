param([switch]$CheckNetwork)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
. (Join-Path $PSScriptRoot 'f358_hardware_context.ps1')
$c=Assert-F358Context
if($CheckNetwork){
    . (Join-Path $PSScriptRoot 'f325_existing_firewall.ps1')
    . (Join-Path $PSScriptRoot 'f336_host_network.ps1')
    $p=Get-Content -LiteralPath $c.plan_path -Raw | ConvertFrom-Json
    [void](Assert-F325ExistingPermission -Plan $p)
    Assert-F336HostNetwork -Plan $p
}
'PASS_F358_INSTALL_CONTEXT'
