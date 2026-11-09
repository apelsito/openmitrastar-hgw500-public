[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RunDir = "",
    [int]$TailLines = 80
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $RunDir) {
    $latest = Get-ChildItem -LiteralPath (Join-Path $Root "outputs\flash-watch") -Directory -Filter "f65-isolated-5g-*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latest) { $RunDir = $latest.FullName }
}

if (-not $RunDir -or -not (Test-Path -LiteralPath $RunDir -PathType Container)) {
    [ordered]@{
        schema = "openmitrastar.f65-flash-watch-report/v1"
        classification = "WATCHER_NOT_RUNNING"
        run_dir = $null
        status = $null
        watcher_processes = @()
        markers = [ordered]@{}
        log = $null
    } | ConvertTo-Json -Depth 8
    exit 0
}

$statusPath = Join-Path $RunDir "status.json"
$logPath = Join-Path $RunDir "watch.log"
$statusRaw = if (Test-Path -LiteralPath $statusPath -PathType Leaf) {
    Get-Content -LiteralPath $statusPath -Raw
} else {
    ""
}
$status = if ($statusRaw) { $statusRaw | ConvertFrom-Json } else { $null }
function Get-LogTailLines([string]$Path, [int]$Count) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return @() }
    $raw = Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue
    if (-not $raw) { return @() }
    $lines = @($raw -split "`r?`n" | Where-Object { $_ -ne "" })
    if ($lines.Count -le $Count) { return $lines }
    return @($lines | Select-Object -Last $Count)
}

$tailList = [System.Collections.Generic.List[string]]::new()
foreach ($line in (Get-LogTailLines $logPath $TailLines)) {
    [void]$tailList.Add([string]$line)
}

$attemptLogs = @(Get-ChildItem -LiteralPath $RunDir -Filter "attempt-*.stdout.log" -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1)
if ($attemptLogs.Count -gt 0) {
    $attemptTail = @(Get-LogTailLines $attemptLogs[0].FullName $TailLines)
    if ($attemptTail.Count -gt 0) {
        [void]$tailList.Add("---- live attempt stdout: $($attemptLogs[0].Name) ----")
        foreach ($line in $attemptTail) {
            [void]$tailList.Add([string]$line)
        }
    }
}

$uartLogs = @(Get-ChildItem -LiteralPath (Join-Path $Root "outputs\uart-live") -Filter "q3-f45-radio5-powerselect-nonfatal-openlab-autostart-autoboot-atgu-flash-*.log" -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1)
if ($uartLogs.Count -gt 0 -and $uartLogs[0].Length -gt 0) {
    $uartTail = @(Get-LogTailLines $uartLogs[0].FullName $TailLines)
    if ($uartTail.Count -gt 0) {
        [void]$tailList.Add("---- live uart: $($uartLogs[0].Name) ----")
        foreach ($line in $uartTail) {
            [void]$tailList.Add([string]$line)
        }
    }
}

$tail = @($tailList)
$text = $tail -join "`n"

$watcherAlive = $false
$watcherPid = $null
if ($status -and $status.PSObject.Properties.Name -contains "watcher_pid") {
    $watcherPid = [int]$status.watcher_pid
    $watcherAlive = [bool](Get-Process -Id $watcherPid -ErrorAction SilentlyContinue)
}

$markers = [ordered]@{
    bootbase_seen = [bool]($text -match "Bootbase|ZHAL>|Hit any key")
    topaz_ready = [bool]($text -match "TOPAZ_READY=1")
    atgu_sent = [bool]($text -match "ATGU_SENT")
    space_sent = [bool]($text -match "SPACE_SENT")
    tftp_seen = [bool]($text -match "tftpboot|Bytes transferred")
    erase_seen = [bool]($text -match "spi_flash erase")
    write_seen = [bool]($text -match "spi_flash write")
    readback_pass = [bool]($text -match "MTD4_BOOTBASE_READBACK_PASS")
    linux_seen = [bool]($text -match "Linux version 5\.10\.260-openmitrastar-radiohw")
    ssh_pass = [bool]($text -match "FLASH_BOOT_SSH_PASS|OMSSH_READY")
    flash_pass = [bool]($text -match "MTD4_FLASH_AND_READBACK_PASS")
    timeout = [bool]($text -match "Timed out waiting for topaz|timeout")
}

$classification = if ($markers.flash_pass) {
    "FLASH_PASS"
} elseif ($markers.write_seen -or $markers.erase_seen -or $markers.tftp_seen) {
    "FLASH_IN_PROGRESS_OR_FAILED_AFTER_BOOTBASE"
} elseif ($markers.topaz_ready) {
    "BOOTBASE_CAPTURED_WAITING_FLASH"
} elseif ($markers.bootbase_seen) {
    "BOOTBASE_SEEN_WAITING_TOPAZ"
} elseif ($watcherAlive) {
    "WATCHER_RUNNING_NO_BOOTBASE_YET"
} else {
    "WATCHER_NOT_RUNNING"
}

$statusState = $null
$statusAttempt = $null
$statusAttempts = $null
$statusExitCode = $null
$statusMessage = $null
$statusUpdatedAt = $null
if ($status) {
    if ($status.PSObject.Properties.Name -contains "state") { $statusState = [string]$status.state }
    if ($status.PSObject.Properties.Name -contains "attempt") { $statusAttempt = [int]$status.attempt }
    if ($status.PSObject.Properties.Name -contains "attempts") { $statusAttempts = [int]$status.attempts }
    if ($status.PSObject.Properties.Name -contains "exit_code") { $statusExitCode = [int]$status.exit_code }
    if ($status.PSObject.Properties.Name -contains "message") { $statusMessage = [string]$status.message }
    if ($status.PSObject.Properties.Name -contains "updated_at") { $statusUpdatedAt = [string]$status.updated_at }
}

function Get-FileSummary([AllowNull()][IO.FileInfo]$File) {
    if ($null -eq $File) { return $null }
    return [ordered]@{
        path = $File.FullName
        name = $File.Name
        bytes = [int64]$File.Length
        last_write = $File.LastWriteTime.ToString("o")
    }
}

$latestAttemptLog = if ($attemptLogs.Count -gt 0) { $attemptLogs[0] } else { $null }
$latestUartLog = if ($uartLogs.Count -gt 0) { $uartLogs[0] } else { $null }
$uartRxBytes = if ($latestUartLog) { [int64]$latestUartLog.Length } else { $null }
$attemptStdoutBytes = if ($latestAttemptLog) { [int64]$latestAttemptLog.Length } else { $null }
$uartRxState = if (-not $latestUartLog) {
    "no_uart_log"
} elseif ($latestUartLog.Length -eq 0) {
    "silent_zero_bytes"
} else {
    "rx_bytes_present"
}

$serialPorts = @(Get-PnpDevice -Class Ports -ErrorAction SilentlyContinue | ForEach-Object {
    [ordered]@{
        status = [string]$_.Status
        friendly_name = [string]$_.FriendlyName
        instance_id = [string]$_.InstanceId
    }
})

$nextAction = if ($markers.flash_pass) {
    "run_post_flash_radio_gate"
} elseif ($markers.topaz_ready) {
    "flash_runner_should_continue_from_topaz"
} elseif ($markers.bootbase_seen) {
    "wait_for_or_send_atgu_space_sequence"
} elseif ($watcherAlive -and $uartRxState -eq "silent_zero_bytes") {
    "uart_tx_active_but_rx_silent_check_router_power_reset_ttl_rx_wire_or_com_mapping"
} elseif ($watcherAlive) {
    "wait_for_bootbase_or_power_cycle"
} else {
    "restart_flash_watcher_after_confirming_single_com_owner"
}

$report = [ordered]@{
    schema = "openmitrastar.f65-flash-watch-report/v1"
    checked_at = (Get-Date).ToString("o")
    classification = $classification
    next_action = $nextAction
    run_dir = [IO.Path]::GetFullPath($RunDir)
    status = [ordered]@{
        state = $statusState
        attempt = $statusAttempt
        attempts = $statusAttempts
        exit_code = $statusExitCode
        message = $statusMessage
        updated_at = $statusUpdatedAt
    }
    watcher = [ordered]@{
        pid = $watcherPid
        alive = $watcherAlive
    }
    serial = [ordered]@{
        requested_port = if ($status -and $status.PSObject.Properties.Name -contains "port") { [string]$status.port } else { $null }
        ports = $serialPorts
    }
    diagnostics = [ordered]@{
        uart_rx_state = $uartRxState
        uart_rx_bytes = $uartRxBytes
        attempt_stdout_bytes = $attemptStdoutBytes
        latest_attempt_stdout = (Get-FileSummary $latestAttemptLog)
        latest_uart_log = (Get-FileSummary $latestUartLog)
    }
    markers = $markers
    log = [ordered]@{
        path = $logPath
        tail = @($tail)
    }
}

$report | ConvertTo-Json -Depth 12
