[CmdletBinding(PositionalBinding=$false)]
param([Parameter(Mandatory=$true)][string]$PlanPath,
      [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$PlanSha256,
      [ValidateSet('Inspect','Experiment')][string]$Mode='Inspect',[switch]$Execute)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
$actual=(Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash.ToLowerInvariant()
if($actual -cne $PlanSha256){throw 'F336_PLAN_HASH'}
$plan=Get-Content -LiteralPath $PlanPath -Raw | ConvertFrom-Json
if($plan.schema -cne 'openmitrastar.f336-executor/v1' -or $plan.flash_allowed -or $plan.status -cne 'REVIEWED_OFFLINE_READY'){throw 'F336_PLAN_SCOPE'}
foreach($p in $plan.sources.PSObject.Properties){if((Get-FileHash -LiteralPath $p.Name -Algorithm SHA256).Hash.ToLowerInvariant() -cne $p.Value){throw 'F336_SOURCE_DRIFT'}}
if(-not $Execute){[pscustomobject]@{status='OFFLINE_ONLY';mode=$Mode;hardware_actions=$false;plan_sha256=$actual}|ConvertTo-Json;return}
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
. (Join-Path $PSScriptRoot 'f321_ssh_guard.ps1')
. (Join-Path $PSScriptRoot 'f325_existing_firewall.ps1')
. (Join-Path $PSScriptRoot 'f336_ram_context.ps1')
. (Join-Path $PSScriptRoot 'f336_host_network.ps1')
$dir=Join-Path (Split-Path -Parent $PSScriptRoot) ('outputs\handoff-live\f336-ram-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8))
[void](New-Item -ItemType Directory -Path $dir)
$guard=$null;$prior=$env:OM_F336_RAM_CONTEXT;$childStarted=$false
try {
    [void](Assert-F325ExistingPermission -Plan $plan)
    Assert-F336HostNetwork -Plan $plan -RequireFreeUdp
    $guard=Enter-F319HardwareGuard -Port COM3 -ExpectedPnpDeviceId $plan.uart_pnp_device_id -PhysicalLockDir $plan.physical_lock_dir -Owner 'F336_RAM_WATCHDOG' -EvidenceDir $dir
    $binding=Assert-F319UartBinding -Port COM3 -ExpectedPnpDeviceId $plan.uart_pnp_device_id -RouterHost '192.168.1.90' -KnownHosts $plan.known_hosts -ExpectedVersion 'lyoko-foundation-6.8.5-f321-classic-ui-f314-device' -HardwareLease $guard
    $now=[DateTimeOffset]::UtcNow
    $context=[ordered]@{schema='openmitrastar.f336-ram-context/v1';purpose='ram-watchdog';candidate_sha256=$plan.kernel.sha256;flash_allowed=$false;
       created_at_utc=$now.ToString('o');expires_at_utc=$now.AddMinutes(30).ToString('o');owner_pid=$guard.OwnerPid;owner_start_ticks=$guard.OwnerStartTicks;
       lease_token=$guard.LeaseToken;physical_lock_dir=$guard.PhysicalLockDir;uart_port=$guard.Port;uart_pnp_device_id=$guard.PnpDeviceId;binding=$binding;plan_sha256=$actual;plan_path=[IO.Path]::GetFullPath($PlanPath)}
    $env:OM_F336_RAM_CONTEXT=$context|ConvertTo-Json -Depth 10 -Compress
    [void](Assert-F336Context)
    $argsList=@((Join-Path $PSScriptRoot 'f336_wdt_ram_executor.py'),'--execute','--plan',$PlanPath,'--plan-sha256',$actual,'--output-dir',$dir,'--mode',$Mode.ToLowerInvariant())
    $childStarted=$true;& $plan.network.python_executable @argsList
    $child=$LASTEXITCODE
    [void](Assert-F325ExistingPermission -Plan $plan)
    if($child -ne 0){throw "F336_EXECUTOR_RESULT_$child"}
} finally {
    $env:OM_F336_RAM_CONTEXT=$prior
    if($guard){
        $resultPath=Join-Path $dir 'result.json';$contained=-not $childStarted
        if(Test-Path -LiteralPath $resultPath){$r=Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json;$contained=$r.containment_confirmed -is [bool] -and $r.containment_confirmed}
        if($contained){Exit-F319HardwareGuard -Guard $guard}
        else {Write-Output 'F336_LOCK_DIRECTORY_LEFT_IN_PLACE_CONTAINMENT_UNPROVEN';Write-Warning 'Do not reuse this attempt. Physical lock directory remains as a barrier; owner process exit does not prove child containment.'}
    }
}
