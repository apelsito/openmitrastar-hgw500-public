Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f367r9_return_context.ps1')
. (Join-Path $PSScriptRoot 'f367r9_host17_guard.ps1')

function Assert-R9ReturnHost17Context {
    param([switch]$Admission)
    $context=Assert-R9ReturnContext -Admission:$Admission
    $plan=Get-Content -LiteralPath $context.plan_path -Raw|ConvertFrom-Json
    if($plan.host_binding_revision -cne 'r9-recovery-host17-v2' -or $plan.network.interface_index -ne 17){throw 'R9_HOST17_CONTEXT_REVISION'}
    [void](Assert-R9Host17ObservationFile -Plan $plan)
    return $context
}
