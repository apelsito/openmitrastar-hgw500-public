Set-StrictMode -Version Latest
# Reuse job containment, byte-safe SSH, UART guard, reboot and platform readers.
# The F321 physical cycle is never called by this module.
. (Join-Path $PSScriptRoot 'f321_mtd4_runtime.ps1')
$script:F322Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))

function Get-F322Plan {
    param([ValidateSet('promote','rollback','fallback')][string]$Direction,
          [string]$ExecutorReview = '', [string]$ExecutorReviewSha256 = '')
    $arguments = @((Join-Path $script:F322Root 'tools/f322_execution_contract.py'), '--direction', $Direction)
    if ($ExecutorReview) { $arguments += @('--executor-review', $ExecutorReview, '--executor-review-sha256', $ExecutorReviewSha256) }
    return ((Invoke-F321Native -Program 'python' -Arguments $arguments -TimeoutSeconds 180) | ConvertFrom-Json)
}

function Assert-F322ExecutionRequest {
    param([object]$Plan, [string]$Ack, [string]$Port, [string]$ExpectedPnpDeviceId, [string]$RouterHost)
    if ($Ack -cne $Plan.required_ack) { throw 'Exact F322 action ACK required; hardware not accessed' }
    if ($Plan.schema -cne 'openmitrastar.f322-mtd4-plan/v1' -or
        $Plan.executor_review_verified -isnot [bool] -or -not $Plan.executor_review_verified -or
        $Plan.local_preflight_pass -isnot [bool] -or -not $Plan.local_preflight_pass) { throw 'F322 reviewed artifact gate unresolved' }
    if ($Port -ine 'COM3' -or $ExpectedPnpDeviceId -ine 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -or
        $ExpectedPnpDeviceId -ine $Plan.uart_pnp_device_id -or $RouterHost -cne '192.168.1.90' -or $Plan.target_host -cne $RouterHost) {
        throw 'F322 is bound to the exact HGW/COM3 identity'
    }
    if ($Plan.write_target -cne 'mtd4/linux_live' -or $Plan.transport -cne 'uart-ymodem' -or
        $Plan.offset -cne '0x007e0000' -or $Plan.erase_bytes -ne 0x5e0000 -or $Plan.slot_bytes -ne 0x7a0000 -or
        $Plan.acquisition_authorized -isnot [bool] -or $Plan.acquisition_authorized) { throw 'F322 physical scope mismatch' }
}

function Invoke-F322Writer {
    param([object]$Plan, [string]$RunDir, [int]$FlashTimeoutSeconds = 1800)
    $saved = Set-F321WriterEnvironment -Plan $Plan
    try {
        $attemptDir = Join-Path $RunDir 'writer'
        $arguments = @((Join-Path $script:F322Root 'tools/f321_mtd4_one_shot.py'),
            '--execute', '--ack', $Plan.required_ack, '--port', 'COM3', '--client-ip', '192.168.1.90', '--host', '192.168.1.90',
            '--skip-reboot', '--timeout', [string]$FlashTimeoutSeconds, '--erase-bytes', '0x5e0000', '--transport', 'uart-ymodem',
            '--uart-attach-topaz', '--evidence-dir', $attemptDir, '--attempt-id', [Guid]::NewGuid().ToString('N'))
        [void](Invoke-F321Native -Program 'python' -Arguments $arguments -LogPrefix (Join-Path $RunDir 'writer-process') -TimeoutSeconds ($FlashTimeoutSeconds + 1500))
        $verified = Invoke-F321Native -Program 'python' -Arguments @((Join-Path $script:F322Root 'tools/f322_execution_contract.py'),
            '--direction', $Plan.direction, '--verify-writer', $attemptDir)
        $result = $verified | ConvertFrom-Json
        if ($result.status -cne 'PASS_VERIFIED_WRITER') { throw 'F322 writer outcome not proven' }
        [IO.File]::WriteAllText((Join-Path $RunDir 'verified-writer.json'), $verified, [Text.UTF8Encoding]::new($false))
        return $result
    } finally { Restore-F321WriterEnvironment -Saved $saved }
}

function Invoke-F322UiGate {
    param([object]$Plan, [string]$RunDir)
    if ($Plan.direction -ceq 'fallback') { return } # F314 platform proof is reported separately.
    if ($Plan.direction -ceq 'rollback') {
        Invoke-F321UiGate -RunDir $RunDir
        $tool = 'tools/verify_f321_authenticated_http.py'; $folder = 'authenticated-http'; $expected = 'PASS_AUTHENTICATED_HTTP_SESSION'
    } else {
        $tool = 'tools/f322_ui_gate.py'; $folder = 'ui'; $expected = 'PASS_F322_UI_AUTHENTICATED_HTTP'
    }
    $output = Join-Path $RunDir $folder
    [void](Invoke-F321Native -Program 'python' -Arguments @((Join-Path $script:F322Root $tool), '--execute', '--output-dir', $output) `
        -LogPrefix (Join-Path $RunDir ($folder + '-process')) -TimeoutSeconds 240)
    $status = Get-Content -LiteralPath (Join-Path $output 'result.json') -Raw | ConvertFrom-Json
    if ($status.status -cne $expected) { throw 'Authenticated UI gate did not prove the selected image' }
}

function Invoke-F322UnarmedBaseline {
    param([string]$RunDir)
    $output = Join-Path $RunDir 'unarmed-baseline'
    [void](Invoke-F321Native -Program 'python' -Arguments @((Join-Path $script:F322Root 'tools/run_f322_shadow_acquisition_gate.py'),
        '--execute', '--baseline-only', '--output-dir', $output) -LogPrefix (Join-Path $RunDir 'baseline-process') -TimeoutSeconds 180)
    $status = Get-Content -LiteralPath (Join-Path $output 'result.json') -Raw | ConvertFrom-Json
    if ($status.status -cne 'PASS_F322_BASELINE_UNARMED') { throw 'F322 baseline is not proven unarmed' }
}

function Assert-F322BorrowedRecoveryGuard {
    param([object]$Guard, [object]$BindingProof, [string]$ExpectedPnpDeviceId)
    if ($Guard.OwnerPid -ne $PID -or $BindingProof.OwnerPid -ne $PID -or
        $Guard.OwnerStartTicks -ne $BindingProof.OwnerStartTicks -or $Guard.LeaseToken -cne $BindingProof.LeaseToken -or
        $null -eq $Guard.LeaseStream -or -not $Guard.LeaseStream.CanWrite -or
        $BindingProof.Binding.NonceObserved -isnot [bool] -or -not $BindingProof.Binding.NonceObserved -or
        $BindingProof.Binding.RouterHost -cne '192.168.1.90' -or $BindingProof.Binding.Port -ine 'COM3' -or
        $BindingProof.Binding.ExpectedVersion -cne 'lyoko-foundation-6.8.5-f321-classic-ui-f314-device' -or
        $BindingProof.Binding.PnpDeviceId -ine $ExpectedPnpDeviceId) {
        throw 'Recovery needs this process live lease and original authenticated F321 binding'
    }
    [void](Assert-F319HardwareLease -PhysicalLockDir $Guard.PhysicalLockDir -OwnerPid $Guard.OwnerPid -OwnerStartTicks $Guard.OwnerStartTicks `
        -LeaseToken $Guard.LeaseToken -Port 'COM3' -ExpectedPnpDeviceId $ExpectedPnpDeviceId)
}

function Invoke-F322PhysicalCycle {
    param([object]$Plan, [string]$RunDir, [int]$FlashTimeoutSeconds = 1800,
          [object]$BorrowedHardwareGuard = $null, [object]$RecoveryBindingProof = $null,
          [string]$ExecutorReview = '', [string]$ExecutorReviewSha256 = '')
    $guard = $null; $owned = $false; $writerVerified = $false; $bindingProof = $null
    $result = [ordered]@{schema='openmitrastar.f322-physical-cycle/v1';direction=$Plan.direction;status='FAIL';
        candidate_sha256=$Plan.image.sha256;write_target='mtd4/linux_live';radio_mutation=$false;shadow_arm=$false;
        dfs_authority=$false;release_eligible=$false;f321_acceptance=$Plan.f321_acceptance}
    try {
        [void](Get-F319VerifiedRecoveryRehearsal -ResultPath $Plan.recovery_rehearsal)
        if (($null -eq $BorrowedHardwareGuard) -ne ($null -eq $RecoveryBindingProof)) { throw 'Incomplete recovery ownership' }
        if ($BorrowedHardwareGuard) {
            if ($Plan.direction -cne 'rollback') { throw 'Only exact F321 rollback may borrow the live lease' }
            Assert-F322BorrowedRecoveryGuard -Guard $BorrowedHardwareGuard -BindingProof $RecoveryBindingProof -ExpectedPnpDeviceId $Plan.uart_pnp_device_id
            $guard = $BorrowedHardwareGuard
        } else {
            $guard = Enter-F319HardwareGuard -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id -PhysicalLockDir $Plan.physical_lock -Owner ('f322-' + $Plan.direction) -EvidenceDir $RunDir
            $owned = $true
            $binding = Assert-F319UartBinding -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id -RouterHost '192.168.1.90' `
                -KnownHosts (Join-Path $Plan.current.directory $Plan.current.known_hosts) -ExpectedVersion $Plan.current.version -HardwareLease $guard
            $bindingProof = [pscustomobject]@{OwnerPid=$guard.OwnerPid;OwnerStartTicks=$guard.OwnerStartTicks;LeaseToken=$guard.LeaseToken;Binding=$binding}
        }
        [void](Assert-F319HardwareLease -PhysicalLockDir $guard.PhysicalLockDir -OwnerPid $guard.OwnerPid -OwnerStartTicks $guard.OwnerStartTicks `
            -LeaseToken $guard.LeaseToken -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id)
        Invoke-F321Reboot -Plan $Plan -RunDir $RunDir
        $result.writer = Invoke-F322Writer -Plan $Plan -RunDir $RunDir -FlashTimeoutSeconds $FlashTimeoutSeconds
        $writerVerified = $true
        Invoke-F321PlatformGate -Plan $Plan -RunDir $RunDir
        [void](Assert-F319UartBinding -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id -RouterHost '192.168.1.90' `
            -KnownHosts (Join-Path $Plan.image.directory $Plan.image.known_hosts) -ExpectedVersion $Plan.image.version -HardwareLease $guard)
        Invoke-F322UiGate -Plan $Plan -RunDir $RunDir
        if ($Plan.direction -ceq 'promote') { Invoke-F322UnarmedBaseline -RunDir $RunDir }
        $result.status = switch ($Plan.direction) {
            promote { 'PASS_F322_BOOT_PLATFORM_UI_UNARMED' }
            rollback { 'PASS_EXACT_F321_RESTORED' }
            fallback { 'PASS_EXACT_F314_FALLBACK_PLATFORM' }
        }
        return [pscustomobject]$result
    } catch {
        $failure = $_.Exception.Message
        $result.error = $failure
        $result.status = 'STOP_NO_AUTOMATIC_RETRY'
        if ($Plan.direction -ceq 'promote' -and $writerVerified -and $guard -and $bindingProof -and -not $script:F321ContainmentFailed) {
            $rollbackPlan = Get-F322Plan -Direction rollback -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256
            Assert-F322ExecutionRequest -Plan $rollbackPlan -Ack $rollbackPlan.required_ack -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id -RouterHost '192.168.1.90'
            $rollbackDir = Join-Path $RunDir 'automatic-exact-f321-rollback'
            if (Test-Path -LiteralPath $rollbackDir) { throw 'Recovery evidence directory already exists' }
            [void][IO.Directory]::CreateDirectory($rollbackDir)
            $restored = Invoke-F322PhysicalCycle -Plan $rollbackPlan -RunDir $rollbackDir -FlashTimeoutSeconds $FlashTimeoutSeconds `
                -BorrowedHardwareGuard $guard -RecoveryBindingProof $bindingProof -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256
            if ($restored.status -cne 'PASS_EXACT_F321_RESTORED') { throw 'Exact F321 restore not proven; do not chain F314 automatically' }
            $result.status = 'FAIL_F322_EXACT_F321_RESTORED'
            throw ('F322 postflash gate failed; exact F321 restored and verified: ' + $failure)
        }
        throw
    } finally {
        $result.helper_containment_verified = -not $script:F321ContainmentFailed
        [IO.File]::WriteAllText((Join-Path $RunDir 'result.json'), ($result | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
        if ($owned -and -not $script:F321ContainmentFailed) { Exit-F319HardwareGuard -Guard $guard }
    }
}
