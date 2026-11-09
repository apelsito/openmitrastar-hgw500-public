[CmdletBinding()]
param(
    [string]$Port = 'COM3',
    [string]$ExpectedPnpDeviceId = 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000',
    [ValidateRange(180, 900)]
    [int]$TimeoutSeconds = 300,
    [Parameter(Mandatory = $true)]
    [string]$StateDirectory
)

$ErrorActionPreference = 'Stop'
$stateRoot = [IO.Path]::GetFullPath($StateDirectory)
New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null
$readyPath = Join-Path $stateRoot 'uart-guard-ready.json'
$resultPath = Join-Path $stateRoot 'uart-guard-result.json'
$triggerPath = Join-Path $stateRoot 'uart-guard-trigger'
$stopPath = Join-Path $stateRoot 'uart-guard-stop'
$logPath = Join-Path $stateRoot 'uart-guard.log'
$serial = $null
$mutex = $null
$ownsMutex = $false
$transcript = [Text.StringBuilder]::new()

function Write-AtomicJson([string]$Path, [object]$Payload) {
    $temporary = $Path + '.tmp'
    [IO.File]::WriteAllText(
        $temporary,
        (($Payload | ConvertTo-Json -Depth 6) + "`n"),
        [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

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
    return @($devices)
}

function Get-PinnedPort {
    $ports = @(Get-SerialDevices | Where-Object { $_.PNPDeviceID -ieq $ExpectedPnpDeviceId })
    if ($ports.Count -ne 1) { throw 'Pinned UART device is not uniquely present' }
    if ([string]$ports[0].DeviceID -ine $Port) { throw 'Pinned UART device is present on an unexpected COM port' }
    return [string]$ports[0].DeviceID
}

function Read-Until([string[]]$Patterns, [int]$Seconds) {
    $window = [Text.StringBuilder]::new()
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $chunk = $serial.ReadExisting()
        if ($chunk) {
            [void]$transcript.Append($chunk)
            [void]$window.Append($chunk)
            $text = $window.ToString()
            foreach ($pattern in $Patterns) {
                if ($text -match $pattern) { return $pattern }
            }
            if ($window.Length -gt 32768) {
                [void]$window.Remove(0, $window.Length - 16384)
            }
        }
        Start-Sleep -Milliseconds 40
    }
    throw "UART timeout waiting for: $($Patterns -join ', ')"
}

function Send-MagicSysRq([char]$Command) {
    $serial.BreakState = $true
    Start-Sleep -Milliseconds 600
    $serial.BreakState = $false
    Start-Sleep -Milliseconds 150
    $serial.Write([string]$Command)
}

try {
    if ($Port -notmatch '^COM[0-9]{1,3}$') { throw 'Port must be a COM port' }
    $resolvedPort = Get-PinnedPort
    $mutexName = 'Local\OpenMitraStar-UART-' + ($ExpectedPnpDeviceId -replace '[^A-Za-z0-9_.-]', '_')
    $mutex = [Threading.Mutex]::new($false, $mutexName)
    $ownsMutex = $mutex.WaitOne(0)
    if (-not $ownsMutex) { throw 'UART ownership conflict' }

    $serial = [IO.Ports.SerialPort]::new($resolvedPort, 115200, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
    $serial.Handshake = [IO.Ports.Handshake]::None
    $serial.ReadTimeout = 150
    $serial.WriteTimeout = 500
    $serial.DtrEnable = $false
    $serial.RtsEnable = $false
    $serial.Open()

    # SysRq help changes no network or storage state and proves host TX plus router RX/TX.
    Send-MagicSysRq 'h'
    [void](Read-Until @('SysRq.*HELP', 'SysRq.*help', 'HELP.*reboot\(b\)') 15)
    Write-AtomicJson $readyPath ([ordered]@{
        schema = 'openmitrastar.f301-vlan-uart-guard/v2'
        ready = $true
        pid = $PID
        port = $resolvedPort
        pinned_pnp_device_id = $ExpectedPnpDeviceId
        dtr = $false
        rts = $false
        sysrq_help_verified = $true
        recovery_action = 'magic-sysrq-reboot-clears-ram-only-vlan-state'
        deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds).ToString('o')
    })

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $reason = ''
    while ([DateTime]::UtcNow -lt $deadline) {
        $chunk = $serial.ReadExisting()
        if ($chunk) { [void]$transcript.Append($chunk) }
        if (Test-Path -LiteralPath $triggerPath) { $reason = 'trigger'; break }
        if (Test-Path -LiteralPath $stopPath) { $reason = 'disarmed'; break }
        Start-Sleep -Milliseconds 100
    }
    if (-not $reason) { $reason = 'timeout' }
    if ($reason -eq 'disarmed') {
        Write-AtomicJson $resultPath ([ordered]@{
            schema = 'openmitrastar.f301-vlan-uart-guard/v2'
            status = 'DISARMED'
            recovery_reboot_sent = $false
        })
        exit 0
    }

    Send-MagicSysRq 'b'
    [void](Read-Until @('Boot reached stage 13', 'Quantenna U-Boot') 45)
    Write-AtomicJson $resultPath ([ordered]@{
        schema = 'openmitrastar.f301-vlan-uart-guard/v2'
        status = 'RECOVERY_REBOOT_CONFIRMED'
        reason = $reason
        recovery_reboot_sent = $true
    })
    exit 0
} catch {
    Write-AtomicJson $resultPath ([ordered]@{
        schema = 'openmitrastar.f301-vlan-uart-guard/v2'
        status = 'FAILED'
        recovery_reboot_sent = $false
        error = $_.Exception.Message
    })
    exit 1
} finally {
    [IO.File]::WriteAllText($logPath, $transcript.ToString(), [Text.UTF8Encoding]::new($false))
    if ($serial) {
        try { if ($serial.IsOpen) { $serial.Close() } } catch {}
        try { $serial.Dispose() } catch {}
    }
    if ($ownsMutex) { try { $mutex.ReleaseMutex() } catch {} }
    if ($mutex) { $mutex.Dispose() }
}
