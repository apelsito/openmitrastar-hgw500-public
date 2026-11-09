[CmdletBinding(PositionalBinding=$false)]
param([Parameter(Mandatory=$true)][string]$OutputDir,[switch]$Observe)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f367r9_host17_guard.ps1')
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$previous=Join-Path $root 'outputs\preflight\r9-return-f365-20260923T081235Z\plan.json'
if((Get-FileHash -LiteralPath $previous -Algorithm SHA256).Hash.ToLowerInvariant() -cne '6cbc06e281b36dcdbe282c96a063b67424816d74b7ed10bb9c25929792594f5e'){throw 'R9_HOST17_PREVIOUS_PLAN_HASH'}
$plan=Get-Content -LiteralPath $previous -Raw|ConvertFrom-Json
Assert-F325ExistingPermissionPlan -Plan $plan
if(-not $Observe){[pscustomobject]@{status='OFFLINE_HOST17_COLLECTOR';host_observation=$false;device_access=$false;host_mutation=$false}|ConvertTo-Json;return}
if($PSVersionTable.PSEdition -cne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5){throw 'R9_HOST17_WINDOWS_POWERSHELL51_REQUIRED'}
$out=Assert-R9ReturnPath $OutputDir -MayNotExist
if(-not $out.StartsWith((Join-Path $root 'outputs\preflight\'),[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $out)){throw 'R9_HOST17_NEW_SCOPED_OUTPUT_REQUIRED'}
[void](New-Item -ItemType Directory -Path $out)
$record=[ordered]@{schema='openmitrastar.r9-host17-observation/v1';status='FAILED_HOST17_BINDING';observed_utc=[DateTime]::UtcNow.ToString('o');
    device_access=$false;host_mutation=$false;firewall_mutation=$false;address_route_mutation=$false;listener_started=$false;
    previous_plan_sha256='6cbc06e281b36dcdbe282c96a063b67424816d74b7ed10bb9c25929792594f5e';cause_of_r9_failure='NOT_ATTESTED';source_pins=@{}}
try {
    $plan.network.interface_index=17
    $record.permission=Get-R9Host17PermissionSnapshot -Plan $plan
    $record.comparison=Assert-R9Host17Projection -Original $plan.network.existing_permission.projection -Current $record.permission.projection
    $record.network=Get-R9Host17NetworkSnapshot -RequireFreeUdp
    foreach($name in @('collect_f367r9_host17_binding.ps1','f367r9_host17_guard.ps1','f325_existing_firewall.ps1','f367r9_return_context.ps1')){
        $file=Join-Path $PSScriptRoot $name;$record.source_pins[$file]=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $record.status='PASS_HOST17_ONLY_INDEX_REBIND'
}catch{$record.error=$_.Exception.Message}
[IO.File]::WriteAllText((Join-Path $out 'result.json'),($record|ConvertTo-Json -Depth 15),[Text.UTF8Encoding]::new($false))
[pscustomobject]@{status=$record.status;result=(Join-Path $out 'result.json');sha256=(Get-FileHash -LiteralPath (Join-Path $out 'result.json') -Algorithm SHA256).Hash.ToLowerInvariant();device_access=$false;host_mutation=$false}|ConvertTo-Json
if($record.status -cne 'PASS_HOST17_ONLY_INDEX_REBIND'){exit 1}
