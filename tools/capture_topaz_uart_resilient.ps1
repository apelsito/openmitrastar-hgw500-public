[CmdletBinding()]
param(
    [string]$Port = 'COM3',
    [int]$Baud = 115200,
    [ValidateRange(30, 3600)]
    [int]$Seconds = 1200,
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,
    [string]$RunId = '',
    [string]$ExpectedPnpDeviceId = '',
    [switch]$ExternalOwnershipHeld,
    [string]$ExternalGuardLockDir = '',
    [int]$ExternalGuardOwnerPid = 0,
    [long]$ExternalGuardOwnerStartTicks = 0,
    [string]$ExternalGuardToken = ''
)

$ErrorActionPreference = 'Stop'
if ($Port -notmatch '^COM[0-9]{1,3}$') { throw 'Port must be a COM port such as COM3' }
if (-not $RunId) { $RunId = 'uart-' + (Get-Date -Format 'yyyyMMdd-HHmmss') }
if ($RunId -notmatch '^[A-Za-z0-9._-]{1,80}$') { throw 'RunId contains unsafe characters' }
if ($ExternalOwnershipHeld) {
    . (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
    $externalLease = @{PhysicalLockDir=$ExternalGuardLockDir;OwnerPid=$ExternalGuardOwnerPid;
        OwnerStartTicks=$ExternalGuardOwnerStartTicks;LeaseToken=$ExternalGuardToken;Port=$Port;ExpectedPnpDeviceId=$ExpectedPnpDeviceId}
    [void](Assert-F319HardwareLease @externalLease)
}

$output = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $output | Out-Null
$rawPath = Join-Path $output 'uart.raw.bin'
$textPath = Join-Path $output 'uart.log'
$eventsPath = Join-Path $output 'uart-events.jsonl'
$statusPath = Join-Path $output 'capture-status.json'
$started = [DateTimeOffset]::UtcNow
$bytes = [int64]0
$gaps = 0
$state = 'starting'
$currentPort = $null
$lastError = $null
$serial = $null
$mutexes = @()
$ownedMutexes = @()

function Get-SerialDevices {
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
    @($devices)
}

function Find-ByPort([string]$Name) {
    @(Get-SerialDevices | Where-Object { $_.DeviceID -ieq $Name }) | Select-Object -First 1
}

function Find-ByPnp([string]$Identity) {
    @(Get-SerialDevices | Where-Object { $_.PNPDeviceID -ieq $Identity }) | Select-Object -First 1
}

$initial = Find-ByPort $Port
if (-not $ExpectedPnpDeviceId) {
    if (-not $initial) { throw "Serial device $Port is not present" }
    $ExpectedPnpDeviceId = [string]$initial.PNPDeviceID
} elseif ($initial -and $initial.PNPDeviceID -ine $ExpectedPnpDeviceId) {
    throw "Port $Port belongs to a different PnP device"
}

if (-not $ExternalOwnershipHeld) {
    $identity = $ExpectedPnpDeviceId.ToUpperInvariant() -replace '[^A-Za-z0-9_.-]', '_'
    $mutexNames = @(('Local\OpenMitraStar-UART-' + $identity), ('Local\OpenRouterLab-UART-' + $identity))
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
}

function Write-Status([string]$NewState, [string]$ErrorText = '') {
    $script:state = $NewState
    if ($ErrorText) { $script:lastError = $ErrorText }
    $payload = [ordered]@{
        schema = 'openmitrastar.uart-capture-status/v1'
        run_id = $RunId
        capture_pid = $PID
        state = $script:state
        ready = ($script:state -in @('ready', 'capturing', 'reconnected', 'complete'))
        current_port = $script:currentPort
        pinned_pnp_device_id = $ExpectedPnpDeviceId
        baud = $Baud
        rx_only = $true
        dtr = $false
        rts = $false
        bytes = $script:bytes
        gaps = $script:gaps
        started_utc = $started.ToString('o')
        updated_utc = [DateTimeOffset]::UtcNow.ToString('o')
        error = $script:lastError
    }
    $json = $payload | ConvertTo-Json -Depth 4
    $temporary = $statusPath + '.tmp'
    [IO.File]::WriteAllText($temporary, $json + "`n", [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $statusPath -Force
}

function Write-Event([string]$Stage, [hashtable]$Fields = @{}) {
    $event = [ordered]@{
        schema = 'openmitrastar.uart-capture-event/v1'
        timestamp_utc = [DateTimeOffset]::UtcNow.ToString('o')
        run_id = $RunId
        stage = $Stage
        port = $script:currentPort
        pnp_device_id = $ExpectedPnpDeviceId
        bytes = $script:bytes
        gaps = $script:gaps
    }
    foreach ($key in $Fields.Keys) { $event[$key] = $Fields[$key] }
    [IO.File]::AppendAllText(
        $eventsPath,
        (($event | ConvertTo-Json -Depth 5 -Compress) + "`n"),
        [Text.UTF8Encoding]::new($false))
    Write-Host "OMUARTCAP stage=$Stage run_id=$RunId port=$($script:currentPort) bytes=$($script:bytes) gaps=$($script:gaps)"
}

function Close-Serial {
    if ($script:serial) {
        try { if ($script:serial.IsOpen) { $script:serial.Close() } } catch {}
        try { $script:serial.Dispose() } catch {}
        $script:serial = $null
    }
    $script:currentPort = $null
}

function Open-PinnedSerial {
    if ($ExternalOwnershipHeld) { [void](Assert-F319HardwareLease @externalLease) }
    $device = Find-ByPnp $ExpectedPnpDeviceId
    if (-not $device) { return $false }
    $candidate = [string]$device.DeviceID
    $instance = [IO.Ports.SerialPort]::new(
        $candidate, $Baud, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
    $instance.Handshake = [IO.Ports.Handshake]::None
    $instance.DtrEnable = $false
    $instance.RtsEnable = $false
    $instance.ReadTimeout = 200
    $instance.WriteTimeout = 200
    try {
        $instance.Open()
    } catch [UnauthorizedAccessException] {
        $instance.Dispose()
        throw "UART ownership conflict: $candidate is present but cannot be opened"
    }
    $script:serial = $instance
    $script:currentPort = $candidate
    return $true
}

$raw = [IO.File]::Open($rawPath, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite)
$text = [IO.StreamWriter]::new(
    [IO.File]::Open($textPath, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite),
    [Text.UTF8Encoding]::new($false))
$text.AutoFlush = $true
$buffer = [byte[]]::new(4096)
$deadline = [DateTimeOffset]::UtcNow.AddSeconds($Seconds)
$lastHeartbeat = [DateTimeOffset]::MinValue
$hadConnection = $false

try {
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        if (-not $serial -or -not $serial.IsOpen) {
            try {
                if (Open-PinnedSerial) {
                    $stage = if ($hadConnection) { 'reconnected' } else { 'ready' }
                    $hadConnection = $true
                    Write-Event $stage
                    Write-Status $stage
                } else {
                    if ($state -ne 'port-lost') {
                        $gaps++
                        Write-Event 'port-lost'
                        Write-Status 'port-lost'
                    }
                    Start-Sleep -Milliseconds 200
                    continue
                }
            } catch {
                Write-Event 'conflict' @{ error = $_.Exception.Message }
                Write-Status 'error' $_.Exception.Message
                throw
            }
        }

        try {
            $count = $serial.Read($buffer, 0, $buffer.Length)
            if ($count -gt 0) {
                $raw.Write($buffer, 0, $count)
                $raw.Flush()
                $chunk = [Text.Encoding]::ASCII.GetString($buffer, 0, $count)
                $text.Write($chunk)
                $bytes += $count
                if ($state -ne 'capturing') { Write-Status 'capturing' }
            }
        } catch [TimeoutException] {
        } catch [IO.IOException], [InvalidOperationException] {
            Close-Serial
            $gaps++
            Write-Event 'port-lost' @{ error = $_.Exception.Message }
            Write-Status 'port-lost' $_.Exception.Message
        }

        if (([DateTimeOffset]::UtcNow - $lastHeartbeat).TotalSeconds -ge 1) {
            if ($ExternalOwnershipHeld) { [void](Assert-F319HardwareLease @externalLease) }
            Write-Status $(if ($serial -and $serial.IsOpen) { 'capturing' } else { 'port-lost' })
            $lastHeartbeat = [DateTimeOffset]::UtcNow
        }
    }
    if ($ExternalOwnershipHeld) { [void](Assert-F319HardwareLease @externalLease) }
    Write-Event 'complete'
    Write-Status 'complete'
} catch {
    if ($state -ne 'error') { Write-Status 'error' $_.Exception.Message }
    throw
} finally {
    Close-Serial
    $text.Dispose()
    $raw.Dispose()
    foreach ($ownedMutex in $ownedMutexes) { try { $ownedMutex.ReleaseMutex() } catch {} }
    foreach ($createdMutex in $mutexes) { if ($createdMutex) { $createdMutex.Dispose() } }
}
