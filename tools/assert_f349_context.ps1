param([switch]$CheckNetwork)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
. (Join-Path $PSScriptRoot 'f349_hardware_context.ps1')
$c=Assert-F349Context
if($CheckNetwork){
    . (Join-Path $PSScriptRoot 'f336_host_network.ps1')
    $p=Get-Content -LiteralPath $c.plan_path -Raw|ConvertFrom-Json
    Assert-F336HostNetwork -Plan $p
}
'PASS_F349_PASSIVE_CONTEXT'
