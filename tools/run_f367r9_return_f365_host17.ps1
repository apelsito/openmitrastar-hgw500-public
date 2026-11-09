[CmdletBinding(PositionalBinding=$false)]
param(
    [Parameter(Mandatory=$true)][string]$PlanPath,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$PlanSha256,
    [string]$FreshBootId='',
    [switch]$Execute
)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f367r9_return_context_host17.ps1')
$PlanPath=Assert-R9ReturnPath $PlanPath
if((Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $PlanSha256){throw 'R9_PLAN_HASH'}
$plan=Get-Content -LiteralPath $PlanPath -Raw|ConvertFrom-Json
if($plan.schema -cne 'openmitrastar.f367r9-return-f365-plan/v1' -or $plan.status -cne 'PASS_OFFLINE_RETURN_PLAN'){throw 'R9_PLAN_SCHEMA'}
foreach($item in $plan.sources.PSObject.Properties){
    [void](Assert-R9ReturnPath $item.Name)
    if((Get-FileHash -LiteralPath $item.Name -Algorithm SHA256).Hash.ToLowerInvariant() -cne $item.Value){throw 'R9_SOURCE_DRIFT'}
}
$python=Assert-R9ReturnPath $plan.network.python_executable
$worker=Join-Path $PSScriptRoot 'f367r9_return_f365_host17.py'
# This process validates only files. No device/network/mutex API precedes Execute.
& $python $worker --plan $PlanPath --plan-sha256 $PlanSha256
if($LASTEXITCODE -ne 0){throw 'R9_OFFLINE_PLAN_INVALID'}
if(-not $Execute){return}
if($PSVersionTable.PSEdition -cne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5){throw 'R9_WINDOWS_POWERSHELL51_REQUIRED'}
if($FreshBootId -cnotmatch '^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$' -or $FreshBootId -ceq 'cf18e917-7a46-4a60-a352-eef2572adff7'){throw 'R9_FRESH_ROOT_OBSERVED_BOOT_ID_REQUIRED'}
. (Join-Path $PSScriptRoot 'f321_mtd4_runtime.ps1')
. (Join-Path $PSScriptRoot 'f367r9_host17_guard.ps1')
. (Join-Path $PSScriptRoot 'f366r3_source_freeze.ps1')
$parent=Assert-R9ReturnPath $plan.physical_lock_dir
$ownerPath=Assert-R9ReturnPath (Join-Path $parent 'owner.json')
$evidenceRoot=Assert-R9ReturnPath $plan.evidence_root
if($evidenceRoot -ine '/workspace/OpenMitraStar\f367-recovery'){throw 'R9_EVIDENCE_ROOT'}
$runName='r9-return-f365-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8)
$out=Assert-R9ReturnPath (Join-Path $evidenceRoot $runName) -MayNotExist
$child=Join-Path $parent 'r9-return-f365.lock'
$archive=Assert-R9ReturnPath (Join-Path (Split-Path -Parent $parent) ($runName+'-retired-quarantine')) -MayNotExist
$guard=$null;$parentStream=$null;$freeze=$null;$power=$null;$launched=$false;$safe=$false;$old=$env:OM_R9_RETURN_CONTEXT
$final=[ordered]@{schema='openmitrastar.r9-return-launcher/v1';status='FAILED_PARENT_QUARANTINE_RETAINED';parent_quarantine_retained=$true;metadata_archived=$false;hardware_worker_started=$false}
function Assert-R9OldOwner {
    $owner=Get-Content -LiteralPath $ownerPath -Raw|ConvertFrom-Json
    if($owner.schema -cne 'openmitrastar.physical-lock/v3' -or $owner.owner -cne 'F367_ACQUISITION_F365_RETURN' -or
       $owner.pid -ne 38908 -or $owner.process_start_ticks -ne 639257141569704476 -or $owner.uart_port -cne 'COM3' -or
       $owner.uart_pnp_device_id -ine $plan.uart_pnp_device_id -or
       [IO.Path]::GetFullPath($owner.evidence_dir) -ine [IO.Path]::GetDirectoryName($plan.failed_result.path)){throw 'R9_RETAINED_OWNER_MISMATCH'}
    if((Get-FileHash -LiteralPath $ownerPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $plan.parent_lease.sha256){throw 'R9_RETAINED_OWNER_CHANGED'}
    $oldProcess=Get-Process -Id 38908 -ErrorAction SilentlyContinue
    if($oldProcess){try{if(-not $oldProcess.HasExited -and $oldProcess.StartTime.ToUniversalTime().Ticks -eq 639257141569704476){throw 'R9_ORIGINAL_OWNER_RUNNING'}}finally{$oldProcess.Dispose()}}
}
try {
    if(Test-Path -LiteralPath $out){throw 'R9_IMMUTABLE_EVIDENCE_REQUIRED'}
    [void](New-Item -ItemType Directory -Path $out)
    $freeze=Enter-F366R3SourceFreeze -PlanPath $PlanPath -PlanSha256 $PlanSha256 -Plan $plan
    if(([IO.DriveInfo]::new('C')).AvailableFreeSpace -lt 500MB -or ([IO.DriveInfo]::new('D')).AvailableFreeSpace -lt 500MB){throw 'R9_DISK_FLOOR'}
    if(-not ('R9ReturnPower' -as [type])){Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class R9ReturnPower { [DllImport("kernel32.dll")] public static extern UInt32 SetThreadExecutionState(UInt32 flags); }'}
    $power=[R9ReturnPower]::SetThreadExecutionState([uint32]2147483649)
    if($power -eq 0){throw 'R9_KEEP_AWAKE_FAILED'}
    $parentStream=[IO.File]::Open($ownerPath,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    Assert-R9OldOwner
    # Both original mutexes are held throughout admission, return and archival.
    $guard=Enter-F319HardwareGuard -Port COM3 -ExpectedPnpDeviceId $plan.uart_pnp_device_id -PhysicalLockDir $child -Owner 'R9_RECOVERY_EXACT_F365_ONLY' -EvidenceDir $out
    Assert-R9OldOwner
    [void](Assert-R9Host17Permission -Plan $plan);Assert-R9Host17Network -Plan $plan -RequireFreeUdp
    $now=[DateTimeOffset]::UtcNow
    $context=[ordered]@{schema='openmitrastar.f367r9-return-f365-context/v1';phase='admission';initial_boot_id=$FreshBootId;binding=$null;
        created_at_utc=$now.ToString('o');expires_at_utc=$now.AddSeconds(3600).ToString('o');plan_path=$PlanPath;plan_sha256=$PlanSha256;
        parent_owner_sha256=$plan.parent_lease.sha256;physical_lock_dir=$child;owner_pid=$guard.OwnerPid;owner_start_ticks=$guard.OwnerStartTicks;lease_token=$guard.LeaseToken}
    $env:OM_R9_RETURN_CONTEXT=$context|ConvertTo-Json -Depth 10 -Compress
    [void](Assert-R9ReturnHost17Context -Admission)
    [void](Invoke-F321Native -Program $python -Arguments @($worker,'--admit','--plan',$PlanPath,'--plan-sha256',$PlanSha256,'--fresh-boot-id',$FreshBootId,'--output-dir',$out) -LogPrefix (Join-Path $out 'admission-worker') -TimeoutSeconds 300)
    $admissionPath=Join-Path $out 'admission.json'
    $admission=Get-Content -LiteralPath $admissionPath -Raw|ConvertFrom-Json
    $age=([DateTimeOffset]::UtcNow-[DateTimeOffset]::Parse($admission.observed_utc)).TotalSeconds
    if($admission.status -cne 'PASS_FRESH_R9_QUIESCENT' -or $admission.identity.boot_id -cne $FreshBootId -or $age -lt 0 -or $age -gt 30){throw 'R9_ADMISSION_NOT_FRESH'}
    $binding=Assert-F319UartBinding -Port COM3 -ExpectedPnpDeviceId $plan.uart_pnp_device_id -RouterHost '192.168.1.90' -KnownHosts $plan.known_hosts -ExpectedVersion $plan.images.f367.version -HardwareLease $guard
    $context.phase='bound';$context.binding=$binding;$context.admission_path=$admissionPath;$context.admission_sha256=(Get-FileHash -LiteralPath $admissionPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $env:OM_R9_RETURN_CONTEXT=$context|ConvertTo-Json -Depth 10 -Compress
    [void](Assert-R9ReturnHost17Context)
    $claim=Join-Path $parent 'r9-return-attempt.json'
    # CreateNew refuses a second recovery attempt even if the prior PID died.
    $claimStream=[IO.File]::Open($claim,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try{$bytes=[Text.Encoding]::UTF8.GetBytes((@{plan_sha256=$PlanSha256;boot_id=$FreshBootId;evidence_dir=$out;created_utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json));$claimStream.Write($bytes,0,$bytes.Length);$claimStream.Flush($true)}finally{$claimStream.Dispose()}
    $launched=$true;$final.hardware_worker_started=$true
    [void](Invoke-F321Native -Program $python -Arguments @($worker,'--execute','--plan',$PlanPath,'--plan-sha256',$PlanSha256,'--fresh-boot-id',$FreshBootId,'--output-dir',$out) -LogPrefix (Join-Path $out 'return-worker') -TimeoutSeconds 3000)
    $result=Get-Content -LiteralPath (Join-Path $out 'result.json') -Raw|ConvertFrom-Json
    $safe=$result.status -ceq 'PASS_R9_EXACT_F365_RETURN' -and $result.f365_return_confirmed -is [bool] -and $result.f365_return_confirmed -and
        $result.containment_confirmed -is [bool] -and $result.containment_confirmed -and $result.retain_lease_required -is [bool] -and -not $result.retain_lease_required -and
        $result.flash_command_in_flight -is [bool] -and -not $result.flash_command_in_flight -and -not $script:F321ContainmentFailed
    if(-not $safe){throw 'R9_RETURN_UNPROVEN'}
    [void](Assert-R9ReturnHost17Context)
    Assert-R9OldOwner
    if(Test-Path -LiteralPath $archive){throw 'R9_ARCHIVE_EXISTS'}
    # Retire only after PASS, without deleting quarantine/attempt metadata.
    # Child cleanup deliberately holds both mutexes until after this same-volume
    # directory rename. The original parent is never released because of a PID.
    [void](Move-R9VerifiedQuarantine -Guard $guard -Parent $parent -Archive $archive -OwnerSha256 $plan.parent_lease.sha256 -ParentStream $parentStream -Result $result)
    $parentStream=$null
    $final.status='PASS_F365_RETURN_QUARANTINE_ARCHIVED';$final.parent_quarantine_retained=$false;$final.metadata_archived=$true;$final.archive_path=$archive
} catch {
    $final.error=$_.Exception.Message
} finally {
    $env:OM_R9_RETURN_CONTEXT=$old
    if($guard){
        if(-not $launched -or $final.metadata_archived){Exit-F319HardwareGuard -Guard $guard}
        else {
            # Preserve failed child metadata; release process-local handles only.
            if($guard.LeaseStream){$guard.LeaseStream.Dispose()}
            foreach($mutex in @($guard.OwnedMutexes)){try{$mutex.ReleaseMutex()}catch{}}
            foreach($mutex in @($guard.Mutexes)){if($mutex){$mutex.Dispose()}}
        }
    }
    if($parentStream){$parentStream.Dispose()}
    if($freeze){Exit-F366R3SourceFreeze -Freeze $freeze}
    if($null -ne $power -and $power -ne 0){[void][R9ReturnPower]::SetThreadExecutionState([uint32]$power)}
    $final.parent_quarantine_retained=(Test-Path -LiteralPath $parent)
    $final.archive_directory_present=(Test-Path -LiteralPath $archive)
    if($final.archive_directory_present){$final.archive_path=$archive}
    if(Test-Path -LiteralPath $out){[IO.File]::WriteAllText((Join-Path $out 'launcher-result.json'),($final|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))}
}
$final|ConvertTo-Json -Depth 8
if($final.status -cne 'PASS_F365_RETURN_QUARANTINE_ARCHIVED'){exit 1}
