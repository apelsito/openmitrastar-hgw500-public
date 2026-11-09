Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f325_ethernet_runtime.ps1')
$script:F334OriginPath='/workspace/user-home\Desktop\MitraStar\outputs\preflight\f334-reset-recovery-20260921T115421Z\origin.json'
$script:F334OriginSha='51770f03e55d34c17179605e3d07ef3981561371d4a30a945b8a84aa7136737b'
if((Get-F325PermissionFileSha256 -Path $script:F334OriginPath) -cne $script:F334OriginSha){throw 'F334_ORIGIN_CONTRACT_CHANGED'}
$script:F334Origin=[IO.File]::ReadAllText($script:F334OriginPath)|ConvertFrom-Json

function Assert-F334OriginDocuments {
    param([object]$Documents)
    $main=$Documents.main;$writer=$Documents.writer;$capture=$Documents.capture;$back=$Documents.rollback
    if($main.status -cne 'STOP_NO_AUTOMATIC_RETRY' -or $main.failed_stage -cne 'capture' -or
       $main.candidate_sha256 -cne $script:F334Origin.candidate_sha256 -or $main.writer_verified -ne $true -or
       $main.automatic_recovery_started -ne $true -or $main.helper_containment_verified -ne $true -or
       $main.lease_released -ne $true -or $main.retain_lease_required -ne $false){throw 'F334_ORIGIN_MAIN_INVALID'}
    if($writer.status -cne 'PASS_VERIFIED_ETHERNET_WRITER' -or
       $writer.candidate_sha256_expected -cne $script:F334Origin.candidate_sha256 -or
       $writer.full_slot_crc32_observed -cne 'cc7d1938' -or $writer.candidate_prefix_compared_bytes -ne 5332992 -or
       $writer.protected_partitions_crc_verified -ne $true){throw 'F334_ORIGIN_WRITER_INVALID'}
    if($capture.status -cne 'FAIL_CAPTURE' -or $capture.candidate_sha256 -cne $script:F334Origin.candidate_sha256 -or
       $capture.arm_attempted -ne $true -or $capture.hardware_restore_proven -ne $false){throw 'F334_ORIGIN_CAPTURE_INVALID'}
    if($back.status -cne 'STOP_NO_AUTOMATIC_RETRY' -or $back.failed_stage -cne 'reboot' -or
       $back.direction -cne 'rollback' -or $back.candidate_sha256 -cne $script:F334Origin.restore_sha256 -or
       $back.writer_verified -ne $false -or $back.helper_containment_verified -ne $true -or
       $back.retain_lease_required -ne $false){throw 'F334_ORIGIN_RESTORE_NOT_PREWRITE'}
    $rows=@($Documents.observations)
    if($rows.Count -ne 1 -or $rows[0].once_phase -ne 0 -or $rows[0].hardware_dirty -ne 0 -or
       $rows[0].configured -ne 0 -or $rows[0].boot_id -cne $script:F334Origin.prearm_boot_id){throw 'F334_ORIGIN_BOOT_INVALID'}
}

function Get-F334OriginalFailure {
    $documents=@{}
    foreach($row in $script:F334Origin.files){
        $path=Join-Path $script:F325EthernetRoot $row.path
        $file=[IO.FileInfo]::new($path)
        if(-not $file.Exists -or $file.Length -ne $row.bytes -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
           (Get-F325PermissionFileSha256 -Path $path) -cne $row.sha256){throw 'F334_ORIGIN_FILE_CHANGED'}
        if($row.label -ne 'uart'){$documents[$row.label]=[IO.File]::ReadAllText($path)|ConvertFrom-Json}
    }
    Assert-F334OriginDocuments -Documents ([pscustomobject]$documents)
    foreach($suffix in @('writer','existing-permission-before-transfer.json','ethernet-loader-process.stdout.log','verified-writer.json')){
        if(Test-Path -LiteralPath (Join-Path $script:F334Origin.failed_return_directory $suffix)){throw 'F334_ORIGIN_HAS_LATER_WRITER'}
    }
    return [pscustomobject]@{status='PASS_ORIGINAL_FAILURE_PREWRITE';prearm_boot_id=$script:F334Origin.prearm_boot_id;
        origin_sha256=$script:F334OriginSha;owner_pid=$documents.parent.owner_pid;finished_at_utc=$documents.parent.finished_at_utc}
}

function Get-F334FreshRecoveryPlan {
    $origin=Get-F334OriginalFailure
    $common=@{ServerIp='192.168.1.49';InterfaceIndex=18;ExecutorReview=$script:F334Origin.review;
        ExecutorReviewSha256=$script:F334Origin.review_sha256;NetworkAuthorization=$script:F334Origin.network;
        NetworkAuthorizationSha256=$script:F334Origin.network_sha256;FirewallMode='existing-permission';
        ExistingPermission=$script:F334Origin.permission;ExistingPermissionSha256=$script:F334Origin.permission_sha256}
    $source=Get-F325EthernetPlan @common -Direction promote
    $restore=Get-F325EthernetPlan @common -Direction rollback
    if($source.image.sha256 -cne $script:F334Origin.candidate_sha256 -or $restore.image.sha256 -cne $script:F334Origin.restore_sha256 -or
       $source.status -cne 'OFFLINE_READY_FRESH_PHYSICAL_GATES_PENDING' -or $restore.status -cne $source.status){throw 'F334_RECOVERY_PLAN_INVALID'}
    return [pscustomobject]@{schema='openmitrastar.f334-reset-recovery-plan/v1';status='OFFLINE_READY_FRESH_BOOT_REQUIRED';
        origin=$origin;source=$source;restore=$restore;hardware_actions=$false;firewall_changes=$false;privilege_requested=$false}
}

function Assert-F334CleanBoot {
    param([object]$State,[string]$PreviousBootId)
    if($State.boot_id -cnotmatch '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' -or
       $State.boot_id -ceq $PreviousBootId -or $State.version -cne 'lyoko-foundation-6.9.5-f334-radar-once-f321-device'){
        throw 'F334_FRESH_BOOT_REQUIRED'
    }
    if($State.provider_state -ceq 'absent'){
        if($State.sysmodule_present -ne $false -or $State.procmodule_present -ne $false -or $State.procstatus_present -ne $false){throw 'F334_PROVIDER_ABSENCE_UNPROVED'}
    }elseif($State.provider_state -ceq 'present'){
        if($State.sysmodule_present -ne $true -or $State.procmodule_present -ne $true -or $State.procstatus_present -ne $true){throw 'F334_PROVIDER_PRESENCE_INCONSISTENT'}
        foreach($key in @('once_phase','hardware_dirty','configured','shadow_arm','polling','mmio_writes')){
            if($State.$key -isnot [int] -or $State.$key -ne 0){throw 'F334_PROVIDER_NOT_PRISTINE'}
        }
    }else{throw 'F334_PROVIDER_STATE_UNKNOWN'}
}

function Get-F334CleanBootState {
    param([object]$SourcePlan,[string]$PreviousBootId)
    $known=Join-Path $SourcePlan.image.directory $SourcePlan.image.known_hosts
    $arguments=@('-i',(Join-Path $env:USERPROFILE '.ssh/id_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
        '-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o',('UserKnownHostsFile='+$known),'-o','LogLevel=ERROR','root@192.168.1.90','sh','-s')
    $command=@'
set -eu
grep -Fqx 'OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.9.5-f334-radar-once-f321-device' /etc/openmitrastar/release
printf 'boot_id=%s\n' "$(cat /proc/sys/kernel/random/boot_id)"
printf 'version=lyoko-foundation-6.9.5-f334-radar-once-f321-device\n'
sys=0; mod=0; status=0
[ ! -d /sys/module/qtn_radar_shadow_f315 ] || sys=1
if grep -q '^qtn_radar_shadow_f315 ' /proc/modules; then mod=1; fi
[ ! -r /proc/openmitrastar_radar_f315/status ] || status=1
printf 'sysmodule_present=%s\nprocmodule_present=%s\nprocstatus_present=%s\n' "$sys" "$mod" "$status"
if [ "$sys$mod$status" = 000 ]; then
 printf 'provider_state=absent\n'
elif [ "$sys$mod$status" = 111 ]; then
 printf 'provider_state=present\n'
 awk -F= '$1=="once_phase" || $1=="hardware_dirty" || $1=="configured" || $1=="shadow_arm" || $1=="polling" || $1=="mmio_writes" {print}' /proc/openmitrastar_radar_f315/status
else
 exit 23
fi
'@
    $reply=Invoke-F319SshScript -SshPath (Join-Path $env:WINDIR 'System32/OpenSSH/ssh.exe') -Arguments $arguments -Script $command -TimeoutSeconds 20
    if($reply.ExitCode -ne 0){throw 'F334_FRESH_STATE_READ_FAILED'}
    $values=[ordered]@{}
    foreach($line in ($reply.Stdout -split "`n")){
        $line=$line.TrimEnd("`r")
        if(-not $line){continue}
        if($line -cnotmatch '^(boot_id|version|provider_state|sysmodule_present|procmodule_present|procstatus_present|once_phase|hardware_dirty|configured|shadow_arm|polling|mmio_writes)=(.+)$'){
            throw 'F334_FRESH_STATE_MALFORMED'
        }
        $key=$Matches[1];$value=$Matches[2]
        if($values.Contains($key)){throw 'F334_FRESH_STATE_DUPLICATE'}
        if($key -in @('boot_id','version','provider_state')){$values[$key]=$value}
        elseif($key.EndsWith('_present')){if($value -cnotin @('0','1')){throw 'F334_FRESH_STATE_MALFORMED'};$values[$key]=($value -ceq '1')}
        else{if($value -cnotmatch '^[0-9]{1,9}$'){throw 'F334_FRESH_STATE_MALFORMED'};$values[$key]=[int]$value}
    }
    $state=[pscustomobject]$values
    Assert-F334CleanBoot -State $state -PreviousBootId $PreviousBootId
    return $state
}

function Assert-F334FreshBorrowedRecoveryGuard {
    param([object]$Guard,[object]$BindingProof,[string]$ExpectedPnpDeviceId)
    [void](Get-F334OriginalFailure)
    if($Guard.OwnerPid -ne $PID -or $BindingProof.OwnerPid -ne $PID -or
       $Guard.OwnerStartTicks -ne $BindingProof.OwnerStartTicks -or $Guard.LeaseToken -cne $BindingProof.LeaseToken -or
       $null -eq $Guard.LeaseStream -or -not $Guard.LeaseStream.CanWrite -or
       $BindingProof.Binding.NonceObserved -isnot [bool] -or -not $BindingProof.Binding.NonceObserved -or
       $BindingProof.Binding.RouterHost -cne '192.168.1.90' -or $BindingProof.Binding.Port -ine 'COM3' -or
       $BindingProof.Binding.ExpectedVersion -cne 'lyoko-foundation-6.9.5-f334-radar-once-f321-device' -or
       $BindingProof.Binding.PnpDeviceId -ine $ExpectedPnpDeviceId -or
       $BindingProof.OriginSha256 -cne $script:F334OriginSha){throw 'F334_FRESH_GUARD_INVALID'}
    Assert-F334CleanBoot -State $BindingProof.CleanState -PreviousBootId $script:F334Origin.prearm_boot_id
    [void](Assert-F319HardwareLease -PhysicalLockDir $Guard.PhysicalLockDir -OwnerPid $Guard.OwnerPid -OwnerStartTicks $Guard.OwnerStartTicks -LeaseToken $Guard.LeaseToken -Port 'COM3' -ExpectedPnpDeviceId $ExpectedPnpDeviceId)
}

function Invoke-F334ResetRecovery {
    param([object]$Plan,[string]$RunDir,[string]$ClaimPath)
    $guard=$null;$stage='origin';$result=[ordered]@{schema='openmitrastar.f334-reset-recovery/v1';status='STOP_NO_AUTOMATIC_RETRY';
        target_sha256=$script:F334Origin.restore_sha256;claim_created=$false;lease_released=$false;firewall_changes=$false;privilege_requested=$false;capture_attempted=$false}
    try{
        if(Test-Path -LiteralPath $ClaimPath){throw 'F334_RECOVERY_CLAIM_ALREADY_USED'}
        $origin=Get-F334OriginalFailure
        $stage='old-process'
        $process=Get-Process -Id $origin.owner_pid -ErrorAction SilentlyContinue
        if($process -and $process.StartTime.ToUniversalTime() -le [DateTime]::Parse($origin.finished_at_utc).ToUniversalTime()){throw 'F334_OLD_PROCESS_STILL_PRESENT'}
        if(Test-F325EthernetUncertain){throw 'F334_PRIOR_CONTAINMENT_UNRESOLVED'}
        $stage='permission';$permission=Assert-F325ExistingPermission -Plan $Plan.restore
        $stage='network';[void](Assert-F325EthernetHostNetwork -Plan $Plan.restore)
        $stage='fresh-boot';$first=Get-F334CleanBootState -SourcePlan $Plan.source -PreviousBootId $origin.prearm_boot_id
        Write-F325EthernetJson -Path (Join-Path $RunDir 'clean-before-lease.json') -Value $first
        $stage='lease';$guard=Enter-F319HardwareGuard -Port 'COM3' -ExpectedPnpDeviceId $Plan.restore.uart_pnp_device_id -PhysicalLockDir $Plan.restore.physical_lock -Owner 'f334-fresh-reset-return-f321' -EvidenceDir $RunDir
        $stage='fresh-binding';$binding=Assert-F319UartBinding -Port 'COM3' -ExpectedPnpDeviceId $Plan.restore.uart_pnp_device_id -RouterHost '192.168.1.90' -KnownHosts (Join-Path $Plan.source.image.directory $Plan.source.image.known_hosts) -ExpectedVersion $Plan.source.image.version -HardwareLease $guard
        $stage='fresh-boot-after-binding';$second=Get-F334CleanBootState -SourcePlan $Plan.source -PreviousBootId $origin.prearm_boot_id
        if($second.boot_id -cne $first.boot_id){throw 'F334_BOOT_CHANGED_DURING_BINDING'}
        $proof=[pscustomobject]@{OwnerPid=$guard.OwnerPid;OwnerStartTicks=$guard.OwnerStartTicks;LeaseToken=$guard.LeaseToken;Binding=$binding;CleanState=$second;OriginSha256=$script:F334OriginSha}
        Assert-F334FreshBorrowedRecoveryGuard -Guard $guard -BindingProof $proof -ExpectedPnpDeviceId $Plan.restore.uart_pnp_device_id
        $witness=[pscustomobject]@{Kind='existing-permission';Name=$script:F325ExistingRuleName;Fingerprint=$permission.fingerprint_sha256;ExecutorOwnsRule=$false;OwnerPid=$guard.OwnerPid;OwnerStartTicks=$guard.OwnerStartTicks;LeaseToken=$guard.LeaseToken}
        Assert-F325EthernetFirewallAccess -Rule $witness -Plan $Plan.restore -Guard $guard
        Write-F325EthernetJson -Path (Join-Path $RunDir 'fresh-binding.json') -Value @{boot_id=$second.boot_id;provider_state=$second.provider_state;nonce_verified=$true;owner_pid=$guard.OwnerPid;origin_sha256=$script:F334OriginSha}
        $stage='claim';Write-F325EthernetJson -Path $ClaimPath -Value @{owner_pid=$PID;created_at_utc=[DateTime]::UtcNow.ToString('o');boot_id=$second.boot_id;origin_sha256=$script:F334OriginSha;run_directory=$RunDir}
        $result.claim_created=$true
        $restoreDir=Join-Path $RunDir 'restore';[void][IO.Directory]::CreateDirectory($restoreDir)
        $stage='exact-f321-return'
        $restored=Invoke-F334FreshRollbackCycle -Plan $Plan.restore -RunDir $restoreDir -ExecutorReview $script:F334Origin.review -ExecutorReviewSha256 $script:F334Origin.review_sha256 -BorrowedHardwareGuard $guard -RecoveryBindingProof $proof -BorrowedFirewallRule $witness
        if($restored.status -cne 'PASS_EXACT_F321_RESTORED'){throw 'F334_RESTORE_NOT_PROVED'}
        $result.status='PASS_EXACT_F321_RESTORED_AFTER_FRESH_RESET'
    }catch{
        $result.failed_stage=$stage;$result.error_type=$_.Exception.GetType().Name
        $result.refusal_code=if($_.Exception.Message -cmatch '^F334_[A-Z0-9_]+$'){$_.Exception.Message}else{'F334_DEPENDENCY_REFUSED'}
    }finally{
        if($guard -and -not(Test-F325EthernetUncertain)){
            try{[void](Assert-F325ExistingPermission -Plan $Plan.restore);Exit-F319HardwareGuard -Guard $guard;$result.lease_released=$true}
            catch{$script:F325EthernetUncertain=$true;$result.status='STOP_NO_AUTOMATIC_RETRY';$result.cleanup_failed=$true}
        }
        $result.helper_containment_verified=-not(Test-F325EthernetUncertain)
        $result.retain_lease_required=Test-F325EthernetUncertain
        if($result.retain_lease_required){$result.status='STOP_NO_AUTOMATIC_RETRY'}
        $result.finished_at_utc=[DateTime]::UtcNow.ToString('o')
        Write-F325EthernetJson -Path (Join-Path $RunDir 'result.json') -Value $result
    }
    return [pscustomobject]$result
}

# Explicit derivative: original cycle remains unchanged; only fresh rollback is accepted.
function Invoke-F334FreshRollbackCycle {
    param([object]$Plan, [string]$RunDir, [int]$FlashTimeoutSeconds = 1800,
        [string]$ExecutorReview = '', [string]$ExecutorReviewSha256 = '',
        [object]$BorrowedHardwareGuard = $null, [object]$RecoveryBindingProof = $null,
        [object]$BorrowedFirewallRule = $null, [switch]$CaptureAndRestore)
    if($Plan.direction -cne 'rollback' -or $CaptureAndRestore){throw 'F334_ONLY_FRESH_F321_RETURN_ALLOWED'}
    $guard=$null; $firewall=$null; $owned=$false; $firewallOwned=$false; $writerVerified=$false; $bindingProof=$null; $failed=$false; $stage='request'; $recoveryAttempted=$false
    $firewallMode=$null; $existingInitial=$null; $permissionPlanArgs=@{}
    $savedContext=[Environment]::GetEnvironmentVariable('OM_F325_PHYSICAL_CONTEXT','Process')
    $savedPreloaded=[Environment]::GetEnvironmentVariable('OM_F325_ETHERNET_PRELOADED','Process')
    $result=[ordered]@{schema='openmitrastar.f325-ethernet-physical-cycle/v1';direction=$Plan.direction;status='STOP_NO_AUTOMATIC_RETRY';
        candidate_sha256=$Plan.image.sha256;write_target='mtd4/linux_live';transport='ethernet-tftp';writer_verified=$false;
        radio_mutation=$false;release_eligible=$false;automatic_recovery_started=$false;firewall_cleanup_verified=$false;
        host_addresses_or_routes_changed=$false;firewall_disabled=$false;failed_stage=$null}
    try {
        Assert-F325EthernetExecutionRequest -Plan $Plan -Ack $Plan.required_ack
        $firewallMode=Get-F325EthernetFirewallMode -Plan $Plan
        $result.firewall_mode=$firewallMode
        $permissionPlanArgs=@{FirewallMode=$firewallMode}
        if ($firewallMode -ceq 'existing-permission') {
            $permissionPlanArgs.ExistingPermission=$Plan.network.existing_permission.path
            $permissionPlanArgs.ExistingPermissionSha256=$Plan.network.existing_permission.sha256
            $result.firewall_changes=$false
            $result.privilege_requested=$false
        }
        if ($Plan.direction -ceq 'rollback') {
            $stage='conditional-rollback'
            # The recorded F321 recovery is conditional on the promoter's
            # verified write and failed postgate, with its same live resources.
            # This is not an independently authorized fresh restore entrypoint.
            if ($BorrowedHardwareGuard -isnot [pscustomobject] -or
                $RecoveryBindingProof -isnot [pscustomobject] -or
                $BorrowedFirewallRule -isnot [pscustomobject]) {
                throw 'Conditional F321 restoration requires the borrowed lease, original binding and firewall rule'
            }
        }
        if (Test-F325EthernetUncertain) { throw 'Earlier containment/cleanup remains unresolved' }
        if ($firewallMode -ceq 'temporary-scoped-rule') {
            $stage='administrator'
            if ((Test-F325EthernetAdministrator) -ne $true) { throw 'Elevated execution is required for the selected temporary firewall rule' }
        } else {
            $stage='existing-permission-before-hardware'
            $existingInitial=Assert-F325ExistingPermission -Plan $Plan
            Write-F325EthernetJson -Path (Join-Path $RunDir 'existing-permission-before-hardware.json') -Value $existingInitial
        }
        [void](Get-F325EthernetActionArguments -Plan $Plan -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256)
        $stage='host-network'
        $hostProof = Assert-F325EthernetHostNetwork -Plan $Plan
        Write-F325EthernetJson -Path (Join-Path $RunDir 'host-network.json') -Value $hostProof
        $stage='recovery-evidence'
        [void](Get-F319VerifiedRecoveryRehearsal -ResultPath $Plan.recovery_rehearsal)
        if (($null -eq $BorrowedHardwareGuard) -ne ($null -eq $RecoveryBindingProof) -or
            ($BorrowedFirewallRule -and -not $BorrowedHardwareGuard)) { throw 'Incomplete borrowed recovery scope' }
        if ($BorrowedHardwareGuard) {
            $stage='borrowed-lease'
            if ($Plan.direction -cne 'rollback') { throw 'Only F321 restoration may borrow ownership' }
            Assert-F334FreshBorrowedRecoveryGuard -Guard $BorrowedHardwareGuard -BindingProof $RecoveryBindingProof -ExpectedPnpDeviceId $Plan.uart_pnp_device_id
            $guard=$BorrowedHardwareGuard; $bindingProof=$RecoveryBindingProof
        } else {
            $stage='ssh-baseline'
            Invoke-F325EthernetBaseline -Plan $Plan -RunDir $RunDir
            $stage='lease'
            $guard=Enter-F319HardwareGuard -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id -PhysicalLockDir $Plan.physical_lock -Owner ('f325-ethernet-'+$Plan.direction) -EvidenceDir $RunDir
            $owned=$true
            $stage='binding'
            $binding=Assert-F319UartBinding -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id -RouterHost '192.168.1.90' `
                -KnownHosts (Join-Path $Plan.current.directory $Plan.current.known_hosts) -ExpectedVersion $Plan.current.version -HardwareLease $guard
            $bindingProof=[pscustomobject]@{OwnerPid=$guard.OwnerPid;OwnerStartTicks=$guard.OwnerStartTicks;LeaseToken=$guard.LeaseToken;Binding=$binding}
        }
        $stage='lease-check'
        [void](Assert-F319HardwareLease -PhysicalLockDir $guard.PhysicalLockDir -OwnerPid $guard.OwnerPid -OwnerStartTicks $guard.OwnerStartTicks `
            -LeaseToken $guard.LeaseToken -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id)
        $stage='firewall'
        if ($BorrowedFirewallRule) {
            Assert-F325EthernetFirewallAccess -Rule $BorrowedFirewallRule -Plan $Plan -Guard $guard
            $firewall=$BorrowedFirewallRule
        } elseif ($firewallMode -ceq 'existing-permission') {
            $firewall=[pscustomobject]@{Kind='existing-permission';Name=$script:F325ExistingRuleName;
                Fingerprint=$script:F325ExistingFingerprint;ExecutorOwnsRule=$false;
                OwnerPid=$PID;OwnerStartTicks=$guard.OwnerStartTicks;LeaseToken=$guard.LeaseToken}
            Assert-F325EthernetFirewallAccess -Rule $firewall -Plan $Plan -Guard $guard
        } else {
            $firewall=New-F325EthernetFirewallRule -Plan $Plan -Guard $guard -RunDir $RunDir
            $firewallOwned=$true
        }
        $result.firewall_rule_name=$firewall.Name
        $stage='physical-context'
        $env:OM_F325_PHYSICAL_CONTEXT=Create-F325PhysicalContext -Guard $guard -BindingProof $bindingProof -CandidateSha256 $Plan.image.sha256 -Direction $Plan.direction
        [Environment]::SetEnvironmentVariable('OM_F325_ETHERNET_PRELOADED',$null,'Process')
        $stage='reboot'
        Invoke-F325Reboot -Plan $Plan -RunDir $RunDir
        $stage='write'
        $result.writer=Invoke-F325EthernetWritePhase -Plan $Plan -RunDir $RunDir -FlashTimeoutSeconds $FlashTimeoutSeconds -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256
        if ($result.writer.status -cne 'PASS_VERIFIED_ETHERNET_WRITER' -or (Test-F325EthernetUncertain)) { throw 'Writer outcome or containment unknown' }
        $writerVerified=$true; $result.writer_verified=$true
        $stage='platform'
        Invoke-F321PlatformGate -Plan $Plan -RunDir $RunDir
        $stage='postbinding'
        [void](Assert-F319UartBinding -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id -RouterHost '192.168.1.90' `
            -KnownHosts (Join-Path $Plan.image.directory $Plan.image.known_hosts) -ExpectedVersion $Plan.image.version -HardwareLease $guard)
        $stage='ui'
        Invoke-F325UiGate -Plan $Plan -RunDir $RunDir
        $result.status=if ($Plan.direction -ceq 'promote') {'PASS_F325_ETHERNET_BOOT_PLATFORM_HTTP'} else {'PASS_EXACT_F321_RESTORED'}
        if ($CaptureAndRestore) {
            if ($Plan.direction -cne 'promote') { throw 'Only promotion can initiate the one-boot diagnostic' }
            $stage='capture'
            $result.radio_mutation_attempted=$true
            $result.radio_mutation=$null
            $result.capture=Invoke-F325CaptureGate -Plan $Plan -RunDir $RunDir
            $result.radio_mutation=$true
            $stage='planned-f321-restoration'
            $rollback=Get-F325EthernetPlan @permissionPlanArgs -Direction rollback -ServerIp $Plan.network.server_ipv4 -InterfaceIndex $Plan.network.interface_index `
                -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256 `
                -NetworkAuthorization $Plan.network_authorization.path -NetworkAuthorizationSha256 $Plan.network_authorization.sha256
            Assert-F325EthernetExecutionRequest -Plan $rollback -Ack $rollback.required_ack
            $rollbackDir=Join-Path $RunDir 'planned-exact-f321-rollback'
            if (Test-Path -LiteralPath $rollbackDir) { throw 'Recovery evidence already exists' }
            [void][IO.Directory]::CreateDirectory($rollbackDir)
            $recoveryAttempted=$true; $result.automatic_recovery_started=$true
            $restored=Invoke-F325EthernetPhysicalCycle -Plan $rollback -RunDir $rollbackDir -FlashTimeoutSeconds $FlashTimeoutSeconds `
                -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256 `
                -BorrowedHardwareGuard $guard -RecoveryBindingProof $bindingProof -BorrowedFirewallRule $firewall
            if ($restored.status -cne 'PASS_EXACT_F321_RESTORED') { throw 'Mandatory F321 restoration unproved' }
            $result.status='PASS_DIAGNOSTIC_COMPLETED_F321_RESTORED'
        }
    } catch {
        $failed=$true; $result.status='STOP_NO_AUTOMATIC_RETRY'; $result.failed_stage=$stage; $result.error_type=$_.Exception.GetType().Name
        if ($Plan.direction -ceq 'promote' -and -not $recoveryAttempted -and $writerVerified -and $guard -and $bindingProof -and $firewall -and -not (Test-F325EthernetUncertain)) {
            try {
                [void](Assert-F319HardwareLease -PhysicalLockDir $guard.PhysicalLockDir -OwnerPid $guard.OwnerPid -OwnerStartTicks $guard.OwnerStartTicks `
                    -LeaseToken $guard.LeaseToken -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id)
                Assert-F325EthernetFirewallAccess -Rule $firewall -Plan $Plan -Guard $guard
                $rollback=Get-F325EthernetPlan @permissionPlanArgs -Direction rollback -ServerIp $Plan.network.server_ipv4 -InterfaceIndex $Plan.network.interface_index `
                    -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256 `
                    -NetworkAuthorization $Plan.network_authorization.path -NetworkAuthorizationSha256 $Plan.network_authorization.sha256
                Assert-F325EthernetExecutionRequest -Plan $rollback -Ack $rollback.required_ack
                $rollbackDir=Join-Path $RunDir 'automatic-exact-f321-rollback'
                if (Test-Path -LiteralPath $rollbackDir) { throw 'Recovery evidence already exists' }
                [void][IO.Directory]::CreateDirectory($rollbackDir)
                $result.automatic_recovery_started=$true
                $recoveryAttempted=$true
                $restored=Invoke-F325EthernetPhysicalCycle -Plan $rollback -RunDir $rollbackDir -FlashTimeoutSeconds $FlashTimeoutSeconds `
                    -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256 `
                    -BorrowedHardwareGuard $guard -RecoveryBindingProof $bindingProof -BorrowedFirewallRule $firewall
                if ($restored.status -cne 'PASS_EXACT_F321_RESTORED') { throw 'Exact F321 restoration unproved' }
                $result.status='FAIL_F325_EXACT_F321_RESTORED'
            } catch { $result.status='STOP_NO_AUTOMATIC_RETRY'; $result.recovery_error_type=$_.Exception.GetType().Name }
        }
    } finally {
        try {
            [Environment]::SetEnvironmentVariable('OM_F325_PHYSICAL_CONTEXT',$savedContext,'Process')
            [Environment]::SetEnvironmentVariable('OM_F325_ETHERNET_PRELOADED',$savedPreloaded,'Process')
        } catch { $script:F325EthernetUncertain=$true; $failed=$true }
        try {
            if ($firewallMode -ceq 'existing-permission' -and $null -ne $existingInitial) {
                $existingFinal=Assert-F325ExistingPermission -Plan $Plan
                if ($existingFinal.fingerprint_sha256 -cne $existingInitial.fingerprint_sha256) { throw 'Existing permission changed during the physical cycle' }
                Write-F325EthernetJson -Path (Join-Path $RunDir 'existing-permission-after.json') -Value $existingFinal
                $result.existing_permission_unchanged=$true
                $result.firewall_cleanup_verified=$true
                $result.firewall_cleanup_deferred_to_owner=$false
            } else {
                if ($firewallOwned) { Remove-F325EthernetFirewallRule -Rule $firewall -Guard $guard }
                $result.firewall_cleanup_verified=($firewallOwned -or $null -eq $firewall)
                $result.firewall_cleanup_deferred_to_owner=($null -ne $firewall -and -not $firewallOwned)
            }
        } catch {
            $script:F325EthernetUncertain=$true; $failed=$true; $result.firewall_cleanup_verified=$false
            $result.cleanup_failed_stage='firewall-cleanup'; if (-not $result.failed_stage) {$result.failed_stage='firewall-cleanup'}
        }
        $result.lease_released=$false
        $result.lease_release_deferred_to_owner=(-not $owned -and $null -ne $guard)
        # Preserve the completed physical/cleanup evidence before surrendering
        # ownership. The final result below additionally records release outcome.
        if ($owned -and -not (Test-F325EthernetUncertain)) {
            try { Write-F325EthernetJson -Path (Join-Path $RunDir 'cleanup-before-release.json') -Value $result }
            catch { $script:F325EthernetUncertain=$true; $failed=$true; $result.cleanup_failed_stage='pre-release-evidence' }
        }
        if ($owned -and -not (Test-F325EthernetUncertain)) {
            try { Exit-F319HardwareGuard -Guard $guard; $result.lease_released=$true }
            catch {
                $script:F325EthernetUncertain=$true; $failed=$true; $result.cleanup_failed_stage='lease-release'
                if (-not $result.failed_stage) {$result.failed_stage='lease-release'}
            }
        }
        $result.helper_containment_verified=-not (Test-F325EthernetUncertain)
        $result.retain_lease_required=Test-F325EthernetUncertain
        if (Test-F325EthernetUncertain) { $result.status='STOP_NO_AUTOMATIC_RETRY'; $failed=$true }
        try { Write-F325EthernetJson -Path (Join-Path $RunDir 'result.json') -Value $result }
        catch { $script:F325EthernetUncertain=$true; $failed=$true }
    }
    if ($failed) { throw 'F325 Ethernet cycle stopped; inspect this run evidence before any further action' }
    return [pscustomobject]$result
}
