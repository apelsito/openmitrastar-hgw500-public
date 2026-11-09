Set-StrictMode -Version Latest
$script:F321Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $script:F321Root 'tools/f319_uart_guard.ps1')
. (Join-Path $script:F321Root 'tools/f319_recovery_guard.ps1')
. (Join-Path $script:F321Root 'tools/f321_ssh_guard.ps1')
$script:F321ContainmentFailed = $false

function Complete-F321NativeContainment {
    param([object]$Process, [object]$Job, [bool]$Started)
    $script:F321ContainmentFailed = $true
    if ($Started) {
        # Startup/compilation can time out before the launcher joins the job.
        # Stop and verify that launcher too; an empty job alone is insufficient.
        if (-not $Process.HasExited) { $Process.Kill() }
        if (-not $Process.WaitForExit(5000)) { throw 'F321 launcher exit could not be proved' }
    }
    if ($Job.ActiveProcesses -ne 0 -and -not $Job.TerminateAndWait(5000)) { throw 'F321 helper job termination could not be proved' }
    $script:F321ContainmentFailed = $false
}

function Invoke-F321Native {
    param([string]$Program, [string[]]$Arguments, [string]$LogPrefix = '', [int]$TimeoutSeconds = 90)
    if (-not ('F321ProcessJob' -as [type])) { Add-Type -Path (Join-Path $script:F321Root 'tools/f321_process_job.cs') }
    $job = [F321ProcessJob]::new('Local\OpenMitraStar-F321-Native-' + [Guid]::NewGuid().ToString('N'))
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject @($Arguments) -Compress)))
    $launcherArgs = @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',
        (Join-Path $script:F321Root 'tools/f321_native_job_launcher.ps1'),'-JobName',$job.Name,'-Program',$Program,'-ArgumentsBase64',$encoded)
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = 'powershell.exe'
    $start.Arguments = (($launcherArgs | ForEach-Object { ConvertTo-F319NativeArgument $_ }) -join ' ')
    $start.UseShellExecute = $false; $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true; $start.RedirectStandardError = $true
    $start.WorkingDirectory = $script:F321Root
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $start
    $stdout = ''; $stderr = ''; $timedOut = $false; $started = $false
    try {
        if (-not $process.Start()) { throw 'Native helper failed to start' }
        $started = $true
        $outTask = $process.StandardOutput.ReadToEndAsync(); $errorTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $timedOut = $true
            # Do not start a recovery/retry after a timeout. The outcome may
            # include an erase/write even when the helper did not finish.
            $script:F321ContainmentFailed = $true
            if (-not $job.TerminateAndWait(5000)) { throw 'Cannot prove writer descendants terminated; hardware lease must remain held' }
            $script:F321ContainmentFailed = $false
            if (-not $process.WaitForExit(5000)) { $script:F321ContainmentFailed = $true; throw 'Contained launcher did not exit; hardware outcome remains ambiguous' }
        }
        if (-not [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($outTask,$errorTask),5000)) {
            $script:F321ContainmentFailed = $true
            if ($job.TerminateAndWait(5000)) { $script:F321ContainmentFailed = $false }
            throw 'Native output pipes did not close; no automatic retry'
        }
        $stdout = $outTask.GetAwaiter().GetResult(); $stderr = $errorTask.GetAwaiter().GetResult()
        if ($LogPrefix) {
            [IO.File]::WriteAllText($LogPrefix + '.stdout.log', $stdout, [Text.UTF8Encoding]::new($false))
            [IO.File]::WriteAllText($LogPrefix + '.stderr.log', $stderr, [Text.UTF8Encoding]::new($false))
        }
        if ($timedOut) { throw 'Native helper timeout: physical outcome ambiguous; no automatic retry' }
        if ($process.ExitCode -ne 0) { throw ('Native helper failed (' + $process.ExitCode + '): ' + $stderr + $stdout) }
        if ($job.ActiveProcesses -ne 0) {
            if (-not $job.TerminateAndWait(5000)) { $script:F321ContainmentFailed = $true }
            throw 'Unexpected live helper descendant after parent exit; no automatic retry'
        }
        return $stdout
    } finally {
        try {
            # Also cover nonzero exits/exceptions before normal child checks.
            # A failed termination/query leaves the physical lease unreleased.
            Complete-F321NativeContainment -Process $process -Job $job -Started $started
        } finally { $job.Dispose(); $process.Dispose() }
    }
}

function Get-F321Plan {
    param([ValidateSet('promote','rollback')][string]$Direction, [string]$ExecutorReview = '', [string]$ExecutorReviewSha256 = '')
    $arguments = @((Join-Path $script:F321Root 'tools/f321_execution_contract.py'), '--direction', $Direction)
    if ($ExecutorReview) { $arguments += @('--executor-review', $ExecutorReview, '--executor-review-sha256', $ExecutorReviewSha256) }
    $text = Invoke-F321Native -Program 'python' -Arguments $arguments -TimeoutSeconds 180
    return ($text | ConvertFrom-Json)
}

function Assert-F321ExecutionRequest {
    param([object]$Plan, [string]$Ack, [string]$Port, [string]$ExpectedPnpDeviceId, [string]$RouterHost)
    if ($Ack -cne $Plan.required_ack) { throw 'Exact F321 action ACK is required; no hardware accessed' }
    if ($Plan.executor_review_verified -isnot [bool] -or -not $Plan.executor_review_verified -or -not $Plan.local_preflight_pass) { throw 'F321 executor review/artifact gate unresolved' }
    if ($Port -ine 'COM3' -or $ExpectedPnpDeviceId -ine $Plan.uart_pnp_device_id -or $RouterHost -cne '192.168.1.90') { throw 'F321 is bound to the exact HGW/COM3 identity' }
    if ($Plan.write_target -cne 'mtd4/linux_live' -or $Plan.transport -cne 'uart-ymodem' -or $Plan.erase_bytes -ne 0x5e0000) { throw 'F321 physical scope mismatch' }
}

function Set-F321WriterEnvironment {
    param([object]$Plan)
    $saved = @{}
    foreach ($item in @(Get-ChildItem Env: | Where-Object { $_.Name -match '^OM_Q3_(FLASH_|F45_)' })) {
        $saved[$item.Name] = $item.Value
        [Environment]::SetEnvironmentVariable($item.Name, $null, 'Process')
    }
    foreach ($property in $Plan.environment.PSObject.Properties) { [Environment]::SetEnvironmentVariable($property.Name, [string]$property.Value, 'Process') }
    return $saved
}

function Restore-F321WriterEnvironment {
    param([hashtable]$Saved)
    foreach ($item in @(Get-ChildItem Env: | Where-Object { $_.Name -match '^OM_Q3_(FLASH_|F45_)' })) { [Environment]::SetEnvironmentVariable($item.Name, $null, 'Process') }
    foreach ($name in $Saved.Keys) { [Environment]::SetEnvironmentVariable($name, $Saved[$name], 'Process') }
}

function Invoke-F321Writer {
    param([object]$Plan, [string]$RunDir, [int]$FlashTimeoutSeconds = 1800)
    $saved = Set-F321WriterEnvironment -Plan $Plan
    try {
        $attemptDir = Join-Path $RunDir 'writer'
        $arguments = @((Join-Path $script:F321Root 'tools/f321_mtd4_one_shot.py'),
            '--execute', '--ack', $Plan.required_ack, '--port', 'COM3', '--client-ip', '192.168.1.90', '--host', '192.168.1.90',
            '--skip-reboot', '--timeout', [string]$FlashTimeoutSeconds, '--erase-bytes', '0x5e0000', '--transport', 'uart-ymodem',
            '--uart-attach-topaz', '--evidence-dir', $attemptDir, '--attempt-id', [Guid]::NewGuid().ToString('N'))
        [void](Invoke-F321Native -Program 'python' -Arguments $arguments -LogPrefix (Join-Path $RunDir 'writer-process') -TimeoutSeconds ($FlashTimeoutSeconds + 1500))
        $verified = Invoke-F321Native -Program 'python' -Arguments @((Join-Path $script:F321Root 'tools/f321_execution_contract.py'), '--direction', $Plan.direction, '--verify-writer', $attemptDir)
        $result = $verified | ConvertFrom-Json
        if ($result.status -cne 'PASS_VERIFIED_WRITER') { throw 'F321 writer did not prove its physical result' }
        [IO.File]::WriteAllText((Join-Path $RunDir 'verified-writer.json'), $verified, [Text.UTF8Encoding]::new($false))
        return $result
    } finally { Restore-F321WriterEnvironment -Saved $saved }
}

function Invoke-F321Reboot {
    param([object]$Plan, [string]$RunDir)
    [void](Invoke-F321Native -Program 'powershell.exe' -Arguments @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        (Join-Path $script:F321Root 'tools/reboot_to_topaz_prompt_sysrq.ps1'), '-Port', 'COM3', '-ExpectedPnpDeviceId', $Plan.uart_pnp_device_id,
        '-LogPath', (Join-Path $RunDir 'uart-to-topaz.log'), '-TimeoutSeconds', '240') -LogPrefix (Join-Path $RunDir 'reboot-process') -TimeoutSeconds 270)
}

function Invoke-F321PlatformGate {
    param([object]$Plan, [string]$RunDir)
    $output = Join-Path $RunDir 'platform'
    [void](Invoke-F321Native -Program 'python' -Arguments @((Join-Path $script:F321Root 'tools/post_flash_f214_device_gate.py'),
        '--host', '192.168.1.90', '--wait-seconds', '360', '--output-dir', $output, '--device-dir', $Plan.image.directory,
        '--expected-version', $Plan.image.version, '--known-hosts-name', $Plan.image.known_hosts) -LogPrefix (Join-Path $RunDir 'platform-process') -TimeoutSeconds 480)
    $status = Get-Content -LiteralPath (Join-Path $output 'status.json') -Raw | ConvertFrom-Json
    if ($status.status -cne 'PASS' -or $status.host -cne '192.168.1.90' -or @($status.checks.PSObject.Properties | Where-Object {$_.Value -isnot [bool] -or $_.Value -ne $true}).Count -ne 0) { throw 'Exact platform gate not proved' }
}

function Invoke-F321UiGate {
    param([string]$RunDir)
    $output = Join-Path $RunDir 'ui'
    [void](Invoke-F321Native -Program 'python' -Arguments @((Join-Path $script:F321Root 'tools/post_flash_f321_ui_gate.py'), '--execute', '--output-dir', $output) -LogPrefix (Join-Path $RunDir 'ui-process') -TimeoutSeconds 180)
    $status = Get-Content -LiteralPath (Join-Path $output 'result.json') -Raw | ConvertFrom-Json
    if ($status.status -cne 'PASS_UI_FILE_API_AND_PUBLIC_HTTP') { throw 'Exact F321 UI/API identity not proved' }
}

function Invoke-F321PhysicalCycle {
    param([object]$Plan, [string]$RunDir, [int]$FlashTimeoutSeconds = 1800,
          [object]$BorrowedHardwareGuard = $null, [object]$RecoveryBindingProof = $null,
          [string]$ExecutorReview = '', [string]$ExecutorReviewSha256 = '')
    $guard = $null; $owned = $false; $writerVerified = $false; $bindingProof = $null
    $result = [ordered]@{schema='openmitrastar.f321-physical-cycle/v1';direction=$Plan.direction;status='FAIL';candidate_sha256=$Plan.image.sha256;write_target='mtd4/linux_live';radio_mutation=$false;spi_probe_loaded=$false;release_eligible=$false}
    try {
        [void](Get-F319VerifiedRecoveryRehearsal -ResultPath $Plan.recovery_rehearsal)
        if (($null -eq $BorrowedHardwareGuard) -ne ($null -eq $RecoveryBindingProof)) { throw 'Incomplete in-process recovery ownership' }
        if ($BorrowedHardwareGuard) {
            if ($Plan.direction -cne 'rollback') { throw 'Only rollback may borrow the still-held hardware lease' }
            [void](Assert-F319BorrowedRecoveryGuard -Guard $BorrowedHardwareGuard -BindingProof $RecoveryBindingProof -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id)
            $guard = $BorrowedHardwareGuard
        } else {
            $guard = Enter-F319HardwareGuard -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id -PhysicalLockDir $Plan.physical_lock -Owner ('f321-' + $Plan.direction) -EvidenceDir $RunDir
            $owned = $true
            $binding = Assert-F319UartBinding -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id -RouterHost '192.168.1.90' -KnownHosts (Join-Path $Plan.current.directory $Plan.current.known_hosts) -ExpectedVersion $Plan.current.version -HardwareLease $guard
            $bindingProof = [pscustomobject]@{OwnerPid=$guard.OwnerPid;OwnerStartTicks=$guard.OwnerStartTicks;LeaseToken=$guard.LeaseToken;Binding=$binding}
        }
        [void](Assert-F319HardwareLease -PhysicalLockDir $guard.PhysicalLockDir -OwnerPid $guard.OwnerPid -OwnerStartTicks $guard.OwnerStartTicks -LeaseToken $guard.LeaseToken -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id)
        Invoke-F321Reboot -Plan $Plan -RunDir $RunDir
        $result.writer = Invoke-F321Writer -Plan $Plan -RunDir $RunDir -FlashTimeoutSeconds $FlashTimeoutSeconds
        $writerVerified = $true
        Invoke-F321PlatformGate -Plan $Plan -RunDir $RunDir
        [void](Assert-F319UartBinding -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id -RouterHost '192.168.1.90' -KnownHosts (Join-Path $Plan.image.directory $Plan.image.known_hosts) -ExpectedVersion $Plan.image.version -HardwareLease $guard)
        if ($Plan.direction -ceq 'promote') { Invoke-F321UiGate -RunDir $RunDir }
        $result.status = if ($Plan.direction -ceq 'promote') { 'PASS_F321_BOOT_PLATFORM_UI' } else { 'PASS_EXACT_F314_RESTORED' }
        return [pscustomobject]$result
    } catch {
        $failure = $_.Exception.Message
        $result.error = $failure
        if ($Plan.direction -ceq 'promote' -and $writerVerified -and $guard -and $bindingProof -and -not $script:F321ContainmentFailed) {
            $rollbackPlan = Get-F321Plan -Direction rollback -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256
            Assert-F321ExecutionRequest -Plan $rollbackPlan -Ack $rollbackPlan.required_ack -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id -RouterHost '192.168.1.90'
            $rollbackDir = Join-Path $RunDir 'automatic-exact-f314-rollback'
            [void][IO.Directory]::CreateDirectory($rollbackDir)
            $restored = Invoke-F321PhysicalCycle -Plan $rollbackPlan -RunDir $rollbackDir -FlashTimeoutSeconds $FlashTimeoutSeconds -BorrowedHardwareGuard $guard -RecoveryBindingProof $bindingProof -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256
            if ($restored.status -cne 'PASS_EXACT_F314_RESTORED') { throw 'Automatic F314 restore did not prove its result' }
            $result.status = 'FAIL_F321_EXACT_F314_RESTORED'
            throw ('F321 gate failed; exact F314 restored and verified: ' + $failure)
        }
        $result.status = 'STOP_NO_AUTOMATIC_RETRY'
        throw
    } finally {
        $result.helper_containment_verified = -not $script:F321ContainmentFailed
        [IO.File]::WriteAllText((Join-Path $RunDir 'result.json'), ($result | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
        if ($owned -and -not $script:F321ContainmentFailed) { Exit-F319HardwareGuard -Guard $guard }
    }
}
