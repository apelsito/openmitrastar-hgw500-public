$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
. (Join-Path $PSScriptRoot 'f336_ram_context.ps1')
$c=Assert-F336Context
if((Get-FileHash -LiteralPath $c.plan_path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $c.plan_sha256){throw 'F336_CONTEXT_PLAN_DRIFT'}
$p=Get-Content -LiteralPath $c.plan_path -Raw | ConvertFrom-Json
. (Join-Path $PSScriptRoot 'f325_existing_firewall.ps1')
. (Join-Path $PSScriptRoot 'f336_host_network.ps1')
[void](Assert-F325ExistingPermission -Plan $p)
Assert-F336HostNetwork -Plan $p
'PASS_F336_RAM_CONTEXT'
