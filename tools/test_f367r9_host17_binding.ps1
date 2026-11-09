[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$OutputDir)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f367r9_host17_guard.ps1')
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$out=Assert-R9ReturnPath $OutputDir -MayNotExist
if(-not $out.StartsWith((Join-Path $root 'outputs\preflight\'),[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $out)){throw 'NEW_SCOPED_TEST_DIR_REQUIRED'}
[void](New-Item -ItemType Directory -Path $out)
$plan=Get-Content -LiteralPath (Join-Path $root 'outputs\preflight\r9-return-f365-20260923T081235Z\plan.json') -Raw|ConvertFrom-Json
$original=ConvertTo-R9Host17Map $plan.network.existing_permission.projection
$current=ConvertTo-R9Host17Map $original;$current.connection_interface_index='17'
$comparison=Assert-R9Host17Projection -Original $original -Current $current
if($comparison.changed_fields.Count -ne 1 -or $comparison.changed_fields[0] -cne 'connection_interface_index'){throw 'ALLOWED_DIFFERENCE_NOT_EXACT'}
$checks=1
foreach($key in $original.Keys){
    $bad=ConvertTo-R9Host17Map $current;$bad[$key]='changed-for-test'
    $rejected=$false
    try{[void](Assert-R9Host17Projection -Original $original -Current $bad)}catch{$rejected=$true}
    if(-not $rejected){throw ('UNRELATED_CHANGE_ACCEPTED_'+$key)}
    $checks++
}
$bad=ConvertTo-R9Host17Map $current;$bad['extra']='field'
$rejected=$false;try{[void](Assert-R9Host17Projection -Original $original -Current $bad)}catch{$rejected=$true};if(-not $rejected){throw 'EXTRA_FIELD_ACCEPTED'};$checks++
$bad=ConvertTo-R9Host17Map $current;$bad.Remove('action')
$rejected=$false;try{[void](Assert-R9Host17Projection -Original $original -Current $bad)}catch{$rejected=$true};if(-not $rejected){throw 'MISSING_FIELD_ACCEPTED'};$checks++
$old=([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'f325_existing_firewall.ps1'))).Replace("`r`n","`n")
$old=$old.Substring($old.IndexOf('function Get-F325ExistingPermissionSnapshot {'))
$new=([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'f367r9_host17_guard.ps1'))).Replace("`r`n","`n")
$new=$new.Substring($new.IndexOf('function Get-R9Host17PermissionSnapshot {'))
$expected=$old.Replace('Get-F325ExistingPermissionSnapshot','Get-R9Host17PermissionSnapshot').Replace('-ne 18','-ne 17').Replace('-InterfaceIndex 18','-InterfaceIndex 17').Replace('Ethernet .49/18','Ethernet .49/17')
if($new -cne $expected){throw 'SNAPSHOT_CHANGED_BEYOND_INDEX_AND_FUNCTION_NAME'};$checks++

# Fake host cmdlets only. The test never queries live adapters or firewall.
$script:case='pass'
function Get-NetAdapter {
    [CmdletBinding()]param([switch]$IncludeHidden)
    [pscustomobject]@{ifIndex=17;Name='Ethernet';Status='Up';MediaType='802.3';InterfaceDescription='Synthetic Realtek fixture';InterfaceGuid=$(if($script:case -ceq 'guid'){'00000000-0000-0000-0000-000000000001'}else{'b75315d5-9f01-448f-a259-c9d8f25d2233'})}
}
function Get-CimInstance {
    [CmdletBinding()]param([Parameter(Position=0)][string]$ClassName,[string]$Filter)
    [pscustomobject]@{GUID='{B75315D5-9F01-448F-A259-C9D8F25D2233}';PNPDeviceID=$(if($script:case -ceq 'pnp'){'OTHER'}else{'PCI\VEN_10EC&DEV_8168&SUBSYS_E0001458&REV_16\6E8F9B4DC018000000'});NetConnectionID='Ethernet';Speed=1000000000;NetEnabled=$true;Name='Synthetic device'}
}
function Get-NetIPAddress {
    [CmdletBinding()]param([int]$InterfaceIndex=0,[string]$AddressFamily)
    if($InterfaceIndex -eq 17 -or $InterfaceIndex -eq 0){[pscustomobject]@{InterfaceIndex=17;IPAddress=$(if($script:case -ceq 'address'){'192.168.1.50'}else{'192.168.1.49'});PrefixLength=24;AddressState='Preferred';SkipAsSource=$false}}
    if($InterfaceIndex -eq 0 -and $script:case -ceq 'old-index'){[pscustomobject]@{InterfaceIndex=18;IPAddress='192.168.1.48'}}
}
function Find-NetRoute {
    [CmdletBinding()]param([string]$RemoteIPAddress)
    [pscustomobject]@{IPAddress='192.168.1.49';InterfaceIndex=17}
    [pscustomobject]@{InterfaceIndex=17;DestinationPrefix='192.168.1.0/24';NextHop=$(if($script:case -ceq 'route'){'192.168.1.1'}else{'0.0.0.0'})}
}
function Get-NetUDPEndpoint {
    [CmdletBinding()]param()
    if($script:case -ceq 'udp'){[pscustomobject]@{LocalPort=69}}
}
[void](Get-R9Host17NetworkSnapshot -RequireFreeUdp);$checks++
foreach($script:case in @('guid','pnp','address','old-index','route','udp')){
    $rejected=$false;try{[void](Get-R9Host17NetworkSnapshot -RequireFreeUdp)}catch{$rejected=$true}
    if(-not $rejected){throw ('HOST_DRIFT_ACCEPTED_'+$script:case)};$checks++
}
$pins=@{}
foreach($name in @('test_f367r9_host17_binding.ps1','f367r9_host17_guard.ps1','collect_f367r9_host17_binding.ps1','f325_existing_firewall.ps1','f367r9_return_context.ps1')){
    $file=Join-Path $PSScriptRoot $name;$pins[$file]=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
}
$result=@{status='PASS_R9_HOST17_BINDING_TESTS';checks=$checks;host_observation=$false;device_access=$false;host_mutation=$false;hardware_actions=$false;source_pins=$pins}
[IO.File]::WriteAllText((Join-Path $out 'result.json'),($result|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
$result|ConvertTo-Json -Depth 5
