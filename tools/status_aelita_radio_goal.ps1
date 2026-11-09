[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RouterHost = "192.168.1.90",
    [string]$AelitaHost = "192.168.1.63",
    [string]$AelitaUser = "AELITA",
    [int]$TcpTimeoutSeconds = 3,
    [switch]$SkipAelita,
    [switch]$IncludeAelitaScan,
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutSeconds = 3) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne([TimeSpan]::FromSeconds($TimeoutSeconds))
        if (-not $ok) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Read-JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return (Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json)
}

function Get-LatestFile([string]$Directory, [string]$Filter) {
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) { return $null }
    $items = @(Get-ChildItem -LiteralPath $Directory -Filter $Filter -File -Recurse -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1)
    if ($items.Count -eq 0) { return $null }
    return $items[0]
}

function Get-LatestDir([string]$Directory, [string]$Filter) {
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) { return $null }
    $items = @(Get-ChildItem -LiteralPath $Directory -Filter $Filter -Directory -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1)
    if ($items.Count -eq 0) { return $null }
    return $items[0]
}

function Get-LatestExecutedFlashDir([string]$Directory, [string]$Filter) {
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) { return $null }
    $items = @(Get-ChildItem -LiteralPath $Directory -Filter $Filter -Directory -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending)
    foreach ($item in $items) {
        $status = Read-JsonFile (Join-Path $item.FullName "status.json")
        if ($status -and $status.PSObject.Properties.Name -contains "execute" -and [bool]$status.execute) {
            return $item
        }
    }
    if ($items.Count -eq 0) { return $null }
    return $items[0]
}

function Get-FileProbe([AllowNull()][string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return [ordered]@{
            path = $Path
            exists = $false
            bytes = $null
            last_write_time = $null
        }
    }
    $item = Get-Item -LiteralPath $Path
    return [ordered]@{
        path = $item.FullName
        exists = $true
        bytes = [int64]$item.Length
        last_write_time = $item.LastWriteTime.ToString("o")
    }
}

function Get-F93F95ChainSnapshot([string]$HostName) {
    $script = Join-Path $PSScriptRoot "status_f93_f95_chain.ps1"
    if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { return $null }
    try {
        $raw = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script -HostAddress $HostName 2>$null
        if ($LASTEXITCODE -ne 0) {
            return [ordered]@{
                error = "status_f93_f95_chain_failed"
                exit_code = [int]$LASTEXITCODE
            }
        }
        return (($raw -join "`n") | ConvertFrom-Json)
    } catch {
        return [ordered]@{
            error = "status_f93_f95_chain_exception"
            message = $_.Exception.Message
        }
    }
}

function Compress-CommandLine([AllowNull()][string]$CommandLine) {
    if ([string]::IsNullOrWhiteSpace($CommandLine)) { return $CommandLine }
    $limit = 360
    if ($CommandLine.Length -le $limit) { return $CommandLine }
    return $CommandLine.Substring(0, $limit) + "...<truncated>"
}

function Get-ProcessMatches {
    @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -in @("powershell.exe", "pwsh.exe") -and
            [string]$_.CommandLine -match 'aelita_recover_uart_then_flash_f66|monitor_f125_flash_then_assoc_only_5g|monitor_f126_flash_then_assoc_only_5g|monitor_f66_flash_then_2g_gate|monitor_router_ssh_then_radio_gate|monitor_f83_flash_then_stage_gate|monitor_f7[678]_flash_then_stage_gate|flash_f83|flash_f7[5678]|watch_flash_f7[456]|q3_f45_radio5|f65|flash_f93_2g_ht40sgi|flash_f95_2g_mcs15|monitor_f93_restore_then_f95'
        } |
        ForEach-Object {
            [ordered]@{
                source = "command_line_match"
                process_id = [int]$_.ProcessId
                alive = $true
                name = [string]$_.Name
                command_line = Compress-CommandLine ([string]$_.CommandLine)
            }
        })
}

function Get-StatusBoundProcesses([object[]]$Entries) {
    $seen = @{}
    foreach ($entry in $Entries) {
        if (-not $entry -or $null -eq $entry.pid) { continue }
        try {
            $pidInt = [int]$entry.pid
        } catch {
            continue
        }
        if ($pidInt -le 0 -or $seen.ContainsKey($pidInt)) { continue }
        $seen[$pidInt] = $true
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pidInt" -ErrorAction SilentlyContinue
        [ordered]@{
            source = [string]$entry.source
            process_id = $pidInt
            alive = [bool]$proc
            name = if ($proc) { [string]$proc.Name } else { $null }
            command_line = if ($proc) { Compress-CommandLine ([string]$proc.CommandLine) } else { $null }
        }
    }
}

function Test-ProcessAlive([AllowNull()][object]$PidValue) {
    if ($null -eq $PidValue) { return $false }
    try {
        $pidInt = [int]$PidValue
    } catch {
        return $false
    }
    return [bool](Get-Process -Id $pidInt -ErrorAction SilentlyContinue)
}

function Get-SerialTriage([AllowNull()][object]$SupervisorStatus, [bool]$RouterTcp22) {
    $ports = @()
    try {
        $ports = @([IO.Ports.SerialPort]::GetPortNames() | Sort-Object)
    } catch {
        $ports = @()
    }

    $pnpPorts = @()
    try {
        $pnpPorts = @(Get-PnpDevice -Class Ports -ErrorAction SilentlyContinue |
            Select-Object Status, FriendlyName, InstanceId)
    } catch {
        $pnpPorts = @()
    }

    $rxBytes = $null
    $blindSpaceCount = $null
    $startedUtc = $null
    $silentSeconds = $null
    $activeAutobreakSeconds = $null
    $blindEnabled = $false
    $state = "missing"
    if ($SupervisorStatus) {
        $state = [string]$SupervisorStatus.state
        if ($SupervisorStatus.PSObject.Properties.Name -contains "blind_autobreak_enabled") {
            $blindEnabled = [bool]$SupervisorStatus.blind_autobreak_enabled
        }
        if ($SupervisorStatus.PSObject.Properties.Name -contains "probe" -and $SupervisorStatus.probe) {
            if ($SupervisorStatus.probe.PSObject.Properties.Name -contains "bytes") {
                $rxBytes = [int64]$SupervisorStatus.probe.bytes
            }
            if ($SupervisorStatus.probe.PSObject.Properties.Name -contains "status" -and $SupervisorStatus.probe.status) {
                if ($SupervisorStatus.probe.status.PSObject.Properties.Name -contains "blind_space_count") {
                    $blindSpaceCount = [int64]$SupervisorStatus.probe.status.blind_space_count
                }
                if ($SupervisorStatus.probe.status.PSObject.Properties.Name -contains "started_utc") {
                    $startedUtc = [string]$SupervisorStatus.probe.status.started_utc
                    try {
                        $startedAt = [DateTimeOffset]::Parse($startedUtc)
                        $silentSeconds = [int64]([DateTimeOffset]::UtcNow - $startedAt).TotalSeconds
                    } catch {
                        $silentSeconds = $null
                    }
                }
            }
        }
        if ($SupervisorStatus.PSObject.Properties.Name -contains "blind_space_interval_ms" -and $blindSpaceCount -ne $null) {
            $activeAutobreakSeconds = [Math]::Round(($blindSpaceCount * [double]$SupervisorStatus.blind_space_interval_ms) / 1000.0, 1)
        }
    }

    $com3Present = [bool]($ports -contains "COM3")
    $diagnosis = if ($RouterTcp22) {
        "ROUTER_SSH_UP_UART_NOT_REQUIRED"
    } elseif (-not $com3Present) {
        "COM3_NOT_ENUMERATED"
    } elseif (-not $SupervisorStatus) {
        "UART_SUPERVISOR_MISSING"
    } elseif ($state -eq "waiting_uart_rx" -and $blindEnabled -and $rxBytes -eq 0 -and $blindSpaceCount -ge 20) {
        "UART_RX_SILENT_DESPITE_ACTIVE_AUTOBREAK"
    } elseif ($state -eq "waiting_uart_rx" -and $rxBytes -eq 0) {
        "UART_RX_SILENT_WAITING"
    } elseif ($rxBytes -gt 0) {
        "UART_RX_SEEN"
    } else {
        "UART_STATE_INDETERMINATE"
    }

    $severity = if ($diagnosis -eq "UART_RX_SILENT_DESPITE_ACTIVE_AUTOBREAK" -and $silentSeconds -ne $null -and $silentSeconds -ge 300) {
        "physical_path_blocked"
    } elseif ($diagnosis -eq "UART_RX_SILENT_DESPITE_ACTIVE_AUTOBREAK") {
        "autobreak_active_waiting_power_cycle_window"
    } elseif ($diagnosis -eq "UART_RX_SEEN" -or $RouterTcp22) {
        "path_available"
    } elseif (-not $com3Present) {
        "adapter_missing"
    } else {
        "waiting"
    }
    $recommendedAction = switch ($severity) {
        "physical_path_blocked" { "Check router TX to FTDI RX, common GND, 3.3V TTL adapter seating, and power-cycle with UART connected from first byte; current scripts are already transmitting autobreak spaces." }
        "autobreak_active_waiting_power_cycle_window" { "Power-cycle target while keeping COM3 connected; supervisor is already sending spaces and will continue with the active flash target after RX." }
        "adapter_missing" { "Reconnect FTDI adapter until COM3 enumerates." }
        "path_available" { "Do not touch COM3; let existing watcher continue into F66 or SSH radio gate." }
        default { "Keep watchers running and refresh status after power-cycle or SSH return." }
    }

    [ordered]@{
        diagnosis = $diagnosis
        severity = $severity
        recommended_action = $recommendedAction
        ports = $ports
        pnp_ports = $pnpPorts
        com3_present = $com3Present
        supervisor_state = $state
        rx_bytes = $rxBytes
        blind_autobreak_enabled = $blindEnabled
        blind_space_count = $blindSpaceCount
        started_utc = $startedUtc
        silent_seconds = $silentSeconds
        active_autobreak_seconds = $activeAutobreakSeconds
    }
}

$latestSupervisorDir = Get-LatestDir (Join-Path $Root "outputs\postflash") "aelita-recover-uart-f66-*"
$supervisorStatus = $null
if ($latestSupervisorDir) {
    $supervisorStatus = Read-JsonFile (Join-Path $latestSupervisorDir.FullName "status.json")
}
$supervisorRxDir = if ($latestSupervisorDir) { Join-Path $latestSupervisorDir.FullName "rx-continuous" } else { "" }

$latestF66Dir = Get-LatestDir (Join-Path $Root "outputs\flash-watch") "f66-2g-qguard-*"
$f66Status = $null
if ($latestF66Dir) {
    $f66Status = Read-JsonFile (Join-Path $latestF66Dir.FullName "status.json")
}

$latestF76Dir = Get-LatestExecutedFlashDir (Join-Path $Root "outputs\flash-watch") "f76-2g-stable-5g-control-stage-guard-*"
$f76Status = $null
if ($latestF76Dir) {
    $f76Status = Read-JsonFile (Join-Path $latestF76Dir.FullName "status.json")
}

$latestF76MonitorDir = Get-LatestDir (Join-Path $Root "outputs\postflash") "f76-flash-pass-then-stage-gate-*"
$f76MonitorStatus = $null
if ($latestF76MonitorDir) {
    $f76MonitorStatus = Read-JsonFile (Join-Path $latestF76MonitorDir.FullName "status.json")
}

$latestF77Dir = Get-LatestExecutedFlashDir (Join-Path $Root "outputs\flash-watch") "f77-2g-fast-5g-stage-guard-*"
$f77Status = $null
if ($latestF77Dir) {
    $f77Status = Read-JsonFile (Join-Path $latestF77Dir.FullName "status.json")
}

$latestF77MonitorDir = Get-LatestDir (Join-Path $Root "outputs\postflash") "f77-flash-pass-then-stage-gate-*"
$f77MonitorStatus = $null
if ($latestF77MonitorDir) {
    $f77MonitorStatus = Read-JsonFile (Join-Path $latestF77MonitorDir.FullName "status.json")
}

$latestF78Dir = Get-LatestExecutedFlashDir (Join-Path $Root "outputs\flash-watch") "f78-2g-fast-5g-precontrol-stage-guard-*"
$f78Status = $null
if ($latestF78Dir) {
    $f78Status = Read-JsonFile (Join-Path $latestF78Dir.FullName "status.json")
}

$latestF78MonitorDir = Get-LatestDir (Join-Path $Root "outputs\postflash") "f78-flash-pass-then-stage-gate-*"
$f78MonitorStatus = $null
if ($latestF78MonitorDir) {
    $f78MonitorStatus = Read-JsonFile (Join-Path $latestF78MonitorDir.FullName "status.json")
}

$latestF83Dir = Get-LatestExecutedFlashDir (Join-Path $Root "outputs\flash-watch") "f83-5g-post-hostapd-stage-2g-mcs7-*"
$f83Status = $null
if ($latestF83Dir) {
    $f83Status = Read-JsonFile (Join-Path $latestF83Dir.FullName "status.json")
}

$latestF83MonitorDir = Get-LatestDir (Join-Path $Root "outputs\postflash") "f83-flash-pass-then-stage-gate-*"
$f83MonitorStatus = $null
if ($latestF83MonitorDir) {
    $f83MonitorStatus = Read-JsonFile (Join-Path $latestF83MonitorDir.FullName "status.json")
}

$latestF83AutoArmDir = Get-LatestDir (Join-Path $Root "outputs\postflash") "f83-auto-arm-*"
$f83AutoArmStatus = $null
if ($latestF83AutoArmDir) {
    $f83AutoArmStatus = Read-JsonFile (Join-Path $latestF83AutoArmDir.FullName "status.json")
}

$latestF75Dir = Get-LatestDir (Join-Path $Root "outputs\flash-watch") "f75-2g-stable-5g-manual-*"
$f75Status = $null
if ($latestF75Dir) {
    $f75Status = Read-JsonFile (Join-Path $latestF75Dir.FullName "status.json")
}

$latestF65Dir = Get-LatestDir (Join-Path $Root "outputs\flash-watch") "f65-isolated-5g-*"
$f65Status = $null
if ($latestF65Dir) {
    $f65Status = Read-JsonFile (Join-Path $latestF65Dir.FullName "status.json")
}

$latestF125Dir = Get-LatestDir (Join-Path $Root "outputs\flash-watch") "f125-5g-assoc-window-guard*"
$f125Status = $null
if ($latestF125Dir) {
    $f125Status = Read-JsonFile (Join-Path $latestF125Dir.FullName "status.json")
}
$f125State = if ($f125Status) { [string]$f125Status.state } else { "missing" }
$f125Alive = $false
if ($f125Status -and $f125Status.PSObject.Properties.Name -contains "pid") {
    $f125Alive = Test-ProcessAlive $f125Status.pid
}
$f125StdoutPath = if ($f125Status -and $f125Status.PSObject.Properties.Name -contains "stdout") {
    [string]$f125Status.stdout
} else {
    ""
}
$f125StdoutText = if ($f125StdoutPath -and (Test-Path -LiteralPath $f125StdoutPath -PathType Leaf)) {
    Get-Content -LiteralPath $f125StdoutPath -Raw
} else {
    ""
}
$f125UartPath = ""
if ($f125StdoutText -match 'log=([^\r\n]+\.log)') {
    $f125UartPath = $Matches[1].Trim()
}
$f125BlindSpaceCount = 0
$f125BlindMatches = @([regex]::Matches($f125StdoutText, 'OMQ3_F45_AUTOBREAK_BLIND_SPACE_SENT=(\d+)'))
if ($f125BlindMatches.Count -gt 0) {
    $f125BlindSpaceCount = [int64]$f125BlindMatches[-1].Groups[1].Value
}
$f125StartedSeconds = $null
if ($f125Status -and $f125Status.PSObject.Properties.Name -contains "updated_at") {
    try {
        $f125StartedAt = [DateTimeOffset]::Parse([string]$f125Status.updated_at)
        $f125StartedSeconds = [int64]([DateTimeOffset]::Now - $f125StartedAt).TotalSeconds
    } catch {
        $f125StartedSeconds = $null
    }
}
$f125UartProbe = Get-FileProbe $f125UartPath
$f125UartRxZeroMarker = [bool]($f125StdoutText -match 'OMQ3_F45_AUTOBREAK_UART_RX_SILENT_ZERO_BYTES|UART_RX_SILENT_ZERO_BYTES')
$f125UartRxZeroObserved = [bool]($f125UartRxZeroMarker -or ($f125UartProbe.exists -and $f125UartProbe.bytes -eq 0 -and $f125BlindSpaceCount -ge 20))
$f125UartRxZeroLong = [bool]($f125UartRxZeroObserved -and $f125StartedSeconds -ne $null -and $f125StartedSeconds -ge 300)

$latestF126Dir = Get-LatestDir (Join-Path $Root "outputs\flash-watch") "f126-5g-assoc-observe*"
$f126Status = $null
if ($latestF126Dir) {
    $f126Status = Read-JsonFile (Join-Path $latestF126Dir.FullName "status.json")
}
$f126State = if ($f126Status) { [string]$f126Status.state } else { "missing" }
$f126Alive = $false
if ($f126Status -and $f126Status.PSObject.Properties.Name -contains "pid") {
    $f126Alive = Test-ProcessAlive $f126Status.pid
}
$f126StdoutPath = if ($f126Status -and $f126Status.PSObject.Properties.Name -contains "stdout") {
    [string]$f126Status.stdout
} else {
    ""
}
$f126StdoutText = if ($f126StdoutPath -and (Test-Path -LiteralPath $f126StdoutPath -PathType Leaf)) {
    Get-Content -LiteralPath $f126StdoutPath -Raw
} else {
    ""
}
$f126UartPath = ""
if ($f126StdoutText -match 'log=([^\r\n]+\.log)') {
    $f126UartPath = $Matches[1].Trim()
}
$f126BlindSpaceCount = 0
$f126BlindMatches = @([regex]::Matches($f126StdoutText, 'OMQ3_F45_AUTOBREAK_BLIND_SPACE_SENT=(\d+)'))
if ($f126BlindMatches.Count -gt 0) {
    $f126BlindSpaceCount = [int64]$f126BlindMatches[-1].Groups[1].Value
}
$f126StartedSeconds = $null
if ($f126Status -and $f126Status.PSObject.Properties.Name -contains "updated_at") {
    try {
        $f126StartedAt = [DateTimeOffset]::Parse([string]$f126Status.updated_at)
        $f126StartedSeconds = [int64]([DateTimeOffset]::Now - $f126StartedAt).TotalSeconds
    } catch {
        $f126StartedSeconds = $null
    }
}
$f126UartProbe = Get-FileProbe $f126UartPath
$f126UartRxZeroMarker = [bool]($f126StdoutText -match 'OMQ3_F45_AUTOBREAK_UART_RX_SILENT_ZERO_BYTES|UART_RX_SILENT_ZERO_BYTES')
$f126UartRxZeroObserved = [bool]($f126UartRxZeroMarker -or ($f126UartProbe.exists -and $f126UartProbe.bytes -eq 0 -and $f126BlindSpaceCount -ge 20))
$f126UartRxZeroLong = [bool]($f126UartRxZeroObserved -and $f126StartedSeconds -ne $null -and $f126StartedSeconds -ge 300)

$latestF66MonitorDir = Get-LatestDir (Join-Path $Root "outputs\postflash") "f66-auto-2g-monitor-*"
$f66MonitorStatus = $null
if ($latestF66MonitorDir) {
    $f66MonitorStatus = Read-JsonFile (Join-Path $latestF66MonitorDir.FullName "monitor-status.json")
}

$latestF125MonitorDir = Get-LatestDir (Join-Path $Root "outputs\postflash") "f125-5g-assoc-only-monitor-*"
$f125MonitorStatus = $null
if ($latestF125MonitorDir) {
    $f125MonitorStatus = Read-JsonFile (Join-Path $latestF125MonitorDir.FullName "monitor-status.json")
}

$latestF126MonitorDir = Get-LatestDir (Join-Path $Root "outputs\postflash") "f126-5g-assoc-only-monitor-*"
$f126MonitorStatus = $null
if ($latestF126MonitorDir) {
    $f126MonitorStatus = Read-JsonFile (Join-Path $latestF126MonitorDir.FullName "monitor-status.json")
}

$latestRouterSshMonitorDir = Get-LatestDir (Join-Path $Root "outputs\postflash") "router-ssh-radio-monitor-*"
$routerSshMonitorStatus = $null
if ($latestRouterSshMonitorDir) {
    $routerSshMonitorStatus = Read-JsonFile (Join-Path $latestRouterSshMonitorDir.FullName "monitor-status.json")
}

$routerPing = [bool](Test-Connection -ComputerName $RouterHost -Count 1 -Quiet -ErrorAction SilentlyContinue)
$routerTcp22 = [bool](Test-TcpPort $RouterHost 22 $TcpTimeoutSeconds)
$uartTriage = Get-SerialTriage $supervisorStatus $routerTcp22
$f93F95Chain = Get-F93F95ChainSnapshot $RouterHost

$aelita = [ordered]@{
    skipped = [bool]$SkipAelita
    host = $AelitaHost
    tcp22 = $null
    ssh = $null
    result = $null
    scan = $null
}
if (-not $SkipAelita) {
    $aelita.tcp22 = [bool](Test-TcpPort $AelitaHost 22 $TcpTimeoutSeconds)
    $connectOut = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "connect_aelita_auto.ps1") `
        -Mode connect `
        -HostAddress $AelitaHost `
        -User $AelitaUser `
        -WaitSeconds 1 2>&1
    $aelita.ssh = [bool]($LASTEXITCODE -eq 0 -and (($connectOut -join "`n") -match "OMAELITA_CONNECT_PASS=1"))
    $aelita.result = ($connectOut -join "`n")

    if ($IncludeAelitaScan -and $aelita.ssh) {
        $scanOut = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "connect_aelita_auto.ps1") `
            -Mode ssh `
            -HostAddress $AelitaHost `
            -User $AelitaUser `
            -RemoteCommand "netsh wlan show networks mode=bssid" 2>&1
        $aelita.scan = ($scanOut -join "`n")
    }
}

$supervisorState = if ($supervisorStatus) { [string]$supervisorStatus.state } else { "missing" }
$f76State = if ($f76Status) { [string]$f76Status.state } else { "missing" }
$f76Alive = $false
if ($f76Status) {
    $f76Pid = $null
    if ($f76Status.PSObject.Properties.Name -contains "process_id") {
        $f76Pid = $f76Status.process_id
    } elseif ($f76Status.PSObject.Properties.Name -contains "current_process_id") {
        $f76Pid = $f76Status.current_process_id
    }
    $f76Alive = Test-ProcessAlive $f76Pid
}
$f76StdoutPath = if ($f76Status -and $f76Status.PSObject.Properties.Name -contains "output_dir") {
    Join-Path ([string]$f76Status.output_dir) "stdout.log"
} else {
    ""
}
$f76StdoutText = if ($f76StdoutPath -and (Test-Path -LiteralPath $f76StdoutPath -PathType Leaf)) {
    Get-Content -LiteralPath $f76StdoutPath -Raw
} else {
    ""
}
$f76UartRxZeroMarker = [bool]($f76StdoutText -match 'OMQ3_F45_AUTOBREAK_UART_RX_SILENT_ZERO_BYTES|UART_RX_SILENT_ZERO_BYTES')
$f76UartPath = ""
if ($f76StdoutText -match 'log=([^\r\n]+\.log)') {
    $f76UartPath = $Matches[1].Trim()
}
$f76BlindSpaceCount = 0
$f76BlindMatches = @([regex]::Matches($f76StdoutText, 'OMQ3_F45_AUTOBREAK_BLIND_SPACE_SENT=(\d+)'))
if ($f76BlindMatches.Count -gt 0) {
    $f76BlindSpaceCount = [int64]$f76BlindMatches[-1].Groups[1].Value
}
$f76StartedSeconds = $null
if ($f76Status -and $f76Status.PSObject.Properties.Name -contains "updated_at") {
    try {
        $f76StartedAt = [DateTimeOffset]::Parse([string]$f76Status.updated_at)
        $f76StartedSeconds = [int64]([DateTimeOffset]::Now - $f76StartedAt).TotalSeconds
    } catch {
        $f76StartedSeconds = $null
    }
}
$f76UartProbe = Get-FileProbe $f76UartPath
$f76UartRxZeroObserved = [bool]($f76UartRxZeroMarker -or ($f76UartProbe.exists -and $f76UartProbe.bytes -eq 0 -and $f76BlindSpaceCount -ge 20))
$f76UartRxZeroLong = [bool]($f76UartRxZeroObserved -and $f76StartedSeconds -ne $null -and $f76StartedSeconds -ge 300)
$f77State = if ($f77Status) { [string]$f77Status.state } else { "missing" }
$f77Alive = $false
if ($f77Status) {
    $f77Pid = $null
    if ($f77Status.PSObject.Properties.Name -contains "process_id") {
        $f77Pid = $f77Status.process_id
    } elseif ($f77Status.PSObject.Properties.Name -contains "current_process_id") {
        $f77Pid = $f77Status.current_process_id
    }
    $f77Alive = Test-ProcessAlive $f77Pid
}
$f77StdoutPath = if ($f77Status -and $f77Status.PSObject.Properties.Name -contains "output_dir") {
    Join-Path ([string]$f77Status.output_dir) "stdout.log"
} else {
    ""
}
$f77StdoutText = if ($f77StdoutPath -and (Test-Path -LiteralPath $f77StdoutPath -PathType Leaf)) {
    Get-Content -LiteralPath $f77StdoutPath -Raw
} else {
    ""
}
$f77UartRxZeroMarker = [bool]($f77StdoutText -match 'OMQ3_F45_AUTOBREAK_UART_RX_SILENT_ZERO_BYTES|UART_RX_SILENT_ZERO_BYTES')
$f77UartPath = ""
if ($f77StdoutText -match 'log=([^\r\n]+\.log)') {
    $f77UartPath = $Matches[1].Trim()
}
$f77BlindSpaceCount = 0
$f77BlindMatches = @([regex]::Matches($f77StdoutText, 'OMQ3_F45_AUTOBREAK_BLIND_SPACE_SENT=(\d+)'))
if ($f77BlindMatches.Count -gt 0) {
    $f77BlindSpaceCount = [int64]$f77BlindMatches[-1].Groups[1].Value
}
$f77StartedSeconds = $null
if ($f77Status -and $f77Status.PSObject.Properties.Name -contains "updated_at") {
    try {
        $f77StartedAt = [DateTimeOffset]::Parse([string]$f77Status.updated_at)
        $f77StartedSeconds = [int64]([DateTimeOffset]::Now - $f77StartedAt).TotalSeconds
    } catch {
        $f77StartedSeconds = $null
    }
}
$f77UartProbe = Get-FileProbe $f77UartPath
$f77UartRxZeroObserved = [bool]($f77UartRxZeroMarker -or ($f77UartProbe.exists -and $f77UartProbe.bytes -eq 0 -and $f77BlindSpaceCount -ge 20))
$f77UartRxZeroLong = [bool]($f77UartRxZeroObserved -and $f77StartedSeconds -ne $null -and $f77StartedSeconds -ge 300)
$f78State = if ($f78Status) { [string]$f78Status.state } else { "missing" }
$f78Alive = $false
if ($f78Status) {
    $f78Pid = $null
    if ($f78Status.PSObject.Properties.Name -contains "process_id") {
        $f78Pid = $f78Status.process_id
    } elseif ($f78Status.PSObject.Properties.Name -contains "current_process_id") {
        $f78Pid = $f78Status.current_process_id
    }
    $f78Alive = Test-ProcessAlive $f78Pid
}
$f78StdoutPath = if ($f78Status -and $f78Status.PSObject.Properties.Name -contains "output_dir") {
    Join-Path ([string]$f78Status.output_dir) "stdout.log"
} else {
    ""
}
$f78StdoutText = if ($f78StdoutPath -and (Test-Path -LiteralPath $f78StdoutPath -PathType Leaf)) {
    Get-Content -LiteralPath $f78StdoutPath -Raw
} else {
    ""
}
$f78UartRxZeroMarker = [bool]($f78StdoutText -match 'OMQ3_F45_AUTOBREAK_UART_RX_SILENT_ZERO_BYTES|UART_RX_SILENT_ZERO_BYTES')
$f78UartPath = ""
if ($f78StdoutText -match 'log=([^\r\n]+\.log)') {
    $f78UartPath = $Matches[1].Trim()
}
$f78BlindSpaceCount = 0
$f78BlindMatches = @([regex]::Matches($f78StdoutText, 'OMQ3_F45_AUTOBREAK_BLIND_SPACE_SENT=(\d+)'))
if ($f78BlindMatches.Count -gt 0) {
    $f78BlindSpaceCount = [int64]$f78BlindMatches[-1].Groups[1].Value
}
$f78StartedSeconds = $null
if ($f78Status -and $f78Status.PSObject.Properties.Name -contains "updated_at") {
    try {
        $f78StartedAt = [DateTimeOffset]::Parse([string]$f78Status.updated_at)
        $f78StartedSeconds = [int64]([DateTimeOffset]::Now - $f78StartedAt).TotalSeconds
    } catch {
        $f78StartedSeconds = $null
    }
}
$f78UartProbe = Get-FileProbe $f78UartPath
$f78UartRxZeroObserved = [bool]($f78UartRxZeroMarker -or ($f78UartProbe.exists -and $f78UartProbe.bytes -eq 0 -and $f78BlindSpaceCount -ge 20))
$f78UartRxZeroLong = [bool]($f78UartRxZeroObserved -and $f78StartedSeconds -ne $null -and $f78StartedSeconds -ge 300)
$f83State = if ($f83Status) { [string]$f83Status.state } else { "missing" }
$f83Alive = $false
if ($f83Status) {
    $f83Pid = $null
    if ($f83Status.PSObject.Properties.Name -contains "process_id") {
        $f83Pid = $f83Status.process_id
    } elseif ($f83Status.PSObject.Properties.Name -contains "current_process_id") {
        $f83Pid = $f83Status.current_process_id
    }
    $f83Alive = Test-ProcessAlive $f83Pid
}
$f83StdoutPath = if ($f83AutoArmStatus -and $f83AutoArmStatus.PSObject.Properties.Name -contains "flash_launch_log") {
    [string]$f83AutoArmStatus.flash_launch_log
} elseif ($f83Status -and $f83Status.PSObject.Properties.Name -contains "output_dir") {
    Join-Path ([string]$f83Status.output_dir) "stdout.log"
} else {
    ""
}
$f83StdoutText = if ($f83StdoutPath -and (Test-Path -LiteralPath $f83StdoutPath -PathType Leaf)) {
    Get-Content -LiteralPath $f83StdoutPath -Raw
} else {
    ""
}
$f83UartRxZeroMarker = [bool]($f83StdoutText -match 'OMQ3_F45_AUTOBREAK_UART_RX_SILENT_ZERO_BYTES|UART_RX_SILENT_ZERO_BYTES')
$f83UartPath = ""
if ($f83StdoutText -match 'log=([^\r\n]+\.log)') {
    $f83UartPath = $Matches[1].Trim()
}
$f83BlindSpaceCount = 0
$f83BlindMatches = @([regex]::Matches($f83StdoutText, 'OMQ3_F45_AUTOBREAK_BLIND_SPACE_SENT=(\d+)'))
if ($f83BlindMatches.Count -gt 0) {
    $f83BlindSpaceCount = [int64]$f83BlindMatches[-1].Groups[1].Value
}
$f83StartedSeconds = $null
if ($f83Status -and $f83Status.PSObject.Properties.Name -contains "updated_at") {
    try {
        $f83StartedAt = [DateTimeOffset]::Parse([string]$f83Status.updated_at)
        $f83StartedSeconds = [int64]([DateTimeOffset]::Now - $f83StartedAt).TotalSeconds
    } catch {
        $f83StartedSeconds = $null
    }
}
$f83UartProbe = Get-FileProbe $f83UartPath
$f83UartRxZeroObserved = [bool]($f83UartRxZeroMarker -or ($f83UartProbe.exists -and $f83UartProbe.bytes -eq 0 -and $f83BlindSpaceCount -ge 20))
$f83UartRxZeroLong = [bool]($f83UartRxZeroObserved -and $f83StartedSeconds -ne $null -and $f83StartedSeconds -ge 300)
$f75State = if ($f75Status) { [string]$f75Status.state } else { "missing" }
$f75Alive = $false
if ($f75Status) {
    $f75Pid = $null
    if ($f75Status.PSObject.Properties.Name -contains "process_id") {
        $f75Pid = $f75Status.process_id
    } elseif ($f75Status.PSObject.Properties.Name -contains "current_process_id") {
        $f75Pid = $f75Status.current_process_id
    }
    $f75Alive = Test-ProcessAlive $f75Pid
}
$f66State = if ($f66Status) { [string]$f66Status.state } else { "missing" }
$f66Alive = $false
if ($f66Status -and $f66Status.PSObject.Properties.Name -contains "watcher_pid") {
    $f66Alive = Test-ProcessAlive $f66Status.watcher_pid
}
$f65Alive = $false
if ($f65Status -and $f65Status.PSObject.Properties.Name -contains "watcher_pid") {
    $f65Alive = Test-ProcessAlive $f65Status.watcher_pid
}
if (-not $routerTcp22 -and $f83State -in @("running_foreground", "background_armed", "failed") -and $f83UartRxZeroObserved) {
    $uartTriage = [ordered]@{
        diagnosis = "F83_UART_RX_ZERO_CURRENT_ATTEMPT"
        severity = "physical_path_blocked_or_power_cycle_needed"
        recommended_action = "Keep F83 watcher armed only if COM3 is connected, then power-cycle target with UART connected from first byte; current F83 attempt is sending autobreak spaces but has received zero UART bytes and has not flashed."
        ports = $uartTriage.ports
        pnp_ports = $uartTriage.pnp_ports
        com3_present = $uartTriage.com3_present
        supervisor_state = $supervisorState
        rx_bytes = 0
        blind_autobreak_enabled = $true
        blind_space_count = $f83BlindSpaceCount
        started_utc = $null
        silent_seconds = $f83StartedSeconds
        active_autobreak_seconds = [Math]::Round(($f83BlindSpaceCount * 0.25), 1)
        source = "f83"
        uart_log = $f83UartProbe
        terminal_marker = $f83UartRxZeroMarker
    }
} elseif (-not $routerTcp22 -and $f78State -in @("running_foreground", "background_armed", "failed") -and $f78UartRxZeroObserved) {
    $uartTriage = [ordered]@{
        diagnosis = "F78_UART_RX_ZERO_CURRENT_ATTEMPT"
        severity = "physical_path_blocked_or_power_cycle_needed"
        recommended_action = "Keep F78 watcher armed only if COM3 is connected, then power-cycle target with UART connected from first byte; current F78 attempt is sending autobreak spaces but has received zero UART bytes and has not flashed."
        ports = $uartTriage.ports
        pnp_ports = $uartTriage.pnp_ports
        com3_present = $uartTriage.com3_present
        supervisor_state = $supervisorState
        rx_bytes = 0
        blind_autobreak_enabled = $true
        blind_space_count = $f78BlindSpaceCount
        started_utc = $null
        silent_seconds = $f78StartedSeconds
        active_autobreak_seconds = [Math]::Round(($f78BlindSpaceCount * 0.25), 1)
        source = "f78"
        uart_log = $f78UartProbe
        terminal_marker = $f78UartRxZeroMarker
    }
} elseif (-not $routerTcp22 -and $f77State -in @("running_foreground", "background_armed", "failed") -and $f77UartRxZeroObserved) {
    $uartTriage = [ordered]@{
        diagnosis = "F77_UART_RX_ZERO_CURRENT_ATTEMPT"
        severity = "physical_path_blocked_or_power_cycle_needed"
        recommended_action = "Keep F77 watcher armed only if COM3 is connected, then power-cycle target with UART connected from first byte; current F77 attempt is sending autobreak spaces but has received zero UART bytes and has not flashed."
        ports = $uartTriage.ports
        pnp_ports = $uartTriage.pnp_ports
        com3_present = $uartTriage.com3_present
        supervisor_state = $supervisorState
        rx_bytes = 0
        blind_autobreak_enabled = $true
        blind_space_count = $f77BlindSpaceCount
        started_utc = $null
        silent_seconds = $f77StartedSeconds
        active_autobreak_seconds = [Math]::Round(($f77BlindSpaceCount * 0.25), 1)
        source = "f77"
        uart_log = $f77UartProbe
        terminal_marker = $f77UartRxZeroMarker
    }
} elseif (-not $routerTcp22 -and $f76State -in @("running_foreground", "background_armed", "failed") -and $f76UartRxZeroObserved) {
    $uartTriage = [ordered]@{
        diagnosis = "F76_UART_RX_ZERO_LAST_ATTEMPT"
        severity = "physical_path_blocked_or_power_cycle_needed"
        recommended_action = "Rearm F76 watcher only when COM3 is free, then power-cycle target with UART connected from first byte; last F76 attempt sent autobreak spaces but received zero UART bytes and did not flash."
        ports = $uartTriage.ports
        pnp_ports = $uartTriage.pnp_ports
        com3_present = $uartTriage.com3_present
        supervisor_state = $supervisorState
        rx_bytes = 0
        blind_autobreak_enabled = $true
        blind_space_count = $f76BlindSpaceCount
        started_utc = $null
        silent_seconds = $f76StartedSeconds
        active_autobreak_seconds = [Math]::Round(($f76BlindSpaceCount * 0.25), 1)
        source = "f76"
        uart_log = $f76UartProbe
        terminal_marker = $f76UartRxZeroMarker
    }
}
$f83MonitorState = if ($f83MonitorStatus) { [string]$f83MonitorStatus.state } else { "missing" }
$f125MonitorState = if ($f125MonitorStatus) { [string]$f125MonitorStatus.state } else { "missing" }
$f125MonitorAlive = $false
if ($f125MonitorStatus -and $f125MonitorStatus.PSObject.Properties.Name -contains "process_id") {
    $f125MonitorAlive = Test-ProcessAlive $f125MonitorStatus.process_id
}
$f126MonitorState = if ($f126MonitorStatus) { [string]$f126MonitorStatus.state } else { "missing" }
$f126MonitorAlive = $false
if ($f126MonitorStatus -and $f126MonitorStatus.PSObject.Properties.Name -contains "process_id") {
    $f126MonitorAlive = Test-ProcessAlive $f126MonitorStatus.process_id
}
$f93F95ChainState = if ($f93F95Chain -and $f93F95Chain.PSObject.Properties.Name -contains "chain_state") { [string]$f93F95Chain.chain_state } else { "missing" }
$f93F95UartZero = [bool]($f93F95Chain -and $f93F95Chain.PSObject.Properties.Name -contains "uart_zero_bytes_stale" -and [bool]$f93F95Chain.uart_zero_bytes_stale)
if ($f93F95UartZero) {
    $uartTriage = [ordered]@{
        diagnosis = "F93_F95_UART_RX_ZERO_CURRENT_CHAIN"
        severity = "physical_path_blocked_or_power_cycle_needed"
        recommended_action = [string]$f93F95Chain.next_action
        ports = $uartTriage.ports
        pnp_ports = $uartTriage.pnp_ports
        com3_present = $uartTriage.com3_present
        supervisor_state = [string]$f93F95Chain.f93_state
        rx_bytes = 0
        blind_autobreak_enabled = $true
        blind_space_count = if ($f93F95Chain.PSObject.Properties.Name -contains "blind_space_count") { [int64]$f93F95Chain.blind_space_count } else { $null }
        started_utc = $null
        silent_seconds = if ($f93F95Chain.uart -and $f93F95Chain.uart.PSObject.Properties.Name -contains "age_seconds") { [double]$f93F95Chain.uart.age_seconds } else { $null }
        active_autobreak_seconds = if ($f93F95Chain.PSObject.Properties.Name -contains "blind_space_count") { [Math]::Round(([double]$f93F95Chain.blind_space_count * 0.25), 1) } else { $null }
        source = "f93_f95"
        uart_log = $f93F95Chain.uart
    }
}
if (-not $routerTcp22 -and $f125State -eq "armed_waiting_bootbase" -and $f125Alive -and $f125UartRxZeroObserved) {
    $uartTriage = [ordered]@{
        diagnosis = "F125_UART_RX_ZERO_CURRENT_ATTEMPT"
        severity = "physical_path_blocked_or_power_cycle_needed"
        recommended_action = "Keep F125 watcher armed only if COM3 is connected, then power-cycle target with UART connected from first byte; current F125 attempt is sending autobreak spaces and ATGU but has received zero UART bytes and has not flashed."
        ports = $uartTriage.ports
        pnp_ports = $uartTriage.pnp_ports
        com3_present = $uartTriage.com3_present
        supervisor_state = $f125State
        rx_bytes = 0
        blind_autobreak_enabled = $true
        blind_space_count = $f125BlindSpaceCount
        started_utc = $null
        silent_seconds = $f125StartedSeconds
        active_autobreak_seconds = [Math]::Round(($f125BlindSpaceCount * 0.25), 1)
        source = "f125"
        uart_log = $f125UartProbe
        terminal_marker = $f125UartRxZeroMarker
    }
}
if (-not $routerTcp22 -and $f126State -eq "armed_waiting_bootbase" -and $f126Alive -and $f126UartRxZeroObserved) {
    $uartTriage = [ordered]@{
        diagnosis = "F126_UART_RX_ZERO_CURRENT_ATTEMPT"
        severity = "physical_path_blocked_or_power_cycle_needed"
        recommended_action = "Keep F126 watcher armed only if COM3 is connected, then power-cycle target with UART connected from first byte; current F126 attempt is sending autobreak spaces and ATGU but has received zero UART bytes and has not flashed."
        ports = $uartTriage.ports
        pnp_ports = $uartTriage.pnp_ports
        com3_present = $uartTriage.com3_present
        supervisor_state = $f126State
        rx_bytes = 0
        blind_autobreak_enabled = $true
        blind_space_count = $f126BlindSpaceCount
        started_utc = $null
        silent_seconds = $f126StartedSeconds
        active_autobreak_seconds = [Math]::Round(($f126BlindSpaceCount * 0.25), 1)
        source = "f126"
        uart_log = $f126UartProbe
        terminal_marker = $f126UartRxZeroMarker
    }
}
$decision = if ($f126MonitorState -eq "pass") {
    "F126_5G_ASSOC_ONLY_PASS"
} elseif ($f126MonitorState -eq "watching" -and $f126MonitorAlive) {
    "WATCH_F126_FLASH_THEN_5G_ASSOC_ONLY"
} elseif ($f126MonitorState -eq "uart_rx_zero_no_flash" -and $f126MonitorAlive) {
    "F126_UART_RX_ZERO_WAITING_POWER_CYCLE_OR_WIRING"
} elseif ($f126State -eq "armed_waiting_bootbase" -and $f126Alive) {
    "WATCH_F126_FLASH"
} elseif ($f125MonitorState -eq "pass") {
    "F125_5G_ASSOC_ONLY_PASS"
} elseif ($f125MonitorState -eq "watching" -and $f125MonitorAlive) {
    "WATCH_F125_FLASH_THEN_5G_ASSOC_ONLY"
} elseif ($f125State -eq "armed_waiting_bootbase" -and $f125Alive) {
    "WATCH_F125_FLASH"
} elseif ($f93F95ChainState -eq "pass") {
    "F93_F95_CHAIN_PASS_REVIEW_2G_GATE"
} elseif ($f93F95ChainState -eq "watching_f93" -and $f93F95UartZero) {
    "F93_F95_CHAIN_UART_RX_ZERO_WAITING_POWER_CYCLE_OR_WIRING"
} elseif ($f93F95ChainState -eq "watching_f93") {
    "WATCH_F93_RESTORE_THEN_F95_CHAIN"
} elseif ($f93F95ChainState -match "failed|timeout") {
    "F93_F95_CHAIN_$($f93F95ChainState.ToUpperInvariant())"
} elseif ($f83MonitorState -eq "pass") {
    "F83_FLASH_2G_AND_5G_POST_HOSTAPD_STAGE_PASS"
} elseif ($f83State -eq "pass" -and $routerTcp22) {
    "RUN_F83_STAGE_GATE"
} elseif ($f83State -eq "pass") {
    "WAIT_ROUTER_SSH_AFTER_F83"
} elseif ($f83State -in @("running_foreground", "background_armed") -and $f83UartRxZeroLong) {
    "F83_FLASH_UART_RX_ZERO_WAITING_POWER_CYCLE_OR_WIRING"
} elseif ($f83State -in @("running_foreground", "background_armed") -and $f83Alive) {
    "WATCH_F83_FLASH"
} elseif ($f83State -in @("running_foreground", "background_armed") -and -not $f83Alive) {
    "F83_FLASH_WATCHER_STALE"
} elseif ($f83State -eq "failed" -and $f83UartRxZeroObserved) {
    "F83_FLASH_UART_RX_ZERO_WAITING_POWER_CYCLE_OR_WIRING"
} elseif ($f83State -in @("failed", "preflight_failed", "busy_com3", "ack_required")) {
    "F83_FLASH_$($f83State.ToUpperInvariant())"
} elseif ($f78State -eq "pass" -and $routerTcp22) {
    "RUN_F78_STAGE_GATE"
} elseif ($f78State -eq "pass") {
    "WAIT_ROUTER_SSH_AFTER_F78"
} elseif ($f78State -in @("running_foreground", "background_armed") -and $f78UartRxZeroLong) {
    "F78_FLASH_UART_RX_ZERO_WAITING_POWER_CYCLE_OR_WIRING"
} elseif ($f78State -in @("running_foreground", "background_armed") -and $f78Alive) {
    "WATCH_F78_FLASH"
} elseif ($f78State -in @("running_foreground", "background_armed") -and -not $f78Alive) {
    "F78_FLASH_WATCHER_STALE"
} elseif ($f78State -eq "failed" -and $f78UartRxZeroObserved) {
    "F78_FLASH_UART_RX_ZERO_WAITING_POWER_CYCLE_OR_WIRING"
} elseif ($f78State -in @("failed", "preflight_failed", "busy_com3", "ack_required")) {
    "F78_FLASH_$($f78State.ToUpperInvariant())"
} elseif ($f77State -eq "pass" -and $routerTcp22) {
    "RUN_F77_STAGE_GATE"
} elseif ($f77State -eq "pass") {
    "WAIT_ROUTER_SSH_AFTER_F77"
} elseif ($f77State -in @("running_foreground", "background_armed") -and $f77UartRxZeroLong) {
    "F77_FLASH_UART_RX_ZERO_WAITING_POWER_CYCLE_OR_WIRING"
} elseif ($f77State -in @("running_foreground", "background_armed") -and $f77Alive) {
    "WATCH_F77_FLASH"
} elseif ($f77State -in @("running_foreground", "background_armed") -and -not $f77Alive) {
    "F77_FLASH_WATCHER_STALE"
} elseif ($f77State -eq "failed" -and $f77UartRxZeroObserved) {
    "F77_FLASH_UART_RX_ZERO_WAITING_POWER_CYCLE_OR_WIRING"
} elseif ($f77State -in @("failed", "preflight_failed", "busy_com3", "ack_required")) {
    "F77_FLASH_$($f77State.ToUpperInvariant())"
} elseif ($f76State -eq "pass" -and $routerTcp22) {
    "RUN_F76_STAGE_GATE"
} elseif ($f76State -eq "pass") {
    "WAIT_ROUTER_SSH_AFTER_F76"
} elseif ($f76State -in @("running_foreground", "background_armed") -and $f76UartRxZeroLong) {
    "F76_FLASH_UART_RX_ZERO_WAITING_POWER_CYCLE_OR_WIRING"
} elseif ($f76State -in @("running_foreground", "background_armed") -and $f76Alive) {
    "WATCH_F76_FLASH"
} elseif ($f76State -in @("running_foreground", "background_armed") -and -not $f76Alive) {
    "F76_FLASH_WATCHER_STALE"
} elseif ($f76State -eq "failed" -and $f76UartRxZeroObserved) {
    "F76_FLASH_UART_RX_ZERO_WAITING_POWER_CYCLE_OR_WIRING"
} elseif ($f76State -in @("failed", "preflight_failed", "busy_com3", "ack_required")) {
    "F76_FLASH_$($f76State.ToUpperInvariant())"
} elseif ($f75State -in @("running_foreground", "background_armed") -and $f75Alive) {
    "WATCH_F75_FLASH"
} elseif ($f66State -eq "pass" -and $routerTcp22) {
    "RUN_2G_POSTFLASH_GATE"
} elseif ($f66State -eq "pass") {
    "WAIT_ROUTER_SSH_AFTER_F66"
} elseif ($supervisorState -eq "f66_started") {
    "WATCH_F66_FLASH"
} elseif ([string]$uartTriage.diagnosis -eq "UART_RX_SILENT_DESPITE_ACTIVE_AUTOBREAK") {
    if ([string]$uartTriage.severity -eq "physical_path_blocked") {
        "PHYSICAL_UART_RX_PATH_BLOCKED"
    } else {
        "WAIT_PHYSICAL_UART_RX_PATH_OR_POWER_CYCLE"
    }
} elseif ($supervisorState -eq "waiting_uart_rx") {
    "WAIT_UART_RX_OR_PHYSICAL_POWER_CYCLE"
} elseif ($routerTcp22) {
    "ROUTER_SSH_UP_RUN_RADIO_STATUS"
} else {
    "NO_ROUTER_PATH_CURRENTLY"
}

$statusProcessEntries = @(
    [pscustomobject]@{ source = "f83_status_current_process"; pid = if ($f83Status -and $f83Status.PSObject.Properties.Name -contains "current_process_id") { $f83Status.current_process_id } else { $null } },
    [pscustomobject]@{ source = "f83_status_background_process"; pid = if ($f83Status -and $f83Status.PSObject.Properties.Name -contains "process_id") { $f83Status.process_id } else { $null } },
    [pscustomobject]@{ source = "f83_auto_arm_flash_process"; pid = if ($f83AutoArmStatus -and $f83AutoArmStatus.PSObject.Properties.Name -contains "flash_pid") { $f83AutoArmStatus.flash_pid } else { $null } },
    [pscustomobject]@{ source = "f83_auto_arm_monitor_process"; pid = if ($f83AutoArmStatus -and $f83AutoArmStatus.PSObject.Properties.Name -contains "monitor_pid") { $f83AutoArmStatus.monitor_pid } else { $null } },
    [pscustomobject]@{ source = "f78_status_current_process"; pid = if ($f78Status -and $f78Status.PSObject.Properties.Name -contains "current_process_id") { $f78Status.current_process_id } else { $null } },
    [pscustomobject]@{ source = "f78_status_background_process"; pid = if ($f78Status -and $f78Status.PSObject.Properties.Name -contains "process_id") { $f78Status.process_id } else { $null } },
    [pscustomobject]@{ source = "f77_status_current_process"; pid = if ($f77Status -and $f77Status.PSObject.Properties.Name -contains "current_process_id") { $f77Status.current_process_id } else { $null } },
    [pscustomobject]@{ source = "f77_status_background_process"; pid = if ($f77Status -and $f77Status.PSObject.Properties.Name -contains "process_id") { $f77Status.process_id } else { $null } },
    [pscustomobject]@{ source = "f76_status_current_process"; pid = if ($f76Status -and $f76Status.PSObject.Properties.Name -contains "current_process_id") { $f76Status.current_process_id } else { $null } },
    [pscustomobject]@{ source = "f76_status_background_process"; pid = if ($f76Status -and $f76Status.PSObject.Properties.Name -contains "process_id") { $f76Status.process_id } else { $null } },
    [pscustomobject]@{ source = "f75_status_current_process"; pid = if ($f75Status -and $f75Status.PSObject.Properties.Name -contains "current_process_id") { $f75Status.current_process_id } else { $null } },
    [pscustomobject]@{ source = "f75_status_background_process"; pid = if ($f75Status -and $f75Status.PSObject.Properties.Name -contains "process_id") { $f75Status.process_id } else { $null } },
    [pscustomobject]@{ source = "f125_status_watcher"; pid = if ($f125Status -and $f125Status.PSObject.Properties.Name -contains "pid") { $f125Status.pid } else { $null } },
    [pscustomobject]@{ source = "f125_assoc_monitor_process"; pid = if ($f125MonitorStatus -and $f125MonitorStatus.PSObject.Properties.Name -contains "process_id") { $f125MonitorStatus.process_id } else { $null } },
    [pscustomobject]@{ source = "f126_status_watcher"; pid = if ($f126Status -and $f126Status.PSObject.Properties.Name -contains "pid") { $f126Status.pid } else { $null } },
    [pscustomobject]@{ source = "f126_assoc_monitor_process"; pid = if ($f126MonitorStatus -and $f126MonitorStatus.PSObject.Properties.Name -contains "process_id") { $f126MonitorStatus.process_id } else { $null } },
    [pscustomobject]@{ source = "f66_status_watcher"; pid = if ($f66Status -and $f66Status.PSObject.Properties.Name -contains "watcher_pid") { $f66Status.watcher_pid } else { $null } },
    [pscustomobject]@{ source = "f65_status_watcher"; pid = if ($f65Status -and $f65Status.PSObject.Properties.Name -contains "watcher_pid") { $f65Status.watcher_pid } else { $null } }
)
$statusBoundProcesses = @(Get-StatusBoundProcesses $statusProcessEntries)
$commandLineProcesses = @(Get-ProcessMatches)

$payload = [ordered]@{
    schema = "openmitrastar.aelita-radio-goal-status/v1"
    checked_at = (Get-Date).ToString("o")
    decision = $decision
    processes = @($commandLineProcesses + $statusBoundProcesses)
    status_bound_processes = $statusBoundProcesses
    router = [ordered]@{
        host = $RouterHost
        ping = $routerPing
        tcp22 = $routerTcp22
    }
    uart_triage = $uartTriage
    f93_f95_chain = $f93F95Chain
    f83 = [ordered]@{
        dir = if ($latestF83Dir) { $latestF83Dir.FullName } else { "" }
        status = $f83Status
        watcher_alive = $f83Alive
        stale_running = [bool]($f83Status -and [string]$f83Status.state -in @("running_foreground", "background_armed") -and -not $f83Alive)
        stdout = Get-FileProbe $f83StdoutPath
        uart_log = $f83UartProbe
        uart_rx_zero_observed = $f83UartRxZeroObserved
        uart_rx_zero_terminal_marker = $f83UartRxZeroMarker
        uart_rx_zero_long = $f83UartRxZeroLong
        blind_space_count = $f83BlindSpaceCount
        started_seconds = $f83StartedSeconds
    }
    f83_stage_monitor = [ordered]@{
        dir = if ($latestF83MonitorDir) { $latestF83MonitorDir.FullName } else { "" }
        status = $f83MonitorStatus
    }
    f83_auto_arm = [ordered]@{
        dir = if ($latestF83AutoArmDir) { $latestF83AutoArmDir.FullName } else { "" }
        status = $f83AutoArmStatus
    }
    f78 = [ordered]@{
        dir = if ($latestF78Dir) { $latestF78Dir.FullName } else { "" }
        status = $f78Status
        watcher_alive = $f78Alive
        stale_running = [bool]($f78Status -and [string]$f78Status.state -in @("running_foreground", "background_armed") -and -not $f78Alive)
        stdout = Get-FileProbe $f78StdoutPath
        uart_log = $f78UartProbe
        uart_rx_zero_observed = $f78UartRxZeroObserved
        uart_rx_zero_terminal_marker = $f78UartRxZeroMarker
        uart_rx_zero_long = $f78UartRxZeroLong
        blind_space_count = $f78BlindSpaceCount
        started_seconds = $f78StartedSeconds
    }
    f78_stage_monitor = [ordered]@{
        dir = if ($latestF78MonitorDir) { $latestF78MonitorDir.FullName } else { "" }
        status = $f78MonitorStatus
    }
    f77 = [ordered]@{
        dir = if ($latestF77Dir) { $latestF77Dir.FullName } else { "" }
        status = $f77Status
        watcher_alive = $f77Alive
        stale_running = [bool]($f77Status -and [string]$f77Status.state -in @("running_foreground", "background_armed") -and -not $f77Alive)
        stdout = Get-FileProbe $f77StdoutPath
        uart_log = $f77UartProbe
        uart_rx_zero_observed = $f77UartRxZeroObserved
        uart_rx_zero_terminal_marker = $f77UartRxZeroMarker
        uart_rx_zero_long = $f77UartRxZeroLong
        blind_space_count = $f77BlindSpaceCount
        started_seconds = $f77StartedSeconds
    }
    f77_stage_monitor = [ordered]@{
        dir = if ($latestF77MonitorDir) { $latestF77MonitorDir.FullName } else { "" }
        status = $f77MonitorStatus
    }
    f76 = [ordered]@{
        dir = if ($latestF76Dir) { $latestF76Dir.FullName } else { "" }
        status = $f76Status
        watcher_alive = $f76Alive
        stale_running = [bool]($f76Status -and [string]$f76Status.state -in @("running_foreground", "background_armed") -and -not $f76Alive)
        stdout = Get-FileProbe $f76StdoutPath
        uart_log = $f76UartProbe
        uart_rx_zero_observed = $f76UartRxZeroObserved
        uart_rx_zero_terminal_marker = $f76UartRxZeroMarker
        uart_rx_zero_long = $f76UartRxZeroLong
        blind_space_count = $f76BlindSpaceCount
        started_seconds = $f76StartedSeconds
    }
    f76_stage_monitor = [ordered]@{
        dir = if ($latestF76MonitorDir) { $latestF76MonitorDir.FullName } else { "" }
        status = $f76MonitorStatus
    }
    f75 = [ordered]@{
        dir = if ($latestF75Dir) { $latestF75Dir.FullName } else { "" }
        status = $f75Status
        watcher_alive = $f75Alive
        stale_running = [bool]($f75Status -and [string]$f75Status.state -in @("running_foreground", "background_armed") -and -not $f75Alive)
    }
    supervisor = [ordered]@{
        dir = if ($latestSupervisorDir) { $latestSupervisorDir.FullName } else { "" }
        status = $supervisorStatus
        rx_logs = [ordered]@{
            uart_log = Get-FileProbe (Join-Path $supervisorRxDir "uart.log")
            uart_raw_bin = Get-FileProbe (Join-Path $supervisorRxDir "uart.raw.bin")
        }
    }
    f66 = [ordered]@{
        dir = if ($latestF66Dir) { $latestF66Dir.FullName } else { "" }
        status = $f66Status
        watcher_alive = $f66Alive
        stale_attempt_running = [bool]($f66Status -and [string]$f66Status.state -eq "attempt_running" -and -not $f66Alive)
    }
    f66_2g_monitor = [ordered]@{
        dir = if ($latestF66MonitorDir) { $latestF66MonitorDir.FullName } else { "" }
        status = $f66MonitorStatus
    }
    router_ssh_monitor = [ordered]@{
        dir = if ($latestRouterSshMonitorDir) { $latestRouterSshMonitorDir.FullName } else { "" }
        status = $routerSshMonitorStatus
    }
    f125 = [ordered]@{
        dir = if ($latestF125Dir) { $latestF125Dir.FullName } else { "" }
        status = $f125Status
        watcher_alive = $f125Alive
        stale_attempt_running = [bool]($f125Status -and [string]$f125Status.state -eq "armed_waiting_bootbase" -and -not $f125Alive)
        stdout = Get-FileProbe $f125StdoutPath
        uart_log = $f125UartProbe
        uart_rx_zero_observed = $f125UartRxZeroObserved
        uart_rx_zero_terminal_marker = $f125UartRxZeroMarker
        uart_rx_zero_long = $f125UartRxZeroLong
        blind_space_count = $f125BlindSpaceCount
        started_seconds = $f125StartedSeconds
    }
    f125_5g_assoc_monitor = [ordered]@{
        dir = if ($latestF125MonitorDir) { $latestF125MonitorDir.FullName } else { "" }
        status = $f125MonitorStatus
        monitor_alive = $f125MonitorAlive
    }
    f126 = [ordered]@{
        dir = if ($latestF126Dir) { $latestF126Dir.FullName } else { "" }
        status = $f126Status
        watcher_alive = $f126Alive
        stale_attempt_running = [bool]($f126Status -and [string]$f126Status.state -eq "armed_waiting_bootbase" -and -not $f126Alive)
        stdout = Get-FileProbe $f126StdoutPath
        uart_log = $f126UartProbe
        uart_rx_zero_observed = $f126UartRxZeroObserved
        uart_rx_zero_terminal_marker = $f126UartRxZeroMarker
        uart_rx_zero_long = $f126UartRxZeroLong
        blind_space_count = $f126BlindSpaceCount
        started_seconds = $f126StartedSeconds
    }
    f126_5g_assoc_monitor = [ordered]@{
        dir = if ($latestF126MonitorDir) { $latestF126MonitorDir.FullName } else { "" }
        status = $f126MonitorStatus
        monitor_alive = $f126MonitorAlive
    }
    f65 = [ordered]@{
        dir = if ($latestF65Dir) { $latestF65Dir.FullName } else { "" }
        status = $f65Status
        watcher_alive = $f65Alive
        stale_attempt_running = [bool]($f65Status -and [string]$f65Status.state -eq "attempt_running" -and -not $f65Alive)
    }
    aelita = $aelita
    artifacts = [ordered]@{
        f66_candidate = "work\mission-state\q3-persistent-composite-f66-2g-queue-guard\build\openmitrastar-linux510-q3-persistent-f66-2g-autorate-reclaim-LZMA-OFFLINE-NO-FLASH.webformat.bin"
        f66_sha256 = "021cd4896ee54db95addd3b3c4111eb811b2dcf77a69c87b28b94dd4bec4b341"
        f66_current_live_crc32 = "26523198"
        f66_qguard_live_crc32 = "9f2a3ac5"
        f66_previous_live_crc32 = "faee4019"
        f64_current_live_crc32 = "b05e9b7b"
        f65_full_slot_crc32 = "aba558f3"
        f75_candidate = "work\mission-state\q3-persistent-composite-f75-2g-stable-5g-manual\build\openmitrastar-linux510-q3-persistent-f75-2g-stable-5g-manual-LZMA-OFFLINE-NO-FLASH.webformat.bin"
        f75_sha256 = "97929ccad0cab1471050d3a5088f1df490dbfb397b8e1261bf5677905d03ec97"
        f76_candidate = "work\mission-state\q3-persistent-composite-f76-2g-stable-5g-control-stage-guard\build\openmitrastar-linux510-q3-persistent-f76-2g-stable-5g-control-stage-guard-LZMA-OFFLINE-NO-FLASH.webformat.bin"
        f76_sha256 = "50d24b19a0c9a4195119062dd2a347a9bbabb5e8d6a468f28f56643d7e5d8210"
        f77_candidate = "work\mission-state\q3-persistent-composite-f77-2g-mcs7-noguard-5g-stage-guard\build\openmitrastar-linux510-q3-persistent-f77-2g-mcs7-noguard-5g-stage-guard-LZMA-OFFLINE-NO-FLASH.webformat.bin"
        f77_sha256 = "05ea7bae9de4796134fa490a3403bec8a41ec637b6434542f701c11b3ab3f83b"
        f78_candidate = "work\mission-state\q3-persistent-composite-f78-2g-fast-5g-modules-precontrol-stage-guard\build\openmitrastar-linux510-q3-persistent-f78-2g-fast-5g-modules-precontrol-stage-guard-LZMA-OFFLINE-NO-FLASH.webformat.bin"
        f78_sha256 = "8e0ca67908d365ebfd3ce4edec27b4cd95d293e68585580d141a80eb415c2b14"
        f83_candidate = "work\mission-state\q3-persistent-composite-f83-5g-post-hostapd-stage-2g-mcs7\build\openmitrastar-linux510-q3-persistent-f83-5g-post-hostapd-stage-2g-mcs7-LZMA-OFFLINE-NO-FLASH.webformat.bin"
        f83_sha256 = "1e3af81904d1bd9e061bb401e9514078e8e329a645b566b5141246f6d1eb1379"
        f93_candidate = "work\mission-state\q3-persistent-composite-f93-2g-ht40sgi-hostapd-compat-fixedsize-after-f92\build\openmitrastar-linux510-q3-persistent-f93-2g-ht40sgi-hostapd-compat-fixedsize-after-f92-LZMA-OFFLINE-NO-FLASH.webformat.bin"
        f93_sha256 = "32a32959b65bf580865da57fa56fff67d6132a97ec084d7739479914f0e5e24d"
        f95_candidate = "work\mission-state\q3-persistent-composite-f95-2g-mcs15-ht40sgi-descfix-fixedsize-after-f93\build\openmitrastar-linux510-q3-persistent-f95-2g-mcs15-ht40sgi-descfix-fixedsize-after-f93-LZMA-OFFLINE-NO-FLASH.webformat.bin"
        f95_sha256 = "994df5e4a6fa2a80f68ea5443f3f980f4c6bf06a6aab07f187179f54b6b50973"
        f95_full_slot_crc32 = "418c9e28"
    }
}

$json = $payload | ConvertTo-Json -Depth 16
if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
    $resolvedOutput = [IO.Path]::GetFullPath($OutputPath)
    $parent = Split-Path -Parent $resolvedOutput
    if ($parent) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $json | Set-Content -Encoding ascii -LiteralPath $resolvedOutput
}
$json
