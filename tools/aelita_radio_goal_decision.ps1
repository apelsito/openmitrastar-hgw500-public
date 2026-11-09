[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Root = "",
    [string]$RouterHost = "192.168.1.90",
    [string]$BootbaseHost = "192.168.1.200",
    [string]$AelitaHost = "192.168.1.63"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not $Root) {
    $Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
} else {
    $Root = [IO.Path]::GetFullPath($Root)
}

function Read-JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try {
        return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-JsonProp($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $Default }
    return $prop.Value
}

function Test-Tcp22([string]$HostName) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, 22, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(700, $false)
        if (-not $ok) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-PingOnce([string]$HostName) {
    try {
        return [bool](Test-Connection -ComputerName $HostName -Count 1 -Quiet -ErrorAction SilentlyContinue)
    } catch {
        return $false
    }
}

function Get-ProcSummary([Nullable[int]]$PidValue) {
    if ($null -eq $PidValue -or $PidValue -le 0) { return $null }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$PidValue" -ErrorAction SilentlyContinue
    if (-not $proc) {
        return [ordered]@{ pid = $PidValue; alive = $false }
    }
    return [ordered]@{
        pid = [int]$proc.ProcessId
        parent_pid = [int]$proc.ParentProcessId
        alive = $true
        name = $proc.Name
        command_line = $proc.CommandLine
    }
}

function Get-FileSummary([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return [ordered]@{ path = $Path; exists = $false; bytes = 0 }
    }
    $item = Get-Item -LiteralPath $Path
    return [ordered]@{
        path = $item.FullName
        exists = $true
        bytes = [int64]$item.Length
        last_write_time = $item.LastWriteTime.ToString("o")
    }
}

function Get-LatestFile([string]$Pattern) {
    $files = @(Get-ChildItem -Path $Pattern -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
    if ($files.Count -eq 0) { return $null }
    return $files[0].FullName
}

function Get-LatestDirectory([string]$Pattern) {
    $dirs = @(Get-ChildItem -Path $Pattern -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
    if ($dirs.Count -eq 0) { return $null }
    return $dirs[0].FullName
}

function Get-MatchingProcessSummary([string]$Pattern) {
    @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match $Pattern } |
        ForEach-Object {
            [ordered]@{
                pid = [int]$_.ProcessId
                parent_pid = [int]$_.ParentProcessId
                alive = $true
                name = $_.Name
                command_line = $_.CommandLine
            }
        })
}

function Get-Artifacts([string]$BuildTag, [string]$BaseName) {
    $build = Join-Path $Root "work\mission-state\q3-persistent-composite-$BuildTag\build"
    $resultPath = Join-Path $build "build-result.json"
    $manifestPath = Join-Path $build "manifest.json"
    $webPath = Join-Path $build ($BaseName + ".webformat.bin")
    $result = Read-JsonFile $resultPath
    $manifest = Read-JsonFile $manifestPath
    return [ordered]@{
        build_dir = $build
        result_path = $resultPath
        manifest_path = $manifestPath
        webformat = Get-FileSummary $webPath
        build_status = if ($result) { $result.status } else { $null }
        bootbase_result = if ($result) { $result.bootbase_result } elseif ($manifest) { $manifest.bootbase_contract.result } else { $null }
        candidate_sha256 = if ($result) { $result.candidate_sha256 } else { $null }
        candidate_crc32 = if ($result) { $result.candidate_crc32 } else { $null }
        full_slot_crc32 = if ($result) { $result.full_slot_crc32 } else { $null }
        tftp_copy = if ($result) { $result.tftp_copy } else { $null }
    }
}

$f103WatchDir = Join-Path $Root "outputs\flash-watch\f103-emac-rxrestart-63pokes-watch-active"
$f103StatusPath = Join-Path $f103WatchDir "status.json"
$f103Status = Read-JsonFile $f103StatusPath
$f103StdoutProp = Get-JsonProp $f103Status "stdout" $null
$f103StderrProp = Get-JsonProp $f103Status "stderr" $null
$f103Stdout = if ($f103StdoutProp) { [string]$f103StdoutProp } else { Join-Path $f103WatchDir "attempt-01\stdout.log" }
$f103Stderr = if ($f103StderrProp) { [string]$f103StderrProp } else { Join-Path $f103WatchDir "attempt-01\stderr.log" }
$uartLog = Get-LatestFile (Join-Path $Root "outputs\uart-live\q3-f45-radio5-powerselect-nonfatal-openlab-autostart-autoboot-atgu-flash-*.log")
$passiveCaptureDir = Get-LatestDirectory (Join-Path $Root "outputs\uart-live\passive-after-watchstop-*")
$passiveCaptureStatusPath = if ($passiveCaptureDir) { Join-Path $passiveCaptureDir "capture-status.json" } else { "" }
$passiveCaptureStatus = Read-JsonFile $passiveCaptureStatusPath
$passiveCaptureLog = if ($passiveCaptureDir) { Join-Path $passiveCaptureDir "uart.log" } else { "" }
$passiveCaptureProcs = @(Get-MatchingProcessSummary "capture_topaz_uart_resilient\.ps1")

$stdoutText = if (Test-Path -LiteralPath $f103Stdout -PathType Leaf) {
    Get-Content -Raw -LiteralPath $f103Stdout
} else {
    ""
}
$stderrText = if (Test-Path -LiteralPath $f103Stderr -PathType Leaf) {
    Get-Content -Raw -LiteralPath $f103Stderr
} else {
    ""
}
$combined = $stdoutText + "`n" + $stderrText
$blindMatches = [regex]::Matches($combined, "OMQ3_F45_AUTOBREAK_BLIND_SPACE_SENT=(\d+)")
$blindSpaceCount = if ($blindMatches.Count -gt 0) { [int]$blindMatches[$blindMatches.Count - 1].Groups[1].Value } else { 0 }
$stuckBlindSpaceThreshold = 600

$f104DryStatusPath = Get-LatestFile (Join-Path $Root "outputs\flash-watch\f104-2g-be-guard16-*\status.json")
$f104DryStatus = Read-JsonFile $f104DryStatusPath

$com3 = Get-PnpDevice -Class Ports -ErrorAction SilentlyContinue |
    Where-Object { $_.FriendlyName -match "\(COM3\)" } |
    Select-Object -First 1

$f103Artifacts = Get-Artifacts `
    "f103-emac-rxrestart-63pokes-from-f101" `
    "openmitrastar-linux510-q3-persistent-f103-emac-rxrestart-63pokes-from-f101-LZMA-OFFLINE-NO-FLASH"
$f104Artifacts = Get-Artifacts `
    "f104-2g-be-guard16-from-f103" `
    "openmitrastar-linux510-q3-persistent-f104-2g-be-guard16-from-f103-LZMA-OFFLINE-NO-FLASH"

$routerTcp22 = Test-Tcp22 $RouterHost
$routerPing = Test-PingOnce $RouterHost
$bootbaseTcp22 = Test-Tcp22 $BootbaseHost
$aelitaTcp22 = Test-Tcp22 $AelitaHost

$watcherPidProp = Get-JsonProp $f103Status "watcher_pid" $null
$watcherPid = if ($watcherPidProp) { [int]$watcherPidProp } else { $null }
$childPid = $null
$childProc = Get-CimInstance Win32_Process -Filter "ParentProcessId=$watcherPid" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "q3_f45_radio5_powerselect" } |
    Select-Object -First 1
if ($childProc) { $childPid = [int]$childProc.ProcessId }

$uartSummary = Get-FileSummary $uartLog
$markers = [ordered]@{
    zhal_seen = $combined -match "ZHAL"
    topaz_ready = $combined -match "topaz>\s*$"
    flash_write = $combined -match "MTD4_FLASH_WRITE|flash write|erase"
    flash_pass = $combined -match "MTD4_FLASH_AND_READBACK_PASS"
    ssh_ready = $combined -match "SSH_READY|SSH_AUTH_PASS"
    blind_space_count = $blindSpaceCount
}

$decision = "UNKNOWN"
$nextAction = "inspect status manually"
$f103WatcherState = Get-JsonProp $f103Status "state" $null
$passiveReady = $false
$passiveRxOnly = $false
$passiveBytes = $null
if ($passiveCaptureStatus) {
    $passiveReady = [bool](Get-JsonProp $passiveCaptureStatus "ready" $false)
    $passiveRxOnly = [bool](Get-JsonProp $passiveCaptureStatus "rx_only" $false)
    $passiveBytes = Get-JsonProp $passiveCaptureStatus "bytes" $null
}

if ($passiveCaptureProcs.Count -gt 0 -and $passiveReady -and $passiveRxOnly -and -not $routerTcp22 -and -not $markers.flash_pass) {
    $decision = "PASSIVE_UART_CAPTURE_WAIT_POWER_CYCLE"
    $nextAction = "keep RX-only UART capture as COM3 owner; do not rearm blind autobreak; wait for physical power-cycle or router network recovery"
} elseif ($uartSummary.exists -and $uartSummary.bytes -eq 0 -and -not $markers.flash_pass -and -not $routerTcp22) {
    if ($f103WatcherState -eq "attempt_running") {
        if ($blindSpaceCount -ge $stuckBlindSpaceThreshold) {
            $decision = "F103_WATCHER_STUCK_UART_RX_ZERO_REOPEN"
            $nextAction = "restart F103 watcher with a fresh COM3 handle and finite no-RX abort; if zero RX repeats, fix router TX to FTDI RX/GND or physical power-cycle after wiring is correct"
        } else {
            $decision = "WAITING_FOR_UART_RX"
            $nextAction = "keep F103 watcher as sole COM3 owner; fix router TX to FTDI RX/GND or physical power-cycle after wiring is correct"
        }
    } else {
        $decision = "F103_WATCHER_EXPIRED_UART_RX_ZERO"
        $nextAction = "rearm one short F103 no-RX probe, then keep waiting for physical UART RX or router power-cycle before any flash"
    }
} elseif ($markers.flash_pass) {
    $decision = "F103_FLASHED_VERIFY_2G"
    $nextAction = "run SSH proof and AELITA 2.4 speed gate; compare against F101 baseline"
} elseif ($markers.zhal_seen -or $markers.topaz_ready -or $markers.flash_write) {
    $decision = "F103_FLASH_IN_PROGRESS_OR_BOOTBASE_CAPTURED"
    $nextAction = "do not open COM3; wait for flash/readback/boot markers"
} elseif ($routerTcp22) {
    $decision = "ROUTER_SSH_AVAILABLE"
    $nextAction = "run SSH proof before any further flash"
} elseif ($f104DryStatus -and $f104DryStatus.state -eq "dry_run_pass") {
    $decision = "F104_READY_AFTER_F103"
    $nextAction = "after F103 measurement, use arm_f104_2g_be_guard16_flash.ps1 -Execute only if F103 fails speed/stability"
}

$payload = [ordered]@{
    schema = "openmitrastar.radio-goal-decision/v1"
    checked_at = (Get-Date).ToString("o")
    decision = $decision
    next_action = $nextAction
    constraints = [ordered]@{
        com3_owner_should_remain_f103 = ($decision -eq "WAITING_FOR_UART_RX" -or $decision -eq "F103_FLASH_IN_PROGRESS_OR_BOOTBASE_CAPTURED")
        rearm_f103_allowed = ($decision -eq "F103_WATCHER_EXPIRED_UART_RX_ZERO" -or $decision -eq "F103_WATCHER_STUCK_UART_RX_ZERO_REOPEN")
        flash_target = "mtd4/linux_live"
        forbidden_targets = @("mtd0/uboot", "mtd1/uboot_env", "mtd2/uboot_env_bak", "mtd3/linux_safety", "mtd5/data", "mtd6/rootfs_live-logical")
        no_ram_writes = $true
    }
    network = [ordered]@{
        router = [ordered]@{ host = $RouterHost; ping = $routerPing; tcp22 = $routerTcp22 }
        bootbase = [ordered]@{ host = $BootbaseHost; tcp22 = $bootbaseTcp22 }
        aelita = [ordered]@{ host = $AelitaHost; tcp22 = $aelitaTcp22 }
    }
    serial = [ordered]@{
        com3 = if ($com3) {
            [ordered]@{ present = $true; status = $com3.Status; friendly_name = $com3.FriendlyName; instance_id = $com3.InstanceId }
        } else {
            [ordered]@{ present = $false }
        }
        uart_log = $uartSummary
        passive_capture = [ordered]@{
            dir = $passiveCaptureDir
            status_path = $passiveCaptureStatusPath
            log = Get-FileSummary $passiveCaptureLog
            ready = $passiveReady
            rx_only = $passiveRxOnly
            bytes = $passiveBytes
            processes = $passiveCaptureProcs
        }
        markers = $markers
    }
    f103 = [ordered]@{
        watcher_status = $f103StatusPath
        watcher_state = $f103WatcherState
        expected_after_flash_full_slot_crc32 = "50cfcf29"
        watcher = Get-ProcSummary $watcherPid
        child = Get-ProcSummary $childPid
        stdout = Get-FileSummary $f103Stdout
        stderr = Get-FileSummary $f103Stderr
        artifacts = $f103Artifacts
    }
    f104 = [ordered]@{
        dry_run_status = $f104DryStatusPath
        dry_run_state = Get-JsonProp $f104DryStatus "state" $null
        dry_run_current_live_crc32 = Get-JsonProp $f104DryStatus "current_live_crc32" $null
        expected_after_flash_full_slot_crc32 = "722f542f"
        arm_script = Join-Path $Root "tools\arm_f104_2g_be_guard16_flash.ps1"
        artifacts = $f104Artifacts
    }
    five_ghz = [ordered]@{
        current_plan = "after 2.4 F103/F104 gate, use F88/RC1 isolated L3; do not bridge wifi0 into br0 until isolated client L3 passes"
    }
}

$payload | ConvertTo-Json -Depth 12
