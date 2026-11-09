[CmdletBinding()]
param(
    [ValidateSet('leases', 'captures', 'transport', 'echo-child', 'verify-child', 'contend-child', 'orphan-child')][string]$Action,
    [Parameter(Mandatory = $true)][string]$Scope,
    [Parameter(Mandatory = $true)][string]$FakeIdentity,
    [string]$LockDir = '', [int]$OwnerId = 0, [long]$OwnerTicks = 0, [string]$Token = '',
    [AllowEmptyString()][string]$QuoteValue = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($FakeIdentity -cnotmatch '^OFFLINE_F319_[0-9a-f]{32}$') { throw 'Only synthetic identities are allowed' }
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
# Stub the sole device-enumeration dependency. No serial/SSH function is called.
function Get-F319SerialDevice {
    param([string]$Port, [string]$ExpectedPnpDeviceId)
    if ($Port -cne 'COM999' -or $ExpectedPnpDeviceId -cne $FakeIdentity) { throw 'Hardware access forbidden in offline test' }
    return [pscustomobject]@{DeviceID='COM999';PNPDeviceID=$FakeIdentity;Name='Synthetic offline device'}
}
$engine = (Get-Process -Id $PID).Path
$self = $PSCommandPath
if ($Action -eq 'echo-child') {
    @{argument=$QuoteValue;stdin=[Console]::In.ReadToEnd()} | ConvertTo-Json -Compress
    exit 0
}
function New-TestGuard([string]$Directory) {
    return (Enter-F319HardwareGuard -Port COM999 -ExpectedPnpDeviceId $FakeIdentity -PhysicalLockDir $Directory -Owner offline-test -EvidenceDir $Scope)
}
function Invoke-Child([string]$Mode, [string]$Directory, [int]$ParentId, [long]$Ticks, [string]$Nonce) {
    $arguments = @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $self,
        '-Action', $Mode, '-Scope', $Scope, '-FakeIdentity', $FakeIdentity, '-LockDir', $Directory,
        '-OwnerId', [string]$ParentId, '-OwnerTicks', [string]$Ticks, '-Token', $Nonce)
    $output = & $engine @arguments
    if ($LASTEXITCODE -ne 0) { throw "Offline child failed: $output" }
    return ($output | ConvertFrom-Json)
}
if ($Action -eq 'verify-child') {
    try {
        [void](Assert-F319HardwareLease -PhysicalLockDir $LockDir -OwnerPid $OwnerId -OwnerStartTicks $OwnerTicks -LeaseToken $Token -Port COM999 -ExpectedPnpDeviceId $FakeIdentity)
        @{accepted=$true} | ConvertTo-Json -Compress
    } catch { @{accepted=$false;reason=$_.Exception.Message} | ConvertTo-Json -Compress }
    exit 0
}
if ($Action -eq 'contend-child') {
    $childGuard = $null
    try { $childGuard = New-TestGuard $LockDir; @{accepted=$true} | ConvertTo-Json -Compress }
    catch { @{accepted=$false;reason=$_.Exception.Message} | ConvertTo-Json -Compress }
    finally { if ($childGuard) { Exit-F319HardwareGuard $childGuard } }
    exit 0
}
if ($Action -eq 'orphan-child') {
    $orphanGuard = New-TestGuard $LockDir
    @{owner_id=$orphanGuard.OwnerPid;ticks=$orphanGuard.OwnerStartTicks;token=$orphanGuard.LeaseToken} | ConvertTo-Json -Compress
    # Intentional process death without normal cleanup; only synthetic files.
    exit 0
}
$cases = [Collections.Generic.List[object]]::new()
function Record([string]$Name, [bool]$Pass) {
    if (-not $Pass) { throw "Offline guard case failed: $Name" }
    $cases.Add([pscustomobject]@{name=$Name;status='PASS'})
}
if ($Action -eq 'leases') {
    $LockDir = Join-Path $Scope 'owned.lock'
    $guard = New-TestGuard $LockDir
    try {
        $lease = Read-F319Lease $LockDir
        $names = @(Get-F319MutexNames $FakeIdentity)
        Record 'two-exact-independent-mutex-names' ($names.Count -eq 2 -and $lease.mutexes.Count -eq 2 -and $names[0] -cne $names[1])
        $valid = Invoke-Child verify-child $LockDir $guard.OwnerPid $guard.OwnerStartTicks $guard.LeaseToken
        Record 'live-parent-lease-and-both-mutexes-accepted' ($valid.accepted -eq $true)
        $collision = Invoke-Child contend-child (Join-Path $Scope 'contender.lock') 1 1 'unused'
        Record 'second-process-blocked-before-lock-directory-creation' (-not $collision.accepted -and -not (Test-Path -LiteralPath (Join-Path $Scope 'contender.lock')))
        $wrong = Invoke-Child verify-child $LockDir $guard.OwnerPid $guard.OwnerStartTicks ('0' * 32)
        Record 'wrong-lease-token-rejected' (-not $wrong.accepted)
        $wrong = Invoke-Child verify-child $LockDir $guard.OwnerPid ($guard.OwnerStartTicks + 1) $guard.LeaseToken
        Record 'reused-pid-or-wrong-start-time-rejected' (-not $wrong.accepted)
        $fake = Join-Path $Scope 'copied.lock'; New-Item -ItemType Directory -Path $fake | Out-Null
        [IO.File]::WriteAllText((Join-Path $fake 'owner.json'), ($lease | ConvertTo-Json))
        $copied = Invoke-Child verify-child $fake $guard.OwnerPid $guard.OwnerStartTicks $guard.LeaseToken
        Record 'copied-metadata-without-open-file-lease-rejected' (-not $copied.accepted)
        foreach ($index in @(0, 1)) {
            $guard.OwnedMutexes[$index].ReleaseMutex()
            try {
                $released = Invoke-Child verify-child $LockDir $guard.OwnerPid $guard.OwnerStartTicks $guard.LeaseToken
                Record "released-mutex-$index-rejected" (-not $released.accepted)
            } finally {
                if (-not $guard.OwnedMutexes[$index].WaitOne(0)) { throw 'Cannot restore synthetic mutex' }
            }
        }
        $guard.LeaseStream.Dispose()
        $released = Invoke-Child verify-child $LockDir $guard.OwnerPid $guard.OwnerStartTicks $guard.LeaseToken
        Record 'closed-lease-rejected-even-while-owner-process-is-alive' (-not $released.accepted)
    } finally { Exit-F319HardwareGuard $guard }
    Record 'normal-cleanup-removes-only-owned-lock' (-not (Test-Path -LiteralPath $LockDir))
    $orphanDir = Join-Path $Scope 'orphan.lock'
    $orphan = Invoke-Child orphan-child $orphanDir 1 1 'unused'
    $dead = Invoke-Child verify-child $orphanDir $orphan.owner_id $orphan.ticks $orphan.token
    Record 'dead-parent-with-stale-directory-rejected' (-not $dead.accepted)
    $guard = New-TestGuard $LockDir
    $foreign = Join-Path $LockDir 'keep.txt'
    [IO.File]::WriteAllText($foreign, 'must survive non-recursive cleanup')
    $cleanupFailed = $false
    try { Exit-F319HardwareGuard $guard } catch { $cleanupFailed = $true }
    Record 'unexpected-file-preserved-and-cleanup-reports-failure' ($cleanupFailed -and (Test-Path -LiteralPath $foreign))
    $released = Invoke-Child contend-child (Join-Path $Scope 'after-cleanup.lock') 1 1 'unused'
    Record 'mutexes-released-even-when-cleanup-fails' ($released.accepted -eq $true)
}
if ($Action -eq 'captures') {
    $run = 'f319-offline-' + [Guid]::NewGuid().ToString('N')
    $body = $run + "_BEGIN`r`nsynthetic owner probe`r`n" + $run + "_END`r`n"
    $base = @{schema='openmitrastar.uart-capture-status/v1';run_id=$run;capture_pid=34567;state='complete';
        ready=$true;rx_only=$true;dtr=$false;rts=$false;gaps=0;error=$null;pinned_pnp_device_id=$FakeIdentity;
        bytes=[Text.Encoding]::ASCII.GetByteCount($body)}
    foreach ($case in @('valid', 'wrong-run', 'wrong-pid', 'wrong-pnp', 'gap', 'error', 'unfinished', 'not-rx-only',
        'dtr-enabled', 'wrong-byte-count', 'missing-raw', 'missing-status', 'missing-text', 'raw-text-mismatch',
        'missing-end', 'wrong-order', 'duplicate-begin', 'zero-bytes', 'failed-process')) {
        $status = $base | ConvertTo-Json | ConvertFrom-Json
        $textBody = $body; $rawBody = $body; $exitCode = 0
        switch ($case) {
            'wrong-run' { $status.run_id = 'other' }
            'wrong-pid' { $status.capture_pid = 34568 }
            'wrong-pnp' { $status.pinned_pnp_device_id = 'other' }
            'gap' { $status.gaps = 1 }
            'error' { $status.error = 'device lost' }
            'unfinished' { $status.state = 'capturing' }
            'not-rx-only' { $status.rx_only = $false }
            'dtr-enabled' { $status.dtr = $true }
            'wrong-byte-count' { $status.bytes += 1 }
            'raw-text-mismatch' { $rawBody = $body + 'extra' }
            'missing-end' { $textBody = $body.Replace($run + '_END', 'missing'); $rawBody = $textBody }
            'wrong-order' { $textBody = $run + "_END`n" + $run + "_BEGIN`n"; $rawBody = $textBody }
            'duplicate-begin' { $textBody = $run + "_BEGIN`n" + $body; $rawBody = $textBody }
            'zero-bytes' { $textBody = ''; $rawBody = '' }
            'failed-process' { $exitCode = 1 }
        }
        if ($case -in @('missing-end', 'wrong-order', 'duplicate-begin', 'zero-bytes')) { $status.bytes = [Text.Encoding]::ASCII.GetByteCount($rawBody) }
        $dir = Join-Path $Scope $case; New-Item -ItemType Directory -Path $dir | Out-Null
        $rawPath = Join-Path $dir 'uart.raw.bin'; $textPath = Join-Path $dir 'uart.log'; $statusPath = Join-Path $dir 'capture-status.json'
        if ($case -ne 'missing-raw') { [IO.File]::WriteAllBytes($rawPath, [Text.Encoding]::ASCII.GetBytes($rawBody)) }
        if ($case -ne 'missing-text') { [IO.File]::WriteAllText($textPath, $textBody, [Text.UTF8Encoding]::new($false)) }
        if ($case -ne 'missing-status') { [IO.File]::WriteAllText($statusPath, ($status | ConvertTo-Json)) }
        $accepted = $true
        try { [void](Assert-F319UartCaptureComplete -StatusPath $statusPath -RawPath $rawPath -TextPath $textPath -ExpectedRunId $run -ExpectedPnpDeviceId $FakeIdentity -CapturePid 34567 -CaptureExitCode $exitCode) }
        catch { $accepted = $false }
        Record "capture-$case" ($accepted -eq ($case -eq 'valid'))
    }
}
if ($Action -eq 'transport') {
    $scriptData = "set -eu`r`nprintf '%s\n' '`"literal`"'`r`n"
    $values = @('', 'path with spaces\', 'embedded"quote', 'many\\"slashes\\', "single'quotes")
    $index = 0
    foreach ($value in $values) {
        $arguments = @('-NoProfile', '-NonInteractive', '-File', $self, '-Action', 'echo-child',
            '-Scope', $Scope, '-FakeIdentity', $FakeIdentity, '-QuoteValue', $value)
        $result = Invoke-F319SshScript -SshPath $engine -Arguments $arguments -Script $scriptData -TimeoutSeconds 10
        $decoded = $result.Stdout | ConvertFrom-Json
        Record "native-argv-and-lf-stdin-$index" ($result.ExitCode -eq 0 -and $decoded.argument -ceq $value -and $decoded.stdin -ceq ($scriptData.Replace("`r`n", "`n") + "`n"))
        $index++
    }
    $result = Invoke-F319SshScript -SshPath $engine -Arguments @('-NoProfile', '-NonInteractive', '-Command', 'exit 7') -Script 'unused' -TimeoutSeconds 10
    Record 'native-nonzero-exit-preserved' ($result.ExitCode -eq 7)
    $timedOut = $false
    try { [void](Invoke-F319SshScript -SshPath $engine -Arguments @('-NoProfile', '-NonInteractive', '-Command', 'Start-Sleep -Seconds 5') -Script 'unused' -TimeoutSeconds 1) }
    catch { $timedOut = $_.Exception.Message -like '*timed out*' }
    Record 'native-process-timeout-is-failure' $timedOut
}
@{status='PASS';engine=$PSVersionTable.PSVersion.ToString();cases=@($cases.ToArray());hardware_actions=$false} | ConvertTo-Json -Depth 5
