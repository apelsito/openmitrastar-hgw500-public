Set-StrictMode -Version Latest

function Get-F319MutexNames {
    param([Parameter(Mandatory = $true)][string]$ExpectedPnpDeviceId)
    $identity = $ExpectedPnpDeviceId.ToUpperInvariant() -replace '[^A-Za-z0-9_.-]', '_'
    # Parentheses are essential: comma binds inside + in the former expression.
    return @(('Local\OpenMitraStar-UART-' + $identity), ('Local\OpenRouterLab-UART-' + $identity))
}

function ConvertTo-F319NativeArgument {
    param([AllowEmptyString()][string]$Value)
    # Windows CommandLineToArgvW quoting, including embedded quotes/trailing slashes.
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Invoke-F319SshScript {
    param(
        [Parameter(Mandatory = $true)][string]$SshPath,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Script,
        [ValidateRange(1, 120)][int]$TimeoutSeconds = 45
    )
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $SshPath
    $start.Arguments = (($Arguments | ForEach-Object { ConvertTo-F319NativeArgument $_ }) -join ' ')
    $start.UseShellExecute = $false; $start.CreateNoWindow = $true
    $start.RedirectStandardInput = $true; $start.RedirectStandardOutput = $true; $start.RedirectStandardError = $true
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $start
    $didStart = $false
    try {
        if (-not $process.Start()) { throw 'Could not start the bounded SSH process' }
        $didStart = $true
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        # stdin preserves POSIX quotes; Windows argv contains only ssh options and sh -s.
        $process.StandardInput.Write($Script.Replace("`r`n", "`n") + "`n")
        $process.StandardInput.Close()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill(); [void]$process.WaitForExit(3000)
            throw 'SSH script timed out; runtime outcome is unproven'
        }
        return [pscustomobject]@{ExitCode=$process.ExitCode;Stdout=$stdoutTask.GetAwaiter().GetResult();Stderr=$stderrTask.GetAwaiter().GetResult()}
    } finally {
        try {
            if ($didStart -and -not $process.HasExited) { $process.Kill(); [void]$process.WaitForExit(3000) }
        } finally { $process.Dispose() }
    }
}

function Read-F319Lease {
    param([Parameter(Mandatory = $true)][string]$PhysicalLockDir)
    $directory = Get-Item -LiteralPath $PhysicalLockDir -ErrorAction Stop
    if (-not $directory.PSIsContainer -or ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Physical lock must be a real directory'
    }
    $path = Join-Path $directory.FullName 'owner.json'
    $stream = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        $reader = [IO.StreamReader]::new($stream)
        try { return ($reader.ReadToEnd() | ConvertFrom-Json) } finally { $reader.Dispose() }
    } finally { $stream.Dispose() }
}

function Assert-F319HardwareLease {
    param(
        [Parameter(Mandatory = $true)][string]$PhysicalLockDir,
        [Parameter(Mandatory = $true)][int]$OwnerPid,
        [Parameter(Mandatory = $true)][long]$OwnerStartTicks,
        [Parameter(Mandatory = $true)][string]$LeaseToken,
        [Parameter(Mandatory = $true)][string]$Port,
        [Parameter(Mandatory = $true)][string]$ExpectedPnpDeviceId
    )
    if ($OwnerPid -le 0 -or $OwnerStartTicks -le 0 -or $LeaseToken -cnotmatch '^[0-9a-f]{32}$') {
        throw 'Missing parent hardware lease credentials'
    }
    $ownerProcess = [Diagnostics.Process]::GetProcessById($OwnerPid)
    try {
        if ($ownerProcess.HasExited -or $ownerProcess.StartTime.ToUniversalTime().Ticks -ne $OwnerStartTicks) {
            throw 'Hardware lease owner is not the original live process'
        }
        $lease = Read-F319Lease -PhysicalLockDir $PhysicalLockDir
        $names = @(Get-F319MutexNames -ExpectedPnpDeviceId $ExpectedPnpDeviceId)
        if ($lease.schema -ne 'openmitrastar.physical-lock/v3' -or $lease.pid -ne $OwnerPid -or
            $lease.process_start_ticks -ne $OwnerStartTicks -or $lease.lease_token -cne $LeaseToken -or
            $lease.uart_port -ine $Port -or $lease.uart_pnp_device_id -ine $ExpectedPnpDeviceId -or
            @($lease.mutexes).Count -ne 2 -or ($lease.mutexes -join '|') -cne ($names -join '|')) {
            throw 'Hardware lease identity mismatch'
        }
        $probe = $null
        $held = $false
        try {
            $probe = [IO.File]::Open((Join-Path $PhysicalLockDir 'owner.json'), [IO.FileMode]::Open,
                [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
        } catch {
            $cause = $_.Exception
            while ($cause.InnerException) { $cause = $cause.InnerException }
            if ($cause -is [IO.IOException] -and ($cause.HResult -band 65535) -eq 32) { $held = $true }
            else { throw }
        } finally { if ($probe) { $probe.Dispose() } }
        if (-not $held) { throw 'Hardware lease file is not held open by its owner' }
        # In a child process, both session-local mutexes must still be unavailable.
        if ($OwnerPid -ne $PID) {
            foreach ($name in $names) {
                $mutex = [Threading.Mutex]::OpenExisting($name)
                $acquired = $false
                try {
                    try { $acquired = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $acquired = $true }
                    if ($acquired) { throw 'Parent UART mutex is no longer owned' }
                } finally {
                    if ($acquired) { $mutex.ReleaseMutex() }
                    $mutex.Dispose()
                }
            }
        }
        if ($ownerProcess.HasExited) { throw 'Hardware lease owner exited during verification' }
        return [pscustomobject]@{PhysicalLockDir=$PhysicalLockDir;OwnerPid=$OwnerPid;OwnerStartTicks=$OwnerStartTicks;
            LeaseToken=$LeaseToken;Port=$Port;PnpDeviceId=$ExpectedPnpDeviceId}
    } finally { $ownerProcess.Dispose() }
}

function Remove-F319OwnedLock {
    param([Parameter(Mandatory = $true)][string]$PhysicalLockDir, [switch]$PreserveOwnerFile)
    # This directory was created by this invocation. Never recursively delete it.
    $path = [IO.Path]::GetFullPath($PhysicalLockDir)
    $entry = Get-Item -LiteralPath $path -ErrorAction Stop
    if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing reparse-point lock cleanup' }
    if (-not $PreserveOwnerFile) { [IO.File]::Delete((Join-Path $path 'owner.json')) }
    [IO.Directory]::Delete($path, $false)
}

function Get-F319SerialDevice {
    param(
        [Parameter(Mandatory = $true)][string]$Port,
        [Parameter(Mandatory = $true)][string]$ExpectedPnpDeviceId
    )

    $devices = @(
        Get-CimInstance Win32_SerialPort -ErrorAction SilentlyContinue |
            Select-Object DeviceID, PNPDeviceID, Name
    )
    $known = @($devices | ForEach-Object { $_.PNPDeviceID.ToUpperInvariant() })
    foreach ($item in @(Get-PnpDevice -Class Ports -PresentOnly -ErrorAction SilentlyContinue)) {
        if ($item.InstanceId -and $item.InstanceId.ToUpperInvariant() -notin $known -and
            $item.FriendlyName -match '\((COM[0-9]{1,3})\)') {
            $devices += [pscustomobject]@{
                DeviceID = $Matches[1]
                PNPDeviceID = [string]$item.InstanceId
                Name = [string]$item.FriendlyName
            }
        }
    }
    $device = @($devices | Where-Object { $_.DeviceID -ieq $Port }) | Select-Object -First 1
    if (-not $device) { throw "UART port $Port is not present" }
    if ([string]$device.PNPDeviceID -ine $ExpectedPnpDeviceId) {
        throw "UART port $Port belongs to a different PnP device"
    }
    return $device
}

function Enter-F319HardwareGuard {
    param(
        [Parameter(Mandatory = $true)][string]$Port,
        [Parameter(Mandatory = $true)][string]$ExpectedPnpDeviceId,
        [Parameter(Mandatory = $true)][string]$PhysicalLockDir,
        [Parameter(Mandatory = $true)][string]$Owner,
        [Parameter(Mandatory = $true)][string]$EvidenceDir
    )

    $device = Get-F319SerialDevice -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId
    $mutexNames = @(Get-F319MutexNames -ExpectedPnpDeviceId $ExpectedPnpDeviceId)
    $mutexes = @()
    $ownedMutexes = @()
    $ownsPhysicalLock = $false
    $leaseStream = $null
    $leaseToken = [Guid]::NewGuid().ToString('N')
    $ownerStartTicks = (Get-Process -Id $PID).StartTime.ToUniversalTime().Ticks
    try {
        foreach ($mutexName in $mutexNames) {
            $mutex = [Threading.Mutex]::new($false, $mutexName)
            $mutexes += $mutex
            $ownsMutex = $false
            try {
                $ownsMutex = $mutex.WaitOne(0)
            } catch [Threading.AbandonedMutexException] {
                $ownsMutex = $true
            }
            if (-not $ownsMutex) { throw "UART ownership conflict for $ExpectedPnpDeviceId ($mutexName)" }
            $ownedMutexes += $mutex
        }

        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $PhysicalLockDir) | Out-Null
        try {
            New-Item -ItemType Directory -Path $PhysicalLockDir -ErrorAction Stop | Out-Null
        } catch {
            throw "Physical hardware lock is already held: $PhysicalLockDir"
        }
        $ownsPhysicalLock = $true
        $metadata = [ordered]@{
            schema = 'openmitrastar.physical-lock/v3'
            owner = $Owner
            pid = $PID
            process_start_ticks = $ownerStartTicks
            lease_token = $leaseToken
            started_at = [DateTime]::UtcNow.ToString('o')
            evidence_dir = $EvidenceDir
            uart_port = [string]$device.DeviceID
            uart_pnp_device_id = [string]$device.PNPDeviceID
            mutexes = $mutexNames
        }
        $leaseStream = [IO.File]::Open((Join-Path $PhysicalLockDir 'owner.json'), [IO.FileMode]::CreateNew,
            [IO.FileAccess]::ReadWrite, [IO.FileShare]::Read)
        $payload = [Text.Encoding]::UTF8.GetBytes(($metadata | ConvertTo-Json) + "`n")
        $leaseStream.Write($payload, 0, $payload.Length)
        $leaseStream.Flush($true)

        return [pscustomobject]@{
            Mutexes = $mutexes
            OwnedMutexes = $ownedMutexes
            PhysicalLockDir = $PhysicalLockDir
            OwnsPhysicalLock = $ownsPhysicalLock
            Port = [string]$device.DeviceID
            PnpDeviceId = [string]$device.PNPDeviceID
            LeaseStream = $leaseStream
            LeaseToken = $leaseToken
            OwnerPid = $PID
            OwnerStartTicks = $ownerStartTicks
        }
    } catch {
        if ($leaseStream) { $leaseStream.Dispose() }
        if ($ownsPhysicalLock -and (Test-Path -LiteralPath $PhysicalLockDir)) {
            try { Remove-F319OwnedLock -PhysicalLockDir $PhysicalLockDir -PreserveOwnerFile:($null -eq $leaseStream) } catch { Write-Warning 'Lock cleanup incomplete; left in place' }
        }
        foreach ($ownedMutex in $ownedMutexes) { try { $ownedMutex.ReleaseMutex() } catch {} }
        foreach ($createdMutex in $mutexes) { $createdMutex.Dispose() }
        throw
    }
}

function Exit-F319HardwareGuard {
    param([object]$Guard)
    if (-not $Guard) { return }
    try {
        if ($Guard.OwnsPhysicalLock -and (Test-Path -LiteralPath $Guard.PhysicalLockDir)) {
            $lease = Read-F319Lease -PhysicalLockDir $Guard.PhysicalLockDir
            if ($lease.lease_token -cne $Guard.LeaseToken -or $lease.pid -ne $PID) { throw 'Cannot clean a different hardware lease' }
            $Guard.LeaseStream.Dispose()
            Remove-F319OwnedLock -PhysicalLockDir $Guard.PhysicalLockDir
        }
    } finally {
        if ($Guard.LeaseStream) { $Guard.LeaseStream.Dispose() }
        foreach ($ownedMutex in @($Guard.OwnedMutexes)) { try { $ownedMutex.ReleaseMutex() } catch {} }
        foreach ($createdMutex in @($Guard.Mutexes)) { if ($createdMutex) { $createdMutex.Dispose() } }
    }
}

function Assert-F319UartBinding {
    param(
        [Parameter(Mandatory = $true)][string]$Port,
        [Parameter(Mandatory = $true)][string]$ExpectedPnpDeviceId,
        [Parameter(Mandatory = $true)][string]$RouterHost,
        [Parameter(Mandatory = $true)][string]$KnownHosts,
        [Parameter(Mandatory = $true)][string]$ExpectedVersion,
        [Parameter(Mandatory = $true)][object]$HardwareLease,
        [ValidateRange(3, 30)][int]$TimeoutSeconds = 10
    )

    [void](Assert-F319HardwareLease -PhysicalLockDir $HardwareLease.PhysicalLockDir -OwnerPid $HardwareLease.OwnerPid -OwnerStartTicks $HardwareLease.OwnerStartTicks -LeaseToken $HardwareLease.LeaseToken -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId)
    [void](Get-F319SerialDevice -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId)
    if (-not (Test-Path -LiteralPath $KnownHosts -PathType Leaf)) {
        throw "Pinned SSH known_hosts is missing: $KnownHosts"
    }

    $serial = [IO.Ports.SerialPort]::new($Port, 115200, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
    $serial.Handshake = [IO.Ports.Handshake]::None
    $serial.DtrEnable = $false
    $serial.RtsEnable = $false
    $serial.ReadTimeout = 100
    $serial.WriteTimeout = 200
    $nonce = 'OMF319_UART_BIND_' + [Guid]::NewGuid().ToString('N').ToUpperInvariant()
    $received = ''
    try {
        $serial.Open()
        $serial.DiscardInBuffer()
        $ssh = Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
        $sshBase = @(
            '-i', "$env:USERPROFILE\.ssh\id_ed25519",
            '-o', 'IdentitiesOnly=yes',
            '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=8',
            '-o', 'StrictHostKeyChecking=yes',
            '-o', "UserKnownHostsFile=$KnownHosts",
            '-o', 'LogLevel=ERROR',
            "root@$RouterHost"
        )
        $remote = "grep -qx 'OPENMITRASTAR_PRODUCT_VERSION=$ExpectedVersion' /etc/openmitrastar/release && printf '%s\n' '$nonce' >/dev/console && echo OMF319_UART_BINDING_SENT"
        $result = Invoke-F319SshScript -SshPath $ssh -Arguments ($sshBase + @('sh', '-s')) -Script $remote -TimeoutSeconds 15
        $sshOutput = @($result.Stdout -split '\r?\n')
        if ($result.ExitCode -ne 0 -or $sshOutput -notcontains 'OMF319_UART_BINDING_SENT') {
            throw 'HGW SSH identity or console nonce emission failed'
        }

        $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
        while ([DateTime]::UtcNow -lt $deadline -and $received -notmatch [regex]::Escape($nonce)) {
            $chunk = $serial.ReadExisting()
            if ($chunk) {
                $received += $chunk
                if ($received.Length -gt 32768) { $received = $received.Substring($received.Length - 32768) }
            }
            Start-Sleep -Milliseconds 20
        }
        if ($received -notmatch [regex]::Escape($nonce)) {
            throw 'UART is not physically bound to the authenticated HGW console'
        }
        return [pscustomobject]@{
            Port = $Port
            PnpDeviceId = $ExpectedPnpDeviceId
            RouterHost = $RouterHost
            ExpectedVersion = $ExpectedVersion
            NonceObserved = $true
        }
    } finally {
        if ($serial.IsOpen) { $serial.Close() }
        $serial.Dispose()
    }
}

function Assert-F319UartCaptureStatus {
    param(
        [Parameter(Mandatory = $true)][object]$Status,
        [Parameter(Mandatory = $true)][string]$ExpectedRunId,
        [Parameter(Mandatory = $true)][string]$ExpectedPnpDeviceId,
        [Parameter(Mandatory = $true)][int]$CapturePid,
        [switch]$Complete
    )
    if ($Status.schema -ne 'openmitrastar.uart-capture-status/v1' -or
        $Status.run_id -cne $ExpectedRunId -or $Status.capture_pid -ne $CapturePid -or
        $Status.pinned_pnp_device_id -ine $ExpectedPnpDeviceId -or
        $Status.ready -isnot [bool] -or $Status.ready -ne $true -or
        $Status.rx_only -isnot [bool] -or $Status.rx_only -ne $true -or
        $Status.dtr -ne $false -or $Status.rts -ne $false -or
        $Status.gaps -ne 0 -or $Status.error) {
        throw 'UART capture identity, ownership or continuity is invalid'
    }
    $states = if ($Complete) { @('complete') } else { @('ready', 'capturing') }
    if ($Status.state -notin $states) { throw 'UART capture is not in the required state' }
    return $Status
}

function Assert-F319UartCaptureComplete {
    param(
        [Parameter(Mandatory = $true)][string]$StatusPath,
        [Parameter(Mandatory = $true)][string]$RawPath,
        [Parameter(Mandatory = $true)][string]$TextPath,
        [Parameter(Mandatory = $true)][string]$ExpectedRunId,
        [Parameter(Mandatory = $true)][string]$ExpectedPnpDeviceId,
        [Parameter(Mandatory = $true)][int]$CapturePid,
        [Parameter(Mandatory = $true)][object]$CaptureExitCode
    )
    if ($CaptureExitCode -isnot [int] -or $CaptureExitCode -ne 0) { throw 'UART capture process failed or exit status is unknown' }
    foreach ($path in @($StatusPath, $RawPath, $TextPath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'UART capture evidence is missing' }
    }
    $status = Get-Content -LiteralPath $StatusPath -Raw | ConvertFrom-Json
    [void](Assert-F319UartCaptureStatus -Status $status -ExpectedRunId $ExpectedRunId -ExpectedPnpDeviceId $ExpectedPnpDeviceId -CapturePid $CapturePid -Complete)
    $raw = [IO.File]::ReadAllBytes($RawPath)
    $text = [IO.File]::ReadAllText($TextPath)
    if ($raw.Length -le 0 -or $status.bytes -ne $raw.Length -or [Text.Encoding]::ASCII.GetString($raw) -cne $text) {
        throw 'UART byte count or text/raw correlation failed'
    }
    $begin = [regex]::Matches($text, ('(?m)^' + [regex]::Escape($ExpectedRunId) + '_BEGIN\r?$'))
    $end = [regex]::Matches($text, ('(?m)^' + [regex]::Escape($ExpectedRunId) + '_END\r?$'))
    if ($begin.Count -ne 1 -or $end.Count -ne 1 -or $begin[0].Index -ge $end[0].Index) {
        throw 'UART capture does not bracket the exact F319 probe'
    }
    return $status
}

function Wait-F319UartCaptureReady {
    param(
        [Parameter(Mandatory = $true)][string]$StatusPath,
        [Parameter(Mandatory = $true)][Diagnostics.Process]$Process,
        [Parameter(Mandatory = $true)][string]$ExpectedRunId,
        [Parameter(Mandatory = $true)][string]$ExpectedPnpDeviceId,
        [ValidateRange(2, 30)][int]$TimeoutSeconds = 10
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process.HasExited) { throw "UART capture exited before becoming ready (rc=$($Process.ExitCode))" }
        if (Test-Path -LiteralPath $StatusPath) {
            try {
                $status = Get-Content -LiteralPath $StatusPath -Raw | ConvertFrom-Json
                if ($status.ready -eq $true) {
                    return (Assert-F319UartCaptureStatus -Status $status -ExpectedRunId $ExpectedRunId -ExpectedPnpDeviceId $ExpectedPnpDeviceId -CapturePid $Process.Id)
                }
                if ($status.state -eq 'error') { throw "UART capture failed: $($status.error)" }
            } catch [System.Management.Automation.RuntimeException] {
                throw
            } catch {
            }
        }
        Start-Sleep -Milliseconds 100
    }
    throw 'UART capture did not become ready before the runtime action'
}
