[CmdletBinding(PositionalBinding=$false)]
param([Parameter(Mandatory=$true)][string]$PlanPath,[Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$PlanSha256,[switch]$Execute)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
$F346Root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if((Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $PlanSha256){throw 'F346_PLAN_HASH'}
$plan=Get-Content -LiteralPath $PlanPath -Raw|ConvertFrom-Json
if($plan.schema -cne 'openmitrastar.f346-install-plan/v1' -or $plan.status -cne 'PASS_OFFLINE_REVIEWED_EXECUTOR' -or $plan.erase_bytes -ne 0x5e0000 -or $plan.write_target -cne 'mtd4/linux_live'){throw 'F346_PLAN_SCOPE'}
foreach($entry in $plan.sources.PSObject.Properties){if((Get-FileHash -LiteralPath $entry.Name -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value){throw 'F346_SOURCE_DRIFT'}}
if(-not $Execute){[pscustomobject]@{status='OFFLINE_ONLY';hardware_actions=$false;candidate_sha256=$plan.images.f340.sha256;rollback_sha256=$plan.images.f321.sha256}|ConvertTo-Json;return}
. (Join-Path $PSScriptRoot 'f321_mtd4_runtime.ps1')
. (Join-Path $PSScriptRoot 'f325_existing_firewall.ps1')
. (Join-Path $PSScriptRoot 'f336_host_network.ps1')
. (Join-Path $PSScriptRoot 'f346_hardware_context.ps1')
$dir=Join-Path $F346Root ('outputs\handoff-live\f346-install-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8))
[void](New-Item -ItemType Directory -Path $dir)
$guard=$null;$launched=$false;$old=$env:OM_F346_CONTEXT
function Get-F346BootId {
    $ssh=Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
    $argv=@('-i',(Join-Path $env:USERPROFILE '.ssh/id_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o',('UserKnownHostsFile='+$plan.known_hosts),'-o','LogLevel=ERROR','root@192.168.1.90','sh','-s')
    $r=Invoke-F319SshScript -SshPath $ssh -Arguments $argv -Script 'cat /proc/sys/kernel/random/boot_id' -TimeoutSeconds 15
    if($r.ExitCode -ne 0 -or $r.Stderr -or $r.Stdout.Trim() -cnotmatch '^[0-9a-f-]{36}$'){throw 'F346_INITIAL_BOOT_ID'}
    return $r.Stdout.Trim()
}
try {
    [void](Assert-F325ExistingPermission -Plan $plan);Assert-F336HostNetwork -Plan $plan -RequireFreeUdp
    $guard=Enter-F319HardwareGuard -Port COM3 -ExpectedPnpDeviceId $plan.uart_pnp_device_id -PhysicalLockDir $plan.physical_lock_dir -Owner 'F346_F340_INSTALL' -EvidenceDir $dir
    $before=Get-F346BootId
    $binding=Assert-F319UartBinding -Port COM3 -ExpectedPnpDeviceId $plan.uart_pnp_device_id -RouterHost '192.168.1.90' -KnownHosts $plan.known_hosts -ExpectedVersion $plan.images.f321.version -HardwareLease $guard
    if((Get-F346BootId) -cne $before){throw 'F346_BOOT_CHANGED_DURING_NONCE'}
    $now=[DateTimeOffset]::UtcNow
    $context=[ordered]@{schema='openmitrastar.f346-install-context/v1';purpose='f340-install-conditional-f321-return';candidate_sha256=$plan.images.f340.sha256;rollback_sha256=$plan.images.f321.sha256;prefix_bytes=0x5e0000;
      created_at_utc=$now.ToString('o');expires_at_utc=$now.AddMinutes(90).ToString('o');owner_pid=$guard.OwnerPid;owner_start_ticks=$guard.OwnerStartTicks;lease_token=$guard.LeaseToken;
      physical_lock_dir=$guard.PhysicalLockDir;uart_port=$guard.Port;uart_pnp_device_id=$guard.PnpDeviceId;binding=$binding;initial_boot_id=$before;plan_path=[IO.Path]::GetFullPath($PlanPath);plan_sha256=$PlanSha256}
    $env:OM_F346_CONTEXT=$context|ConvertTo-Json -Depth 10 -Compress
    [void](Assert-F346Context)
    Write-Output ('F346_RUN_DIRECTORY='+$dir)
    $launched=$true
    [void](Invoke-F321Native -Program $plan.network.python_executable -Arguments @((Join-Path $PSScriptRoot 'f346_install_executor.py'),'--execute','--plan',$PlanPath,'--plan-sha256',$PlanSha256,'--output-dir',$dir) -LogPrefix (Join-Path $dir 'worker') -TimeoutSeconds 3600)
    [void](Assert-F325ExistingPermission -Plan $plan)
} finally {
    $env:OM_F346_CONTEXT=$old
    if($guard){
        $safe=-not $launched;$path=Join-Path $dir 'result.json'
        if(Test-Path -LiteralPath $path){$r=Get-Content -LiteralPath $path -Raw|ConvertFrom-Json;$safe=$r.containment_confirmed -is [bool] -and $r.containment_confirmed -and $r.retain_lease_required -is [bool] -and -not $r.retain_lease_required}
        if($script:F321ContainmentFailed){$safe=$false}
        if($safe){Exit-F319HardwareGuard -Guard $guard}else{Write-Warning 'F346 lock directory retained: containment or flash completion is unproven; no automatic retry'}
    }
}
