[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [string]$AelitaHost = "192.168.1.63",
    [string]$AelitaUser = "AELITA",
    [ValidateRange(60, 86400)]
    [int]$WaitSeconds = 21600,
    [ValidateRange(5, 300)]
    [int]$PollSeconds = 30,
    [string]$CurrentLiveCrc32 = "20e93d1b",
    [double]$Min2gMbps = 5.0,
    [double]$Diag2gMbps = 20.0,
    [string]$Ack = "OPENMITRASTAR_Q3_F83_5G_POST_HOSTAPD_STAGE_2G_MCS7_MTD4_FLASH_1E3AF819",
    [switch]$Run2gProbe,
    [switch]$Run5gProbe,
    [switch]$DryRun,
    [switch]$Once,
    [ValidateSet("txpath", "v6scheduler")]
    [string]$FiveGProfile = "txpath",
    [ValidateRange(60, 900)]
    [int]$FiveGSeconds = 120,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$RequiredAck = "OPENMITRASTAR_Q3_F83_5G_POST_HOSTAPD_STAGE_2G_MCS7_MTD4_FLASH_1E3AF819"
if ($Ack -ne $RequiredAck) {
    throw "Exact acknowledgement required: $RequiredAck"
}
if ($CurrentLiveCrc32 -notmatch '^[0-9a-fA-F]{8}$') {
    throw "CurrentLiveCrc32 must be 8 hex characters"
}
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\aelita-radio-goal-watchdog-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$statusPath = Join-Path $OutputDir "watchdog-status.json"
$logPath = Join-Path $OutputDir "watchdog.log"
$statusSnapshotPath = Join-Path $OutputDir "latest-radio-status.json"
$networkSnapshotPath = Join-Path $OutputDir "latest-network-discovery.json"
$globalStatusSnapshotPath = Join-Path $Root "outputs\postflash\aelita-radio-goal-status-latest.json"

function Write-WatchdogStatus([string]$State, [string]$Message, [object]$Actions = @()) {
    [ordered]@{
        schema = "openmitrastar.aelita-radio-goal-watchdog/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        port = $Port
        host = $HostAddress
        aelita_host = $AelitaHost
        current_live_crc32 = $CurrentLiveCrc32
        min_2g_mbps = $Min2gMbps
        diag_2g_mbps = $Diag2gMbps
        run_2g_probe = [bool]$Run2gProbe
        run_5g_probe = [bool]$Run5gProbe
        dry_run = [bool]$DryRun
        once = [bool]$Once
        five_g_profile = $FiveGProfile
        five_g_seconds = $FiveGSeconds
        actions = $Actions
    } | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $statusPath
}

function Get-WorkspaceProcesses([string]$Needle) {
    @(Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $cmd = [string]$_.CommandLine
            $cmd -like "*MitraStar*" -and $cmd -like "*$Needle*"
        } |
        Select-Object ProcessId, CommandLine)
}

function Read-JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try {
        return (Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Get-ActiveFlashOwnerFromStatus {
    $status = Read-JsonFile $globalStatusSnapshotPath
    if (-not $status) { return $null }

    foreach ($name in @("f83", "f78", "f77", "f76")) {
        $entry = $status.$name
        if (-not $entry -or -not $entry.status) { continue }
        $state = [string]$entry.status.state
        if ($state -notin @("running_foreground", "background_armed")) { continue }
        if (-not [bool]$entry.watcher_alive) { continue }

        $pidValue = $null
        if ($entry.status.PSObject.Properties.Name -contains "process_id") {
            $pidValue = $entry.status.process_id
        } elseif ($entry.status.PSObject.Properties.Name -contains "current_process_id") {
            $pidValue = $entry.status.current_process_id
        }
        $decision = if ($status.PSObject.Properties.Name -contains "decision") { [string]$status.decision } else { "" }
        return [ordered]@{
            component = "uart_supervisor"
            state = "blocked_by_active_$($name)_flash"
            pid = if ($pidValue -ne $null) { [int]$pidValue } else { $null }
            active_flash = $name
            decision = $decision
            reason = "COM3 is already owned by active $name flash watcher"
        }
    }
    return $null
}

function Start-HiddenPowerShell([string[]]$ArgumentList) {
    if ($DryRun) {
        return [pscustomobject]@{ Id = -1; DryRun = $true; Arguments = ($ArgumentList -join " ") }
    }
    Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList $ArgumentList -PassThru
}

function Ensure-F83AutoArm {
    $activeFlashOwner = Get-ActiveFlashOwnerFromStatus
    if ($activeFlashOwner) {
        return $activeFlashOwner
    }

    $existing = @(Get-WorkspaceProcesses "arm_f83_flash_then_stage_gate.ps1")
    if ($existing.Count -gt 0) {
        return [ordered]@{ component = "f83_auto_arm"; state = "already_running"; pid = [int]$existing[0].ProcessId }
    }
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $out = Join-Path $Root "outputs\postflash\f83-auto-arm-watchdog-$stamp"
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "arm_f83_flash_then_stage_gate.ps1"),
        "-Port", $Port,
        "-ServerIp", $ServerIp,
        "-ClientIp", $ClientIp,
        "-HostAddress", $HostAddress,
        "-OutputDir", $out,
        "-NoRxAbortSeconds", "900",
        "-FlashTimeoutSeconds", "900",
        "-MonitorTimeoutSeconds", "$WaitSeconds",
        "-Min2gMbps", "$Min2gMbps",
        "-Diag2gMbps", "$Diag2gMbps",
        "-Ack", $RequiredAck
    )
    if (-not $DryRun) { $args += "-Execute" }
    $proc = Start-HiddenPowerShell $args
    $state = if ($DryRun) { "would_start" } else { "started" }
    return [ordered]@{ component = "f83_auto_arm"; state = $state; pid = [int]$proc.Id; output_dir = $out }
}

function Ensure-RouterSshMonitor {
    $existing = @(Get-WorkspaceProcesses "monitor_router_ssh_then_radio_gate.ps1")
    if ($existing.Count -gt 0) {
        return [ordered]@{ component = "router_ssh_monitor"; state = "already_running"; pid = [int]$existing[0].ProcessId }
    }
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $out = Join-Path $Root "outputs\postflash\router-ssh-radio-monitor-watchdog-$stamp"
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "monitor_router_ssh_then_radio_gate.ps1"),
        "-TimeoutSeconds", "$WaitSeconds",
        "-PollSeconds", "10",
        "-OutputDir", $out,
        "-HostAddress", $HostAddress,
        "-OracleHost", $AelitaHost,
        "-OracleUser", $AelitaUser,
        "-Min2gMbps", "$Min2gMbps",
        "-Diag2gMbps", "$Diag2gMbps",
        "-FiveGProfile", $FiveGProfile,
        "-FiveGSeconds", "$FiveGSeconds"
    )
    if ($Run2gProbe) { $args += "-Run2gProbe" }
    if ($Run5gProbe) { $args += "-Run5gProbe" }
    $proc = Start-HiddenPowerShell $args
    $state = if ($DryRun) { "would_start" } else { "started" }
    return [ordered]@{ component = "router_ssh_monitor"; state = $state; pid = [int]$proc.Id; output_dir = $out }
}

function Update-Snapshots {
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "status_aelita_radio_goal.ps1") `
            -RouterHost $HostAddress `
            -AelitaHost $AelitaHost `
            -AelitaUser $AelitaUser `
            -SkipAelita `
            -OutputPath $globalStatusSnapshotPath |
            Set-Content -Encoding ascii -LiteralPath $statusSnapshotPath
    } catch {
        "STATUS_SNAPSHOT_ERROR $($_.Exception.Message)" | Add-Content -Encoding ascii -LiteralPath $logPath
    }
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "discover_openmitrastar_network.ps1") `
            -RouterHost $HostAddress |
            Set-Content -Encoding ascii -LiteralPath $networkSnapshotPath
    } catch {
        "NETWORK_SNAPSHOT_ERROR $($_.Exception.Message)" | Add-Content -Encoding ascii -LiteralPath $logPath
    }
}

"AELITA_RADIO_WATCHDOG_START at=$(Get-Date -Format o) out=$OutputDir" |
    Add-Content -Encoding ascii -LiteralPath $logPath
Write-WatchdogStatus "starting" "watchdog starting"

$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $deadline) {
    Update-Snapshots
    $actions = @(
        Ensure-F83AutoArm
        Ensure-RouterSshMonitor
    )
    $summary = ($actions | ForEach-Object { "$($_.component):$($_.state):$($_.pid)" }) -join ","
    "AELITA_RADIO_WATCHDOG_POLL at=$(Get-Date -Format o) $summary" |
        Add-Content -Encoding ascii -LiteralPath $logPath
    Write-WatchdogStatus "watching" "watchers ensured" $actions
    if ($Once) {
        Write-Host "OMAELITA_RADIO_WATCHDOG_ONCE=1 status=$statusPath"
        exit 0
    }
    Start-Sleep -Seconds $PollSeconds
}

Write-WatchdogStatus "timeout" "watchdog timeout"
exit 0
