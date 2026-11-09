# F320-only orchestration. Dot-sourcing defines functions; it performs no I/O.
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
. (Join-Path $PSScriptRoot 'f319_recovery_guard.ps1')

function Write-F320Json([string]$Path, [object]$Value) {
    $bytes = [Text.Encoding]::UTF8.GetBytes(($Value | ConvertTo-Json -Depth 14) + "`n")
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
}

function Assert-F320ExecutionRequest([string]$Ack, [bool]$PowerCycleReady, [string]$Action) {
    if ($Ack -cne 'OPENMITRASTAR_F320_MTD4_66FF3E8F') { throw 'Exact F320 campaign acknowledgement required; F319 authority is not reusable' }
    if ($Action -notin @('Promote', 'RestoreF314')) { throw 'Unknown F320 action' }
    if ($Action -eq 'Promote' -and -not $PowerCycleReady) { throw 'HGW-only manual power-cycle contingency must be confirmed before promotion' }
}

function Get-F320Contract([string]$QualificationPath) {
    $arguments = @((Join-Path $PSScriptRoot 'f320_campaign_contract.py'))
    if ($QualificationPath) { $arguments += @('--qualification', $QualificationPath) }
    $output = & python @arguments
    if ($LASTEXITCODE -ne 0) { throw 'F320 file-only artifact/qualification validation failed' }
    return (($output -join "`n") | ConvertFrom-Json)
}

function Assert-F320Qualified([object]$Context) {
    if (-not $Context.QualificationPath) { throw 'Missing F320 offline qualification' }
    $verified = Get-F320Contract $Context.QualificationPath
    if ($verified.qualification -ne 'PASS_OFFLINE') { throw 'F320 executor is not qualified' }
    $Context.Contract = $verified
    $Context.Recovery = Get-F319VerifiedRecoveryRehearsal -ResultPath $Context.RecoveryPath
}

function Assert-F320LocalTftp([object]$Context) {
    if ($Context.TftpHost -notmatch '^192\.168\.1\.(\d{1,3})$' -or
        [int]$Matches[1] -notin 2..254 -or $Context.TftpHost -eq '192.168.1.90') {
        throw 'Explicit local management-subnet TFTP address required'
    }
    $address = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object { $_.IPAddress -eq $Context.TftpHost -and $_.AddressState -eq 'Preferred' })
    if ($address.Count -ne 1) { throw 'TFTP address is not uniquely assigned to this computer' }
}

function Invoke-F320Ssh([object]$Context, [string]$Tag, [string]$Script, [int]$Seconds = 20) {
    $known = $Context.Contract.images.$Tag.known_hosts
    $arguments = @('-i', "$env:USERPROFILE\.ssh\id_ed25519", '-o', 'IdentitiesOnly=yes',
        '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', '-o', 'StrictHostKeyChecking=yes',
        '-o', "UserKnownHostsFile=$known", '-o', 'LogLevel=ERROR', 'root@192.168.1.90', 'sh', '-s')
    return (Invoke-F319SshScript -SshPath (Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe') -Arguments $arguments -Script $Script -TimeoutSeconds $Seconds)
}

function Assert-F320ReadOnlyIdentity([object]$Context, [string]$Tag) {
    $remote = @'
set -eu
grep -Fqx 'OPENMITRASTAR_PRODUCT_VERSION=__VERSION__' /etc/openmitrastar/release
test "$(uname -r)" = 5.10.260-openmitrastar-radiohw
! grep -Eiq '(^|[ _-])(spi|store).*probe|^qtn_topaz_spi_' /proc/modules
echo OMF320_PINNED_IDENTITY_PASS
'@
    $remote = $remote.Replace('__VERSION__', $Context.Contract.images.$Tag.version)
    $result = Invoke-F320Ssh $Context $Tag $remote
    if ($result.ExitCode -ne 0 -or @($result.Stdout -split '\r?\n') -notcontains 'OMF320_PINNED_IDENTITY_PASS') {
        throw 'Pinned SSH version/kernel or unloaded-module identity gate failed'
    }
}

function Enter-F320Guard([object]$Context) {
    return (Enter-F319HardwareGuard -Port COM3 -ExpectedPnpDeviceId $Context.Contract.pnp -PhysicalLockDir $Context.LockDir -Owner f320-campaign -EvidenceDir $Context.OutputDir)
}

function Get-F320Binding([object]$Context, [string]$Tag) {
    return (Assert-F319UartBinding -Port COM3 -ExpectedPnpDeviceId $Context.Contract.pnp -RouterHost '192.168.1.90' -KnownHosts $Context.Contract.images.$Tag.known_hosts -ExpectedVersion $Context.Contract.images.$Tag.version -HardwareLease $Context.Guard)
}

function Assert-F320BoundGuard([object]$Context) {
    $guard = $Context.Guard
    $proof = $Context.BindingProof
    # No saved binding JSON, different process or F314 rehearsal binding may
    # stand in for this campaign's original F319 (or restore-only F320) nonce.
    if ($null -eq $guard -or $null -eq $proof -or $guard.OwnerPid -ne $PID -or
        $proof.OwnerPid -ne $PID -or $guard.OwnerStartTicks -ne $proof.OwnerStartTicks -or
        $guard.LeaseToken -cne $proof.LeaseToken -or $null -eq $guard.LeaseStream -or -not $guard.LeaseStream.CanWrite -or
        $proof.Binding.NonceObserved -isnot [bool] -or $proof.Binding.NonceObserved -ne $true -or
        $proof.Binding.ExpectedVersion -cne $Context.Contract.images.($Context.InitialTag).version -or
        $proof.Binding.RouterHost -cne '192.168.1.90' -or $proof.Binding.Port -cne 'COM3' -or
        $proof.Binding.PnpDeviceId -ine $Context.Contract.pnp) {
        throw 'F320 mutation requires the original authenticated binding and same live in-process guard'
    }
    [void](Assert-F319HardwareLease -PhysicalLockDir $Context.LockDir -OwnerPid $guard.OwnerPid -OwnerStartTicks $guard.OwnerStartTicks -LeaseToken $guard.LeaseToken -Port COM3 -ExpectedPnpDeviceId $Context.Contract.pnp)
    [void](Get-F319SerialDevice -Port COM3 -ExpectedPnpDeviceId $Context.Contract.pnp)
}

function Invoke-F320Bootbase([object]$Context, [string]$Label) {
    Assert-F320BoundGuard $Context
    & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'reboot_to_topaz_prompt_sysrq.ps1') -Port COM3 -ExpectedPnpDeviceId $Context.Contract.pnp -LogPath (Join-Path $Context.OutputDir "$Label-to-topaz.log") -TimeoutSeconds 180 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Could not acquire Bootbase; no automatic retry' }
}

function Invoke-F320Writer([object]$Context, [string]$Target, [string]$Current, [string]$Label) {
    Assert-F320BoundGuard $Context
    $image = $Context.Contract.images.$Target
    $previous = $Context.Contract.images.$Current
    $folder = $image.folder; $stem = $image.stem
    # Explicitly pin the shared backend; never inherit an alternate backend or
    # transport. Environment is restored even on a failed or ambiguous write.
    $settings = @{
        OM_Q3_FLASH_ACK='OPENMITRASTAR_F320_MTD4_66FF3E8F'; OM_Q3_FLASH_BUILD_DIR=$folder
        OM_Q3_FLASH_CANDIDATE=$image.path; OM_Q3_FLASH_BOOTBASE_CONTRACT=(Join-Path $folder 'bootbase-contract.json')
        OM_Q3_FLASH_MANIFEST=(Join-Path $folder 'manifest.json'); OM_Q3_FLASH_INITRAMFS=(Join-Path $folder "$stem.kernel.raw.bin")
        OM_Q3_FLASH_KCONFIG=(Join-Path $folder "$stem.config"); OM_Q3_FLASH_LAYOUT_MODE='squashfs-split'
        OM_Q3_FLASH_ROOTFS_IMAGE=(Join-Path $folder "$stem.rootfs.squashfs"); OM_Q3_FLASH_DTB=(Join-Path $folder "$stem.dtb")
        OM_Q3_FLASH_ROOTFS_OFFSET='0x180000'; OM_Q3_FLASH_EXPECTED_SHA256=$image.sha256; OM_Q3_FLASH_EXPECTED_BYTES='5292032'
        OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32=$previous.full_slot_crc32; OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256=$previous.full_slot_sha256
        OM_Q3_F45_REQUIRE_BACKUP_LIVE_SLOT_MATCH='0'
        OM_Q3_FLASH_POWERSHELL_BACKEND=(Join-Path $PSScriptRoot 'q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_bootbase_flash.ps1')
    }
    $saved = @{}
    $attempt = Join-Path $Context.OutputDir $Label
    try {
        foreach ($key in $settings.Keys) {
            $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
            [Environment]::SetEnvironmentVariable($key, $settings[$key], 'Process')
        }
        & python (Join-Path $PSScriptRoot 'run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py') --execute --ack OPENMITRASTAR_F320_MTD4_66FF3E8F --port COM3 --host 192.168.1.90 --client-ip 192.168.1.90 --server-ip $Context.TftpHost --skip-reboot --transport tftp --uart-attach-topaz --timeout 900 --erase-bytes 0x5e0000 --evidence-dir $attempt --attempt-id ([Guid]::NewGuid().ToString('N')) | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Writer failed or outcome ambiguous; do not retry or change transport' }
        $validation = & python (Join-Path $PSScriptRoot 'f320_campaign_contract.py') --writer-result (Join-Path $attempt 'result.json') --tag $Target
        if ($LASTEXITCODE -ne 0 -or (($validation -join "`n") | ConvertFrom-Json).status -ne 'PASS') {
            throw 'Writer completion/readback evidence rejected; no automatic second write'
        }
    } finally {
        foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key], 'Process') }
    }
}

function Invoke-F320Platform([object]$Context, [string]$Tag, [string]$Label) {
    $image = $Context.Contract.images.$Tag
    & python (Join-Path $PSScriptRoot 'post_flash_f214_device_gate.py') --host 192.168.1.90 --wait-seconds 120 --output-dir (Join-Path $Context.OutputDir $Label) --device-dir $image.folder --expected-version $image.version --known-hosts-name "known_hosts.$Tag" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Management/UI/API/dual-radio control-plane gate failed' }
}

function Invoke-F320Probe([object]$Context) {
    Assert-F320BoundGuard $Context
    Assert-F320ReadOnlyIdentity $Context f320
    $binding = Get-F320Binding $Context f320
    Write-F320Json (Join-Path $Context.OutputDir 'preprobe-binding.json') $binding
    $output = Join-Path $Context.OutputDir 'runtime'
    New-Item -ItemType Directory -Path $output -ErrorAction Stop | Out-Null
    $uartDir = Join-Path $output 'uart'
    $runId = 'f320-' + [Guid]::NewGuid().ToString('N')
    $guard = $Context.Guard
    $uart = $null
    $captureDeadline = [DateTime]::UtcNow
    $failure = $null
    $result = $null
    $captureComplete = $false
    try {
        $arguments = @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
            (Join-Path $PSScriptRoot 'capture_topaz_uart_resilient.ps1'), '-Port', 'COM3',
            '-ExpectedPnpDeviceId', $Context.Contract.pnp, '-ExternalOwnershipHeld',
            '-ExternalGuardLockDir', $Context.LockDir, '-ExternalGuardOwnerPid', [string]$guard.OwnerPid,
            '-ExternalGuardOwnerStartTicks', [string]$guard.OwnerStartTicks, '-ExternalGuardToken', $guard.LeaseToken,
            '-Seconds', '60', '-OutputDirectory', $uartDir, '-RunId', $runId)
        $uart = Start-Process -FilePath powershell.exe -WindowStyle Hidden -ArgumentList (($arguments | ForEach-Object { ConvertTo-F319NativeArgument $_ }) -join ' ') -RedirectStandardOutput (Join-Path $output 'uart.stdout.log') -RedirectStandardError (Join-Path $output 'uart.stderr.log') -PassThru
        [void]$uart.Handle # Retain the real ExitCode on Windows PowerShell 5.1.
        $captureDeadline = [DateTime]::UtcNow.AddSeconds(70)
        [void](Wait-F319UartCaptureReady -StatusPath (Join-Path $uartDir 'capture-status.json') -Process $uart -ExpectedRunId $runId -ExpectedPnpDeviceId $Context.Contract.pnp -TimeoutSeconds 10)
        $remote = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'f320_spi_read.sh')).Replace('__CAPTURE_RUN__', $runId)
        Assert-F320BoundGuard $Context
        [void](Wait-F319UartCaptureReady -StatusPath (Join-Path $uartDir 'capture-status.json') -Process $uart -ExpectedRunId $runId -ExpectedPnpDeviceId $Context.Contract.pnp -TimeoutSeconds 2)
        $Context.ProbeAttempted = $true
        $result = Invoke-F320Ssh $Context f320 $remote 30
        [IO.File]::WriteAllText((Join-Path $output 'probe.stdout.log'), $result.Stdout)
        [IO.File]::WriteAllText((Join-Path $output 'probe.stderr.log'), $result.Stderr)
        if ($result.ExitCode -ne 0) { throw 'SPI probe SSH returned nonzero; never retry insmod' }
    } catch {
        $failure = $_.Exception.Message
    } finally {
        # A timeout must not kill the evidence before the fixed RX window ends.
        # Each wait is at most 30s; the whole capture has a fixed deadline.
        # No reset is attempted from this function.
        if ($uart) {
            try {
                while (-not $uart.HasExited -and [DateTime]::UtcNow -lt $captureDeadline) {
                    $remaining = [int][Math]::Ceiling(($captureDeadline - [DateTime]::UtcNow).TotalMilliseconds)
                    [void]$uart.WaitForExit([Math]::Min(30000, [Math]::Max(1, $remaining)))
                }
                if (-not $uart.HasExited) { throw 'RX process exceeded its capture window' }
                $uart.Refresh()
                [void](Assert-F319UartCaptureComplete -StatusPath (Join-Path $uartDir 'capture-status.json') -RawPath (Join-Path $uartDir 'uart.raw.bin') -TextPath (Join-Path $uartDir 'uart.log') -ExpectedRunId $runId -ExpectedPnpDeviceId $Context.Contract.pnp -CapturePid $uart.Id -CaptureExitCode $uart.ExitCode)
                $captureComplete = $true
            } catch { $failure = "$failure; $($_.Exception.Message)" }
            finally {
                if (-not $uart.HasExited) { $uart.Kill(); [void]$uart.WaitForExit(3000) }
            }
        }
    }
    $uartLog = Join-Path $uartDir 'uart.log'
    if (Test-Path -LiteralPath $uartLog) {
        $Context.RuntimeHardFault = [bool](Select-String -LiteralPath $uartLog -Quiet -Pattern 'Machine Check|kernel panic|Oops:|BUG:|Misaligned Access|MuC has halted|MuC:.*exception|EV_TLB|EV_ProtV')
    }
    $checks = $null
    if (-not $failure -and $captureComplete) {
        $validation = & python (Join-Path $PSScriptRoot 'f320_campaign_contract.py') --runtime-dir $output --run-id $runId
        if ($LASTEXITCODE -ne 0) { $failure = 'Single read/unload/zero-write/UART snapshot invariants failed' }
        else { $checks = (($validation -join "`n") | ConvertFrom-Json) }
    }
    $evidence = @()
    foreach ($file in @('probe.stdout.log','probe.stderr.log','uart/capture-status.json','uart/uart.raw.bin','uart/uart.log')) {
        $path = Join-Path $output $file
        if (Test-Path -LiteralPath $path -PathType Leaf) { $evidence += @{file=$file;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()} }
    }
    $report = [ordered]@{schema='openmitrastar.f320-spi-control-runtime/v1';generated_at=[DateTime]::UtcNow.ToString('o');status=if ($failure) {'FAIL'} else {'PASS'};
        firmware_sha256=$Context.Contract.images.f320.sha256;module_sha256='6ec075b4875890d5f366ff568932b591b59cc15231282274d77bb868a768a06a';
        error=$failure;probe_attempted=$Context.ProbeAttempted;hard_fault=$Context.RuntimeHardFault;capture_complete=$captureComplete;
        capture_run_id=$runId;capture_pid=if ($uart) {$uart.Id} else {$null};capture_exit_code=if ($uart -and $uart.HasExited) {$uart.ExitCode} else {$null};checks=$checks;
        evidence=$evidence;flash=$false;mtd_writes=$false}
    Write-F320Json (Join-Path $output 'result.json') $report
    if ($failure) { throw $failure }
}

function Restore-F320ExactF314([object]$Context) {
    Assert-F320BoundGuard $Context
    # Only a responsive, pinned F320 without a surviving probe is a recoverable
    # automatic branch. A CPU halt is explicitly not treated as SysRq-recoverable.
    Assert-F320ReadOnlyIdentity $Context f320
    Invoke-F320Bootbase $Context rollback
    Invoke-F320Writer $Context f314 f320 f314-restore
    Invoke-F320Platform $Context f314 postrestore-f314
    Write-F320Json (Join-Path $Context.OutputDir 'restored-binding.json') (Get-F320Binding $Context f314)
}

function Invoke-F320Campaign([object]$Context) {
    $status = 'NO_GO'
    $failure = $null
    $recoveryError = $null
    try {
        Assert-F320ExecutionRequest $Context.Ack $Context.PowerCycleReady $Context.Action
        Assert-F320Qualified $Context
        Assert-F320LocalTftp $Context
        # Read-only pinned SSH happens BEFORE any UART open, even RX binding.
        Assert-F320ReadOnlyIdentity $Context $Context.InitialTag
        $Context.Guard = Enter-F320Guard $Context
        $Context.HardwareActions = $true
        $binding = Get-F320Binding $Context $Context.InitialTag
        $Context.BindingProof = [pscustomobject]@{OwnerPid=$Context.Guard.OwnerPid;OwnerStartTicks=$Context.Guard.OwnerStartTicks;LeaseToken=$Context.Guard.LeaseToken;Binding=$binding}
        Write-F320Json (Join-Path $Context.OutputDir 'initial-binding.json') $binding
        Assert-F320BoundGuard $Context
        if ($Context.Action -eq 'RestoreF314') {
            Restore-F320ExactF314 $Context
            $status = 'PASS_EXACT_F314_RESTORED'
        } else {
            Invoke-F320Bootbase $Context promotion
            $Context.FlashAttempted = $true
            Invoke-F320Writer $Context f320 f319 f320-install
            $Context.FlashCompleted = $true
            Invoke-F320Platform $Context f320 postflash-f320
            Invoke-F320Probe $Context
            Invoke-F320Platform $Context f320 postprobe-f320
            $status = 'PASS_F320_SINGLE_CONTROL_READ_UNLOAD'
        }
    } catch {
        $failure = $_.Exception.Message
        if ($Context.FlashCompleted -and $Context.Action -eq 'Promote') {
            if ($Context.RuntimeHardFault) { $status = 'MANUAL_HGW_POWER_CYCLE_REQUIRED' }
            else {
                try {
                    Restore-F320ExactF314 $Context
                    $status = 'FAIL_F320_EXACT_F314_RESTORED'
                } catch {
                    $recoveryError = $_.Exception.Message
                    $status = 'MANUAL_RECOVERY_REQUIRED_NO_RETRY'
                }
            }
        } elseif ($Context.FlashAttempted -or $Context.Action -eq 'RestoreF314') {
            $status = 'UNPROVEN_WRITE_OR_RECOVERY_NO_RETRY'
        }
    } finally {
        Exit-F319HardwareGuard -Guard $Context.Guard
    }
    $report = [ordered]@{schema='openmitrastar.f320-campaign-result/v1';generated_at=[DateTime]::UtcNow.ToString('o');status=$status;
        action=$Context.Action;error=$failure;recovery_error=$recoveryError;hardware_actions=$Context.HardwareActions;
        flash_attempted=$Context.FlashAttempted;flash_completed=$Context.FlashCompleted;probe_attempted=$Context.ProbeAttempted;
        hard_fault=$Context.RuntimeHardFault;qualification=$Context.QualificationPath;f319_preserved_as_artifact=$true;
        protected_partitions_written=$false;release_pass=$false}
    Write-F320Json (Join-Path $Context.OutputDir 'result.json') $report
    return [pscustomobject]$report
}
