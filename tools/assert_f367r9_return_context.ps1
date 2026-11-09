param([switch]$CheckNetwork,[switch]$Admission)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
. (Join-Path $PSScriptRoot 'f367r9_return_context.ps1')
$context=Assert-R9ReturnContext -Admission:$Admission
if($CheckNetwork){
    . (Join-Path $PSScriptRoot 'f325_existing_firewall.ps1')
    . (Join-Path $PSScriptRoot 'f336_host_network.ps1')
    $plan=Get-Content -LiteralPath $context.plan_path -Raw|ConvertFrom-Json
    [void](Assert-F325ExistingPermission -Plan $plan)
    Assert-F336HostNetwork -Plan $plan
}
'PASS_R9_RETURN_CONTEXT'
