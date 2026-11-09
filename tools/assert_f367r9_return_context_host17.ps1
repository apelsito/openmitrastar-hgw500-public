param([switch]$CheckNetwork,[switch]$Admission)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
. (Join-Path $PSScriptRoot 'f367r9_return_context_host17.ps1')
$context=Assert-R9ReturnHost17Context -Admission:$Admission
if($CheckNetwork){
    $plan=Get-Content -LiteralPath $context.plan_path -Raw|ConvertFrom-Json
    [void](Assert-R9Host17Permission -Plan $plan)
    Assert-R9Host17Network -Plan $plan
}
'PASS_R9_RETURN_HOST17_CONTEXT'
