[CmdletBinding(PositionalBinding=$false)]
param([Parameter(Mandatory=$true)][string]$PlanPath,[Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$PlanSha256,[switch]$Execute)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
$F366Root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if((Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $PlanSha256){throw 'F366_PLAN_HASH'}
$plan=Get-Content -LiteralPath $PlanPath -Raw|ConvertFrom-Json
if($plan.schema -cne 'openmitrastar.f366-acquisition-plan/v1' -or $plan.status -cne 'PASS_OFFLINE_REVIEWED_EXECUTOR' -or $plan.erase_bytes -ne 0x5e0000 -or $plan.write_target -cne 'mtd4/linux_live'){throw 'F366_PLAN_SCOPE'}
if($plan.callback_authority -ne 0 -or $plan.diagnostic_channel -ne 36 -or $plan.diagnostic_bandwidth -ne 80 -or $plan.watchdog_session_ms -ne 180000 -or $plan.always_restore_f365 -isnot [bool] -or -not $plan.always_restore_f365 -or $plan.watchdog_arm_allowed -isnot [bool] -or -not $plan.watchdog_arm_allowed){throw 'F366_DIAGNOSTIC_SCOPE'}
if($plan.candidate_revision -cne 'f366r3' -or $plan.capture_revision -ne 2 -or $plan.images.f366.sha256 -cne 'ca66ddf07a6a1ef4470a77ca85c4151354e9d7dd831abc7e5f02c1a53a8b5d2d'){throw 'F366R3_EXACT_SCOPE'}
foreach($entry in $plan.sources.PSObject.Properties){if((Get-FileHash -LiteralPath $entry.Name -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value){throw 'F366_SOURCE_DRIFT'}}
if(-not $Execute){[pscustomobject]@{status='OFFLINE_ONLY';hardware_actions=$false;candidate_sha256=$plan.images.f366.sha256;rollback_sha256=$plan.images.f365.sha256}|ConvertTo-Json;return}
. (Join-Path $PSScriptRoot 'f366r3_source_freeze.ps1')
$f366r3Freeze=$null
try {
    $f366r3Freeze=Enter-F366R3SourceFreeze -PlanPath $PlanPath -PlanSha256 $PlanSha256 -Plan $plan
    Write-Output ('F366R3_FROZEN_FILES='+$f366r3Freeze.Count)
if($PSVersionTable.PSEdition -cne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5){throw 'F366_REQUIRES_WINDOWS_POWERSHELL_51'}
if(([IO.DriveInfo]::new('C')).AvailableFreeSpace -le 500MB -or ([IO.DriveInfo]::new('D')).AvailableFreeSpace -le 500MB){throw 'F366_DISK_ADMISSION_FLOOR'}
if([IO.Path]::GetFullPath($plan.evidence_root) -ine '/workspace/OpenMitraStar\f366-acquisition' -or -not (Test-Path -LiteralPath $plan.evidence_root -PathType Container)){throw 'F366_EVIDENCE_ROOT'}
$checkedDirectory=[IO.DirectoryInfo]::new($plan.evidence_root)
while($null -ne $checkedDirectory){if($checkedDirectory.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'F366_EVIDENCE_REPARSE'};$checkedDirectory=$checkedDirectory.Parent}
. (Join-Path $PSScriptRoot 'f321_mtd4_runtime.ps1')
. (Join-Path $PSScriptRoot 'f325_existing_firewall.ps1')
. (Join-Path $PSScriptRoot 'f336_host_network.ps1')
. (Join-Path $PSScriptRoot 'f366_hardware_context.ps1')
$dir=Join-Path $plan.evidence_root ('f366r3-acquisition-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8))
[void](New-Item -ItemType Directory -Path $dir)
$guard=$null;$launched=$false;$old=$env:OM_F366_CONTEXT
function Get-F366BootId {
    $ssh=Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
    $argv=@('-i',(Join-Path $env:USERPROFILE '.ssh/id_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o',('UserKnownHostsFile='+$plan.known_hosts),'-o','LogLevel=ERROR','root@192.168.1.90','sh','-s')
    $r=Invoke-F319SshScript -SshPath $ssh -Arguments $argv -Script 'cat /proc/sys/kernel/random/boot_id' -TimeoutSeconds 15
    if($r.ExitCode -ne 0 -or $r.Stderr -or $r.Stdout.Trim() -cnotmatch '^[0-9a-f-]{36}$'){throw 'F366_INITIAL_BOOT_ID'}
    return $r.Stdout.Trim()
}
try {
    [void](Assert-F325ExistingPermission -Plan $plan);Assert-F336HostNetwork -Plan $plan -RequireFreeUdp
    $guard=Enter-F319HardwareGuard -Port COM3 -ExpectedPnpDeviceId $plan.uart_pnp_device_id -PhysicalLockDir $plan.physical_lock_dir -Owner 'F366R3_ACQUISITION_F365_RETURN' -EvidenceDir $dir
    $before=Get-F366BootId
    $binding=Assert-F319UartBinding -Port COM3 -ExpectedPnpDeviceId $plan.uart_pnp_device_id -RouterHost '192.168.1.90' -KnownHosts $plan.known_hosts -ExpectedVersion $plan.images.f365.version -HardwareLease $guard
    if((Get-F366BootId) -cne $before){throw 'F366_BOOT_CHANGED_DURING_NONCE'}
    $now=[DateTimeOffset]::UtcNow
    $context=[ordered]@{schema='openmitrastar.f366-acquisition-context/v1';purpose='f366-acquisition-always-f365-return';candidate_sha256=$plan.images.f366.sha256;rollback_sha256=$plan.images.f365.sha256;prefix_bytes=0x5e0000;store_sha256=$plan.store.sha256;
      created_at_utc=$now.ToString('o');expires_at_utc=$now.AddMinutes(90).ToString('o');owner_pid=$guard.OwnerPid;owner_start_ticks=$guard.OwnerStartTicks;lease_token=$guard.LeaseToken;
      physical_lock_dir=$guard.PhysicalLockDir;uart_port=$guard.Port;uart_pnp_device_id=$guard.PnpDeviceId;binding=$binding;initial_boot_id=$before;plan_path=[IO.Path]::GetFullPath($PlanPath);plan_sha256=$PlanSha256}
    $env:OM_F366_CONTEXT=$context|ConvertTo-Json -Depth 10 -Compress
    [void](Assert-F366Context)
    Write-Output ('F366_RUN_DIRECTORY='+$dir)
    $launched=$true
    [void](Invoke-F321Native -Program $plan.network.python_executable -Arguments @((Join-Path $PSScriptRoot 'f366r3_acquisition_worker.py'),'--execute','--plan',$PlanPath,'--plan-sha256',$PlanSha256,'--output-dir',$dir) -LogPrefix (Join-Path $dir 'worker') -TimeoutSeconds 3600)
    [void](Assert-F325ExistingPermission -Plan $plan)
} finally {
    $env:OM_F366_CONTEXT=$old
    if($guard){
        $safe=-not $launched;$path=Join-Path $dir 'result.json'
        if(Test-Path -LiteralPath $path){$r=Get-Content -LiteralPath $path -Raw|ConvertFrom-Json;$safe=$r.containment_confirmed -is [bool] -and $r.containment_confirmed -and $r.retain_lease_required -is [bool] -and -not $r.retain_lease_required}
        if($script:F321ContainmentFailed){$safe=$false}
        if($safe){Exit-F319HardwareGuard -Guard $guard}else{Write-Warning 'F366 lock directory retained: containment or flash completion is unproven; no automatic retry'}
    }
}

} finally {
    if($f366r3Freeze){Exit-F366R3SourceFreeze -Freeze $f366r3Freeze}
}
