Set-StrictMode -Version Latest

function Assert-R9ReturnPath {
    param([Parameter(Mandatory=$true)][string]$Path,[switch]$MayNotExist)
    if(-not [IO.Path]::IsPathRooted($Path) -or $Path.StartsWith('\\') -or $Path -match '(?:^|[\\/])\.\.(?:[\\/]|$)'){throw 'R9_ABSOLUTE_LOCAL_PATH_REQUIRED'}
    $full=[IO.Path]::GetFullPath($Path)
    if($full -cnotmatch '^[CD]:\\'){throw 'R9_PATH_DRIVE'}
    $walk=$full
    while($walk){
        if(Test-Path -LiteralPath $walk){if((Get-Item -LiteralPath $walk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'R9_PATH_REPARSE'}}
        $walk=Split-Path -Parent $walk
    }
    if(-not $MayNotExist -and -not (Test-Path -LiteralPath $full)){throw 'R9_PATH_MISSING'}
    return $full
}

function Assert-R9ReturnContext {
    param([switch]$Admission)
    $c=$env:OM_R9_RETURN_CONTEXT|ConvertFrom-Json
    if($c.schema -cne 'openmitrastar.f367r9-return-f365-context/v1' -or $c.initial_boot_id -cnotmatch '^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$' -or
       $c.initial_boot_id -ceq 'cf18e917-7a46-4a60-a352-eef2572adff7' -or $c.parent_owner_sha256 -cnotmatch '^[0-9a-f]{64}$'){throw 'R9_CONTEXT_SCOPE'}
    $planPath=Assert-R9ReturnPath $c.plan_path
    if((Get-FileHash -LiteralPath $planPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $c.plan_sha256){throw 'R9_CONTEXT_PLAN'}
    $p=Get-Content -LiteralPath $planPath -Raw|ConvertFrom-Json
    if($p.schema -cne 'openmitrastar.f367r9-return-f365-plan/v1' -or $p.images.f365.sha256 -cne '43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355' -or
       $p.images.f367.sha256 -cne '6bf5a08edd5b18adf1597efbd5367d5ad439363c7f7a13a035efc615b4cee440' -or $p.erase_bytes -ne 0x5e0000 -or
       $p.write_target -cne 'mtd4/linux_live' -or $p.max_attempts -ne 1 -or $p.context_ttl_seconds -ne 3600){throw 'R9_PLAN_SCOPE'}
    foreach($name in @('watchdog_arm_allowed','radio_tests_allowed','sensor_activation_allowed','boot_environment_persistence_allowed','store_write_allowed','serial_reset_fallback_allowed')){
        if($p.$name -isnot [bool] -or $p.$name){throw 'R9_FORBIDDEN_PLAN_ACTION'}
    }
    $issued=[DateTimeOffset]::Parse($c.created_at_utc);$expires=[DateTimeOffset]::Parse($c.expires_at_utc)
    if($issued -gt [DateTimeOffset]::UtcNow -or $expires -le [DateTimeOffset]::UtcNow -or ($expires-$issued).TotalSeconds -ne 3600){throw 'R9_CONTEXT_LIFETIME'}
    $root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    $parent=Assert-R9ReturnPath $p.physical_lock_dir
    if($parent -ine (Join-Path $root 'outputs\locks\f301-physical-radio.lock') -or
       (Assert-R9ReturnPath $c.physical_lock_dir) -ine (Join-Path $parent 'r9-return-f365.lock')){throw 'R9_CHILD_LEASE_SCOPE'}
    $ownerPath=Assert-R9ReturnPath (Join-Path $parent 'owner.json')
    if((Get-FileHash -LiteralPath $ownerPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $c.parent_owner_sha256 -or
       $c.parent_owner_sha256 -cne $p.parent_lease.sha256){throw 'R9_PARENT_QUARANTINE_DRIFT'}
    if($Admission){if($c.phase -cne 'admission' -or $null -ne $c.binding){throw 'R9_ADMISSION_PHASE'}}
    else {
        if($c.phase -cne 'bound' -or $c.binding.NonceObserved -isnot [bool] -or -not $c.binding.NonceObserved -or
           $c.binding.RouterHost -cne '192.168.1.90' -or $c.binding.Port -cne 'COM3' -or
           $c.binding.PnpDeviceId -ine $p.uart_pnp_device_id -or $c.binding.ExpectedVersion -cne 'lyoko-foundation-6.11.8-f367r9-transition-observation-device'){throw 'R9_NONCE_BINDING'}
        if((Get-FileHash -LiteralPath (Assert-R9ReturnPath $c.admission_path) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $c.admission_sha256){throw 'R9_ADMISSION_HASH'}
        $a=Get-Content -LiteralPath $c.admission_path -Raw|ConvertFrom-Json
        if($a.status -cne 'PASS_FRESH_R9_QUIESCENT' -or $a.identity.boot_id -cne $c.initial_boot_id){throw 'R9_ADMISSION_EPOCH'}
    }
    [void](Get-F319SerialDevice -Port COM3 -ExpectedPnpDeviceId $p.uart_pnp_device_id)
    [void](Assert-F319HardwareLease -PhysicalLockDir $c.physical_lock_dir -OwnerPid $c.owner_pid -OwnerStartTicks $c.owner_start_ticks -LeaseToken $c.lease_token -Port COM3 -ExpectedPnpDeviceId $p.uart_pnp_device_id)
    return $c
}

function Move-R9VerifiedQuarantine {
    param([Parameter(Mandatory=$true)]$Guard,[Parameter(Mandatory=$true)][string]$Parent,
          [Parameter(Mandatory=$true)][string]$Archive,[Parameter(Mandatory=$true)][string]$OwnerSha256,
          [Parameter(Mandatory=$true)]$ParentStream,[Parameter(Mandatory=$true)]$Result)
    if($Result.status -cne 'PASS_R9_EXACT_F365_RETURN' -or $Result.f365_return_confirmed -isnot [bool] -or -not $Result.f365_return_confirmed -or
       $Result.containment_confirmed -isnot [bool] -or -not $Result.containment_confirmed -or
       $Result.retain_lease_required -isnot [bool] -or $Result.retain_lease_required -or
       $Result.flash_command_in_flight -isnot [bool] -or $Result.flash_command_in_flight){throw 'R9_ARCHIVE_REQUIRES_COMPLETE_RETURN'}
    $Parent=Assert-R9ReturnPath $Parent
    $Archive=Assert-R9ReturnPath $Archive -MayNotExist
    if((Split-Path -Parent $Parent) -ine (Split-Path -Parent $Archive) -or (Test-Path -LiteralPath $Archive)){throw 'R9_SIBLING_ARCHIVE_REQUIRED'}
    if(@($Guard.OwnedMutexes).Count -ne 2 -or -not $Guard.OwnsPhysicalLock -or
       [IO.Path]::GetFullPath($Guard.PhysicalLockDir) -ine (Join-Path $Parent 'r9-return-f365.lock')){throw 'R9_ARCHIVE_EXCLUSION_REQUIRED'}
    $ownerPath=Join-Path $Parent 'owner.json'
    if((Get-FileHash -LiteralPath $ownerPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $OwnerSha256){throw 'R9_ARCHIVE_OWNER_CHANGED'}
    $childOwner=Read-F319Lease -PhysicalLockDir $Guard.PhysicalLockDir
    if($childOwner.lease_token -cne $Guard.LeaseToken -or $childOwner.pid -ne $PID){throw 'R9_CHILD_IDENTITY_CHANGED'}
    $Guard.LeaseStream.Dispose();$Guard.LeaseStream=$null
    # Only the child directory created by this invocation is removed, using
    # the reviewed nonrecursive helper; both OwnedMutexes remain held.
    Remove-F319OwnedLock -PhysicalLockDir $Guard.PhysicalLockDir
    $Guard.OwnsPhysicalLock=$false
    $ParentStream.Dispose()
    [void](Assert-R9ReturnPath $Parent);[void](Assert-R9ReturnPath $Archive -MayNotExist)
    [IO.Directory]::Move($Parent,$Archive)
    if((Get-FileHash -LiteralPath (Join-Path $Archive 'owner.json') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $OwnerSha256){throw 'R9_ARCHIVE_METADATA_CHANGED'}
    return $Archive
}
