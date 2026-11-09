param([switch]$CheckNetwork)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
. (Join-Path $PSScriptRoot 'f360_hardware_context.ps1')
$c=Assert-F360Context
if($CheckNetwork){. (Join-Path $PSScriptRoot 'f336_host_network.ps1');$p=Get-Content -LiteralPath $c.plan_path -Raw|ConvertFrom-Json;Assert-F336HostNetwork -Plan $p}
'PASS_F360_SAVE_CONTEXT'
