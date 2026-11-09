[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [ValidateRange(1, 300)]
    [int]$RxProbeSeconds = 5,
    [ValidateRange(5, 21600)]
    [int]$WaitSeconds = 3600,
    [ValidateRange(1, 120)]
    [int]$PollSeconds = 10,
    [string]$CurrentLiveCrc32 = "26523198",
    [switch]$ExecuteFlash,
    [string]$Ack = "",
    [switch]$StopStaleFlashWatchers,
    [switch]$NoFirstByteSpace,
    [switch]$AllowBlindAutobreak,
    [ValidateRange(100, 5000)]
    [int]$BlindSpaceIntervalMilliseconds = 250,
    [switch]$LegacyProbeLoop,
    [switch]$Once,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$RequiredAck = "OPENMITRASTAR_AELITA_RECOVER_UART_FLASH_F66_RECLAIM_021CD489"
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\aelita-recover-uart-f66-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$statusPath = Join-Path $OutputDir "status.json"
$logPath = Join-Path $OutputDir "recover.log"

function Write-JsonStatus([string]$State, [string]$Message, [object]$Probe = $null, [string]$F66Run = "") {
    [ordered]@{
        schema = "openmitrastar.aelita-recover-uart-f66/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        execute_flash = [bool]$ExecuteFlash
        port = $Port
        server_ip = $ServerIp
        client_ip = $ClientIp
        host = $HostAddress
        rx_probe_seconds = $RxProbeSeconds
        wait_seconds = $WaitSeconds
        poll_seconds = $PollSeconds
        current_live_crc32 = $CurrentLiveCrc32
        required_ack = $RequiredAck
        first_byte_space_enabled = [bool]($ExecuteFlash -and -not $NoFirstByteSpace)
        blind_autobreak_enabled = [bool]$AllowBlindAutobreak
        blind_space_interval_ms = $BlindSpaceIntervalMilliseconds
        probe = $Probe
        f66_run = $F66Run
    } | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $statusPath
}

function Get-StaleFlashWatchers {
    @(Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $cmd = [string]$_.CommandLine
            $cmd -like "*MitraStar*" -and (
                $cmd -like "*watch_flash_f65_isolated_5g_until_bootbase.ps1*" -or
                $cmd -like "*flash_f65_isolated_5g.ps1*" -or
                $cmd -like "*q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1*" -or
                $cmd -like "*monitor_f65_flash_then_gate.ps1*" -or
                $cmd -like "*monitor_f65_mgmt_then_gate.ps1*"
            )
        })
}

function Stop-StaleFlashWatchers {
    $stale = @(Get-StaleFlashWatchers)
    foreach ($proc in $stale) {
        Stop-Process -Id ([int]$proc.ProcessId) -Force -ErrorAction Stop
        "STOPPED_STALE pid=$($proc.ProcessId) cmd=$($proc.CommandLine)" |
            Add-Content -Encoding ascii -LiteralPath $logPath
    }
    return $stale.Count
}

function Invoke-RxProbe([int]$Attempt) {
    $probeDir = Join-Path $OutputDir ("rx-probe-{0:000}" -f $Attempt)
    New-Item -ItemType Directory -Force -Path $probeDir | Out-Null
    $rawPath = Join-Path $probeDir "uart.raw.bin"
    $textPath = Join-Path $probeDir "uart.log"
    $statusFile = Join-Path $probeDir "capture-status.json"
    $bytes = [int64]0
    $errorText = ""
    $serial = $null
    $raw = $null
    $text = $null
    $buffer = [byte[]]::new(4096)
    $deadline = [DateTime]::UtcNow.AddSeconds($RxProbeSeconds)
    try {
        $serial = [IO.Ports.SerialPort]::new(
            $Port, 115200, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
        $serial.Handshake = [IO.Ports.Handshake]::None
        $serial.DtrEnable = $false
        $serial.RtsEnable = $false
        $serial.ReadTimeout = 100
        $serial.WriteTimeout = 200
        $serial.Open()
        $raw = [IO.File]::Open($rawPath, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite)
        $text = [IO.StreamWriter]::new(
            [IO.File]::Open($textPath, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite),
            [Text.UTF8Encoding]::new($false))
        $text.AutoFlush = $true
        while ([DateTime]::UtcNow -lt $deadline) {
            try {
                $count = $serial.Read($buffer, 0, $buffer.Length)
                if ($count -gt 0) {
                    $raw.Write($buffer, 0, $count)
                    $raw.Flush()
                    $text.Write([Text.Encoding]::ASCII.GetString($buffer, 0, $count))
                    $bytes += $count
                    break
                }
            } catch [TimeoutException] {
            }
        }
    } catch {
        $errorText = $_.Exception.Message
    } finally {
        if ($serial -and $serial.IsOpen) { $serial.Close() }
        if ($serial) { $serial.Dispose() }
        if ($text) { $text.Dispose() }
        if ($raw) { $raw.Dispose() }
    }
    $status = [ordered]@{
        schema = "openmitrastar.quick-uart-rx-probe/v1"
        run_id = ("aelita-f66-rx-probe-{0:000}" -f $Attempt)
        state = if ($errorText) { "error" } elseif ($bytes -gt 0) { "rx_seen" } else { "silent" }
        current_port = $Port
        baud = 115200
        rx_only = $true
        dtr = $false
        rts = $false
        bytes = $bytes
        updated_utc = [DateTimeOffset]::UtcNow.ToString("o")
        error = $errorText
    }
    $status | ConvertTo-Json -Depth 5 | Set-Content -Encoding ascii -LiteralPath $statusFile
    [ordered]@{
        attempt = $Attempt
        rc = if ($errorText) { 1 } else { 0 }
        output = ""
        dir = $probeDir
        status = [pscustomobject]$status
        bytes = $bytes
        error = $errorText
    }
}

function Start-F66Watcher {
    if (-not $ExecuteFlash) {
        return "dry-run"
    }
    if ($Ack -ne $RequiredAck) {
        throw "ExecuteFlash requires exact Ack: $RequiredAck"
    }
    $preflightScript = Join-Path $PSScriptRoot "verify_f66_offline_preflight.py"
    if (-not (Test-Path -LiteralPath $preflightScript -PathType Leaf)) {
        throw "Missing F66 offline preflight verifier: $preflightScript"
    }
    $preflightOut = Join-Path $OutputDir "f66-offline-preflight-before-watch.json"
    & python $preflightScript --current-live-crc32 $CurrentLiveCrc32 --output $preflightOut |
        Add-Content -Encoding ascii -LiteralPath $logPath
    if ($LASTEXITCODE -ne 0) {
        throw "F66 offline preflight failed before watcher start"
    }
    $existing = @(Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { [string]$_.CommandLine -like "*watch_flash_f66_2g_qguard_until_bootbase.ps1*" })
    if ($existing.Count -gt 0) {
        throw "F66 watcher already running"
    }
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "watch_flash_f66_2g_qguard_until_bootbase.ps1"),
        "-Port", $Port,
        "-ServerIp", $ServerIp,
        "-ClientIp", $ClientIp,
        "-HostAddress", $HostAddress,
        "-CurrentLiveCrc32", $CurrentLiveCrc32.ToLowerInvariant(),
        "-PulseResetLinesFirst",
        "-ConsoleRebootAssist",
        "-SysRqRebootFirst"
    )
    if ($AllowBlindAutobreak) {
        $args += "-AllowBlindAutobreak"
        $args += "-AllowNoRxRebootAssist"
    }
    $proc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList $args -PassThru
    return "pid=$($proc.Id)"
}

function Wait-UartRxContinuous {
    $probeDir = Join-Path $OutputDir "rx-continuous"
    New-Item -ItemType Directory -Force -Path $probeDir | Out-Null
    $rawPath = Join-Path $probeDir "uart.raw.bin"
    $textPath = Join-Path $probeDir "uart.log"
    $serial = $null
    $raw = $null
    $text = $null
    $bytes = [int64]0
    $errorText = ""
    $buffer = [byte[]]::new(4096)
    $started = [DateTimeOffset]::UtcNow
    $deadline = [DateTime]::UtcNow.AddSeconds($WaitSeconds)
    $lastStatusAt = [DateTime]::MinValue
    $lastBlindSpaceAt = [DateTime]::MinValue
    $firstByteSpaceSent = $false
    $blindSpaceCount = 0
    try {
        $serial = [IO.Ports.SerialPort]::new(
            $Port, 115200, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
        $serial.Handshake = [IO.Ports.Handshake]::None
        $serial.DtrEnable = $false
        $serial.RtsEnable = $false
        $serial.ReadTimeout = 100
        $serial.WriteTimeout = 200
        $serial.Open()
        $raw = [IO.File]::Open($rawPath, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite)
        $text = [IO.StreamWriter]::new(
            [IO.File]::Open($textPath, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite),
            [Text.UTF8Encoding]::new($false))
        $text.AutoFlush = $true

        while ([DateTime]::UtcNow -lt $deadline) {
            try {
                $count = $serial.Read($buffer, 0, $buffer.Length)
                if ($count -gt 0) {
                    $raw.Write($buffer, 0, $count)
                    $raw.Flush()
                    $text.Write([Text.Encoding]::ASCII.GetString($buffer, 0, $count))
                    $bytes += $count
                    if ($ExecuteFlash -and -not $NoFirstByteSpace) {
                        $serial.Write(" ")
                        $firstByteSpaceSent = $true
                        "RX_CONTINUOUS_FIRST_BYTE_SPACE_SENT bytes=$bytes at=$(Get-Date -Format o)" |
                            Add-Content -Encoding ascii -LiteralPath $logPath
                    }
                    break
                }
            } catch [TimeoutException] {
            }

            if ($ExecuteFlash -and $AllowBlindAutobreak -and
                ([DateTime]::UtcNow - $lastBlindSpaceAt).TotalMilliseconds -ge $BlindSpaceIntervalMilliseconds) {
                $serial.Write(" ")
                $lastBlindSpaceAt = [DateTime]::UtcNow
                $blindSpaceCount += 1
                if (($blindSpaceCount % 20) -eq 0) {
                    "RX_CONTINUOUS_BLIND_SPACE_SENT count=$blindSpaceCount at=$(Get-Date -Format o)" |
                        Add-Content -Encoding ascii -LiteralPath $logPath
                }
            }

            if (([DateTime]::UtcNow - $lastStatusAt).TotalSeconds -ge $PollSeconds) {
                $probe = [ordered]@{
                    attempt = 1
                    rc = 0
                    output = ""
                    dir = $probeDir
                    status = [ordered]@{
                        schema = "openmitrastar.continuous-uart-rx-probe/v1"
                        run_id = "aelita-f66-rx-continuous"
                        state = "silent"
                        current_port = $Port
                        baud = 115200
                        rx_only = $true
                        dtr = $false
                        rts = $false
                        bytes = $bytes
                        first_byte_space_sent = $false
                        blind_space_count = $blindSpaceCount
                        started_utc = $started.ToString("o")
                        updated_utc = [DateTimeOffset]::UtcNow.ToString("o")
                        error = ""
                    }
                    bytes = $bytes
                    error = ""
                }
                Write-JsonStatus "waiting_uart_rx" "UART RX still silent; continuous reader armed" $probe
                "RX_CONTINUOUS heartbeat bytes=$bytes at=$(Get-Date -Format o)" |
                    Add-Content -Encoding ascii -LiteralPath $logPath
                $lastStatusAt = [DateTime]::UtcNow
            }
        }
    } catch {
        $errorText = $_.Exception.Message
    } finally {
        if ($serial -and $serial.IsOpen) { $serial.Close() }
        if ($serial) { $serial.Dispose() }
        if ($text) { $text.Dispose() }
        if ($raw) { $raw.Dispose() }
    }
    [ordered]@{
        attempt = 1
        rc = if ($errorText) { 1 } else { 0 }
        output = ""
        dir = $probeDir
        status = [ordered]@{
            schema = "openmitrastar.continuous-uart-rx-probe/v1"
            run_id = "aelita-f66-rx-continuous"
            state = if ($errorText) { "error" } elseif ($bytes -gt 0) { "rx_seen" } else { "silent" }
            current_port = $Port
            baud = 115200
            rx_only = -not $firstByteSpaceSent
            dtr = $false
            rts = $false
            bytes = $bytes
            first_byte_space_sent = $firstByteSpaceSent
            blind_space_count = $blindSpaceCount
            started_utc = $started.ToString("o")
            updated_utc = [DateTimeOffset]::UtcNow.ToString("o")
            error = $errorText
        }
        bytes = $bytes
        error = $errorText
    }
}

"AELITA_RECOVER_START at=$(Get-Date -Format o) execute=$([int]$ExecuteFlash.IsPresent) out=$OutputDir" |
    Add-Content -Encoding ascii -LiteralPath $logPath

if ($ExecuteFlash -and $Ack -ne $RequiredAck) {
    Write-JsonStatus "ack_required" "exact acknowledgement missing"
    throw "ExecuteFlash requires exact Ack: $RequiredAck"
}
if ($CurrentLiveCrc32 -notmatch '^[0-9a-fA-F]{8}$') {
    Write-JsonStatus "bad_current_live_crc32" "CurrentLiveCrc32 must be 8 hex characters"
    throw "CurrentLiveCrc32 must be 8 hex characters"
}

if ($StopStaleFlashWatchers) {
    $stopped = Stop-StaleFlashWatchers
    "STALE_STOPPED count=$stopped" | Add-Content -Encoding ascii -LiteralPath $logPath
}

if (-not $LegacyProbeLoop -and -not $Once) {
    $probe = Wait-UartRxContinuous
    "RX_CONTINUOUS_DONE rc=$($probe.rc) bytes=$($probe.bytes) dir=$($probe.dir)" |
        Add-Content -Encoding ascii -LiteralPath $logPath
    if ($probe.bytes -gt 0) {
        $f66 = Start-F66Watcher
        if ($ExecuteFlash) {
            Write-JsonStatus "f66_started" "UART RX is alive; F66 watcher started" $probe $f66
        } else {
            Write-JsonStatus "would_start_f66" "UART RX is alive; rerun with ExecuteFlash and exact Ack to start F66" $probe $f66
        }
        exit 0
    }
    Write-JsonStatus "timeout_waiting_uart_rx" "No UART RX bytes observed before timeout" $probe
    exit 1
}

$deadline = (Get-Date).AddSeconds($WaitSeconds)
$attempt = 0
while ((Get-Date) -lt $deadline) {
    $attempt += 1
    $probe = Invoke-RxProbe $attempt
    "RX_PROBE attempt=$attempt rc=$($probe.rc) bytes=$($probe.bytes) dir=$($probe.dir)" |
        Add-Content -Encoding ascii -LiteralPath $logPath
    if ($probe.bytes -gt 0) {
        $f66 = Start-F66Watcher
        if ($ExecuteFlash) {
            Write-JsonStatus "f66_started" "UART RX is alive; F66 watcher started" $probe $f66
        } else {
            Write-JsonStatus "would_start_f66" "UART RX is alive; rerun with ExecuteFlash and exact Ack to start F66" $probe $f66
        }
        exit 0
    }
    Write-JsonStatus "waiting_uart_rx" "UART RX still silent; power-cycle or check router TX to adapter RX" $probe
    if ($Once) { exit 2 }
    Start-Sleep -Seconds $PollSeconds
}

Write-JsonStatus "timeout_waiting_uart_rx" "No UART RX bytes observed before timeout"
exit 1
