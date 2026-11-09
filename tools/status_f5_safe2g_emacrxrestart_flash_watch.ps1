[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RunDir = "",
    [int[]]$KnownPids = @(24976, 4136, 18572),
    [int]$TailLines = 80
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $RunDir) {
    $latest = Get-ChildItem -LiteralPath (Join-Path $Root "outputs\flash-watch") -Directory |
        Where-Object { $_.Name -like "f5-safe2g-emacrxrestart-*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $latest) {
        throw "No f5-safe2g-emacrxrestart flash-watch directory found"
    }
    $RunDir = $latest.FullName
}

$RunDir = [IO.Path]::GetFullPath($RunDir)
$statusPath = Join-Path $RunDir "status.json"
$logPath = Join-Path $RunDir "watch.log"

if (-not (Test-Path -LiteralPath $logPath -PathType Leaf)) {
    throw "watch.log not found: $logPath"
}

$status = $null
if (Test-Path -LiteralPath $statusPath -PathType Leaf) {
    $status = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
}

$processRows = @{}
foreach ($knownPid in $KnownPids) {
    $proc = Get-Process -Id $knownPid -ErrorAction SilentlyContinue
    if ($proc) {
        $processRows[$proc.Id] = [ordered]@{
            pid = $proc.Id
            parent_pid = $null
            name = $proc.ProcessName
            start_time = $proc.StartTime.ToString("o")
            responding = [bool]$proc.Responding
            matched_by = "known-pid"
        }
    }
}

$cmdProcesses = Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -like "*watch_flash_f5_safe2g_emacrxrestart_until_bootbase.ps1*" -or
            $_.CommandLine -like "*flash_openmitrastar_f5_safe2g_emacrxrestart_auto.ps1*" -or
            $_.CommandLine -like "*f5_safe2g_emacrxrestart_autoboot_atgu_flash.ps1*" -or
            $_.CommandLine -like "*watch_f5_emacrxrestart_postflash_gate.ps1*"
        )
    }
foreach ($proc in $cmdProcesses) {
    if (-not $processRows.ContainsKey([int]$proc.ProcessId)) {
        $processRows[[int]$proc.ProcessId] = [ordered]@{
            pid = [int]$proc.ProcessId
            parent_pid = [int]$proc.ParentProcessId
            name = $proc.Name
            start_time = $null
            responding = $null
            matched_by = "command-line"
        }
    } elseif ($null -eq $processRows[[int]$proc.ProcessId].parent_pid) {
        $processRows[[int]$proc.ProcessId].parent_pid = [int]$proc.ParentProcessId
    }
}
$processes = @($processRows.Values | Sort-Object { $_.pid })

$tailLinesText = @(Get-Content -LiteralPath $logPath -Tail $TailLines)
$tail = $tailLinesText -join "`n"

$markers = [ordered]@{
    bootbase_seen = [bool]($tail -match "(?m)(^Bootbase\b|^ZHAL>|^topaz>|Hit any key to (stop autoboot|exit))")
    topaz_ready = [bool]($tail -match "OMF5_AUTOBREAK_TOPAZ_READY")
    flash_marker_seen = [bool]($tail -match "OMF5_FLASH_MARKER|spi_flash erase|spi_flash write")
    flash_pass = [bool]($tail -match "OMF5_AUTONOMOUS_MTD4_FLASH_AND_READBACK_PASS=1")
    timeout = [bool]($tail -match "Timed out waiting|WATCH_ATTEMPT_END")
    emac_old_freeze = [bool]($tail -match "rx_cons=119 rx_prod=119 tx_head=38 tx_tail=38")
}

$classification = "UNKNOWN"
if ($markers.flash_pass) {
    $classification = "FLASH_PASS"
} elseif ($markers.flash_marker_seen) {
    $classification = "FLASH_IN_PROGRESS_OR_FAILED_AFTER_BOOTBASE"
} elseif ($markers.topaz_ready -or $markers.bootbase_seen) {
    $classification = "BOOTBASE_CAPTURED_WAITING_FLASH"
} elseif ($markers.emac_old_freeze) {
    $classification = "WAITING_PHYSICAL_POWER_CYCLE_OLD_EMAC_FREEZE"
} elseif ($processes.Count -gt 0) {
    $classification = "WATCHER_RUNNING_NO_BOOTBASE_YET"
} else {
    $classification = "WATCHER_NOT_RUNNING"
}

[ordered]@{
    schema = "openmitrastar.f5-safe2g-emacrxrestart.flash-watch-status/v1"
    checked_at = (Get-Date).ToString("o")
    run_dir = $RunDir
    status = $status
    watcher_processes = $processes
    log = [ordered]@{
        path = $logPath
        bytes = (Get-Item -LiteralPath $logPath).Length
        last_write_time = (Get-Item -LiteralPath $logPath).LastWriteTime.ToString("o")
    }
    markers = $markers
    classification = $classification
    next_action = if ($classification -eq "WAITING_PHYSICAL_POWER_CYCLE_OLD_EMAC_FREEZE") {
        "power-cycle AELITA while this watcher remains running; do not start another COM3 owner"
    } elseif ($classification -eq "FLASH_PASS") {
        "run tools\\post_flash_f5_radio_gate.ps1 -HostAddress 192.168.1.90 -Run2gProbe"
    } else {
        "inspect watch.log tail and avoid duplicate COM3 ownership"
    }
    tail = $tailLinesText
} | ConvertTo-Json -Depth 8
