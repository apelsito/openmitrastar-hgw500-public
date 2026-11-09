[CmdletBinding(PositionalBinding=$false)]
param([Parameter(Mandatory=$true)][string]$PlanPath,[Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$PlanSha256,[switch]$Execute)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
$F367Root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if((Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $PlanSha256){throw 'F367_PLAN_HASH'}
$plan=Get-Content -LiteralPath $PlanPath -Raw|ConvertFrom-Json
if($plan.schema -cne 'openmitrastar.f367-campaign-plan/v1' -or $plan.status -cne 'PASS_OFFLINE_REVIEWED_EXECUTOR' -or $plan.erase_bytes -ne 0x5e0000 -or $plan.write_target -cne 'mtd4/linux_live'){throw 'F367_PLAN_SCOPE'}
if($plan.callback_authority -ne 1 -or $plan.dfs_primary -ne 52 -or $plan.dfs_bandwidth -ne 20 -or $plan.watchdog_session_ms -ne 5400000 -or $plan.outer_timeout_seconds -ne 7500 -or $plan.context_ttl_seconds -ne 7800 -or $plan.always_restore_f365 -isnot [bool] -or -not $plan.always_restore_f365 -or $plan.watchdog_arm_allowed -isnot [bool] -or -not $plan.watchdog_arm_allowed){throw 'F367_DIAGNOSTIC_SCOPE'}
if($plan.uart_semantic_capture_revision -ne 2 -or $plan.repeat_scope -cne 'one-f367r5-regulatory-profile-trial' -or $plan.max_completed_executions -ne 1){throw 'F367_CAPTURE_REPEAT_SCOPE'}
if($plan.runtime_revision -cne 'F367r5' -or $plan.activate_timeout_seconds -ne 240){throw 'F367R5_BINDING_SCOPE'}
if($plan.host_phase_gate_revision -ne 2){throw 'F367_PHASE_GATE_SCOPE'}
if($plan.initial_target52_readback_required -isnot [bool] -or -not $plan.initial_target52_readback_required){throw 'F367R5_PROFILE_SCOPE'}
if($plan.readonly_guard_revision -ne 3 -or $plan.readonly_guard_retries -ne 1){throw 'F367_READONLY_GUARD_SCOPE'}
foreach($entry in $plan.sources.PSObject.Properties){if((Get-FileHash -LiteralPath $entry.Name -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value){throw 'F367_SOURCE_DRIFT'}}
if(-not $Execute){[pscustomobject]@{status='OFFLINE_ONLY';hardware_actions=$false;candidate_sha256=$plan.images.f367.sha256;rollback_sha256=$plan.images.f365.sha256}|ConvertTo-Json;return}
if(Test-Path -LiteralPath (Join-Path (Join-Path $plan.evidence_root 'one-shot-plans') ($PlanSha256+'.json'))){throw 'F367_CAPTURE_PLAN_ALREADY_CONSUMED'}
. (Join-Path $PSScriptRoot 'f366r3_source_freeze.ps1')
$f367Freeze=$null;$f367PreviousPower=$null
try {
    $f367Freeze=Enter-F366R3SourceFreeze -PlanPath $PlanPath -PlanSha256 $PlanSha256 -Plan $plan
    Write-Output ('F367_FROZEN_FILES='+$f367Freeze.Count)
if($PSVersionTable.PSEdition -cne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5){throw 'F367_REQUIRES_WINDOWS_POWERSHELL_51'}
if(-not ('F367ExecutionState' -as [type])){Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class F367ExecutionState { [DllImport("kernel32.dll", SetLastError=true)] public static extern UInt32 SetThreadExecutionState(UInt32 flags); }'}
$f367PreviousPower=[F367ExecutionState]::SetThreadExecutionState([uint32]2147483649)
if($f367PreviousPower -eq 0){throw 'F367_KEEP_AWAKE_FAILED'}
if(([IO.DriveInfo]::new('C')).AvailableFreeSpace -le 500MB -or ([IO.DriveInfo]::new('D')).AvailableFreeSpace -le 500MB){throw 'F367_DISK_ADMISSION_FLOOR'}
if([IO.Path]::GetFullPath($plan.evidence_root) -ine '/workspace/OpenMitraStar\f367-campaign' -or -not (Test-Path -LiteralPath $plan.evidence_root -PathType Container)){throw 'F367_EVIDENCE_ROOT'}
$checkedDirectory=[IO.DirectoryInfo]::new($plan.evidence_root)
while($null -ne $checkedDirectory){if($checkedDirectory.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'F367_EVIDENCE_REPARSE'};$checkedDirectory=$checkedDirectory.Parent}
. (Join-Path $PSScriptRoot 'f321_mtd4_runtime.ps1')
. (Join-Path $PSScriptRoot 'f325_existing_firewall.ps1')
. (Join-Path $PSScriptRoot 'f336_host_network.ps1')
. (Join-Path $PSScriptRoot 'f367_hardware_context.ps1')
$dir=Join-Path $plan.evidence_root ('f367r5-campaign-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8))
[void](New-Item -ItemType Directory -Path $dir)
$guard=$null;$launched=$false;$old=$env:OM_F367_CONTEXT
function Get-F367BootId {
    $ssh=Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
    $argv=@('-i',(Join-Path $env:USERPROFILE '.ssh/id_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o',('UserKnownHostsFile='+$plan.known_hosts),'-o','LogLevel=ERROR','root@192.168.1.90','sh','-s')
    $r=Invoke-F319SshScript -SshPath $ssh -Arguments $argv -Script 'cat /proc/sys/kernel/random/boot_id' -TimeoutSeconds 15
    if($r.ExitCode -ne 0 -or $r.Stderr -or $r.Stdout.Trim() -cnotmatch '^[0-9a-f-]{36}$'){throw 'F367_INITIAL_BOOT_ID'}
    return $r.Stdout.Trim()
}
try {
    [void](Assert-F325ExistingPermission -Plan $plan);Assert-F336HostNetwork -Plan $plan -RequireFreeUdp
    $guard=Enter-F319HardwareGuard -Port COM3 -ExpectedPnpDeviceId $plan.uart_pnp_device_id -PhysicalLockDir $plan.physical_lock_dir -Owner 'F367_ACQUISITION_F365_RETURN' -EvidenceDir $dir
    $before=Get-F367BootId
    $binding=Assert-F319UartBinding -Port COM3 -ExpectedPnpDeviceId $plan.uart_pnp_device_id -RouterHost '192.168.1.90' -KnownHosts $plan.known_hosts -ExpectedVersion $plan.images.f365.version -HardwareLease $guard
    if((Get-F367BootId) -cne $before){throw 'F367_BOOT_CHANGED_DURING_NONCE'}
    $now=[DateTimeOffset]::UtcNow
    $context=[ordered]@{schema='openmitrastar.f367-campaign-context/v1';purpose='f367-campaign-always-f365-return';candidate_sha256=$plan.images.f367.sha256;rollback_sha256=$plan.images.f365.sha256;prefix_bytes=0x5e0000;store_sha256=$plan.store.sha256;
      created_at_utc=$now.ToString('o');expires_at_utc=$now.AddMinutes(130).ToString('o');owner_pid=$guard.OwnerPid;owner_start_ticks=$guard.OwnerStartTicks;lease_token=$guard.LeaseToken;
      physical_lock_dir=$guard.PhysicalLockDir;uart_port=$guard.Port;uart_pnp_device_id=$guard.PnpDeviceId;binding=$binding;initial_boot_id=$before;plan_path=[IO.Path]::GetFullPath($PlanPath);plan_sha256=$PlanSha256}
    $env:OM_F367_CONTEXT=$context|ConvertTo-Json -Depth 10 -Compress
    [void](Assert-F367Context)
    Write-Output ('F367_RUN_DIRECTORY='+$dir)
    $launched=$true
    [void](Invoke-F321Native -Program $plan.network.python_executable -Arguments @((Join-Path $PSScriptRoot 'f367r5_campaign_worker.py'),'--execute','--plan',$PlanPath,'--plan-sha256',$PlanSha256,'--output-dir',$dir) -LogPrefix (Join-Path $dir 'worker') -TimeoutSeconds 7500)
    [void](Assert-F325ExistingPermission -Plan $plan)
} finally {
    $env:OM_F367_CONTEXT=$old
    if($guard){
        $safe=-not $launched;$path=Join-Path $dir 'result.json'
        if(Test-Path -LiteralPath $path){$r=Get-Content -LiteralPath $path -Raw|ConvertFrom-Json;$safe=$r.containment_confirmed -is [bool] -and $r.containment_confirmed -and $r.retain_lease_required -is [bool] -and -not $r.retain_lease_required}
        if($script:F321ContainmentFailed){$safe=$false}
        if($safe){Exit-F319HardwareGuard -Guard $guard}else{Write-Warning 'F367 lock directory retained: containment or flash completion is unproven; no automatic retry'}
    }
}

} finally {
    if($null -ne $f367PreviousPower -and $f367PreviousPower -ne 0){[void][F367ExecutionState]::SetThreadExecutionState([uint32]$f367PreviousPower)}
    if($f367Freeze){Exit-F366R3SourceFreeze -Freeze $f367Freeze}
}
