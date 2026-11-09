[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [switch]$ReplaceMonitor,
    [switch]$ReplaceWatcher,
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "001de769",
    [ValidateRange(600, 21600)]
    [int]$BootWaitSeconds = 21600,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [ValidateRange(0, 300)]
    [int]$NoRxAbortSeconds = 0,
    [ValidateRange(0, 300)]
    [int]$BlindAtguAfterNoRxSeconds = 8,
    [ValidateRange(1, 200)]
    [double]$Min2gMbps = 20.0,
    [ValidateSet("download", "upload", "both")]
    [string]$TwoGTrafficDirection = "both",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$ExpectedSha256 = "87e0d43536a2d80baf8353c52919d9c7c02de595dcc70b8ddd65ee5797197089"
$CandidateName = "f126-5g-assoc-observe-from-f125"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
if (-not $OutputDir) {
    $OutputDir = Join-Path $Root "outputs\postflash\f126-auto-arm-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StatusPath = Join-Path $OutputDir "status.json"

function Read-JsonFile([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
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

function Get-LatestF126RunDir {
    $items = @(Get-ChildItem -LiteralPath (Join-Path $Root "outputs\flash-watch") -Directory -Filter "f126-5g-assoc-observe*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending)
    foreach ($item in $items) {
        $status = Read-JsonFile (Join-Path $item.FullName "status.json")
        if ($status -and [string]$status.candidate_sha256 -eq $ExpectedSha256) {
            return $item.FullName
        }
    }
    return ""
}

function Get-LatestF126Monitor {
    $items = @(Get-ChildItem -LiteralPath (Join-Path $Root "outputs\postflash") -Directory -Filter "f126-5g-assoc-only-monitor-*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending)
    foreach ($item in $items) {
        $status = Read-JsonFile (Join-Path $item.FullName "monitor-status.json")
        if ($status -and [string]$status.candidate_sha256 -eq $ExpectedSha256) {
            return [ordered]@{ dir = $item.FullName; status = $status }
        }
    }
    return $null
}

function Write-Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f126-auto-arm-and-monitor/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        execute = [bool]$Execute
        replace_monitor = [bool]$ReplaceMonitor
        replace_watcher = [bool]$ReplaceWatcher
        candidate = $CandidateName
        candidate_sha256 = $ExpectedSha256
        port = $Port
        host = $HostAddress
        min_2g_mbps = $Min2gMbps
        two_g_traffic_direction = $TwoGTrafficDirection
    }
    foreach ($key in $Extra.Keys) { $payload[$key] = $Extra[$key] }
    $payload | ConvertTo-Json -Depth 10 | Set-Content -Encoding ascii -LiteralPath $StatusPath
}

$runDir = Get-LatestF126RunDir
$runStatus = if ($runDir) { Read-JsonFile (Join-Path $runDir "status.json") } else { $null }
$watcherAlive = [bool]($runStatus -and ($runStatus.PSObject.Properties.Name -contains "pid") -and (Test-ProcessAlive $runStatus.pid))

if ($ReplaceWatcher -and $watcherAlive) {
    Stop-Process -Id ([int]$runStatus.pid) -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    $watcherAlive = $false
}

if (-not $Execute) {
    $dryDir = Join-Path $OutputDir "dry-run"
    $dryOut = Join-Path $OutputDir "arm-dry-run.stdout.log"
    $dryErr = Join-Path $OutputDir "arm-dry-run.stderr.log"
    $proc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -PassThru `
        -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $PSScriptRoot "arm_f126_5g_assoc_observe_flash.ps1"),
            "-OutputDir", $dryDir,
            "-Port", $Port,
            "-ServerIp", $ServerIp,
            "-ClientIp", $ClientIp,
            "-HostAddress", $HostAddress,
            "-CurrentLiveCrc32", $CurrentLiveCrc32,
            "-BootWaitSeconds", "$BootWaitSeconds",
            "-FlashTimeoutSeconds", "$FlashTimeoutSeconds",
            "-NoRxAbortSeconds", "$NoRxAbortSeconds",
            "-BlindAtguAfterNoRxSeconds", "$BlindAtguAfterNoRxSeconds"
        ) `
        -RedirectStandardOutput $dryOut `
        -RedirectStandardError $dryErr
    $proc.WaitForExit()
    Write-Status "dry_run_complete" "F126 auto-arm dry-run complete; no router writes" @{
        dry_run_dir = $dryDir
        dry_run_stdout = $dryOut
        dry_run_stderr = $dryErr
        dry_run_exit_code = [int]$proc.ExitCode
    }
    Write-Host "OMF126_SUPERVISOR_DRY_RUN_COMPLETE=1 status=$StatusPath"
    exit $proc.ExitCode
}

if (-not $watcherAlive) {
    $runDir = Join-Path $Root "outputs\flash-watch\f126-5g-assoc-observe-blind-atgu-$stamp"
    $armOut = Join-Path $OutputDir "arm-execute.stdout.log"
    $armErr = Join-Path $OutputDir "arm-execute.stderr.log"
    $armArgs = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "arm_f126_5g_assoc_observe_flash.ps1"),
        "-Execute",
        "-OutputDir", $runDir,
        "-Port", $Port,
        "-ServerIp", $ServerIp,
        "-ClientIp", $ClientIp,
        "-HostAddress", $HostAddress,
        "-CurrentLiveCrc32", $CurrentLiveCrc32,
        "-BootWaitSeconds", "$BootWaitSeconds",
        "-FlashTimeoutSeconds", "$FlashTimeoutSeconds",
        "-NoRxAbortSeconds", "$NoRxAbortSeconds",
        "-BlindAtguAfterNoRxSeconds", "$BlindAtguAfterNoRxSeconds",
        "-AllowBlindAutobreak",
        "-AllowNoRxRebootAssist"
    )
    $armProc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -PassThru `
        -ArgumentList $armArgs `
        -RedirectStandardOutput $armOut `
        -RedirectStandardError $armErr
    $deadline = (Get-Date).AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 250
        $runStatus = Read-JsonFile (Join-Path $runDir "status.json")
        $watcherAlive = [bool]($runStatus -and ($runStatus.PSObject.Properties.Name -contains "pid") -and (Test-ProcessAlive $runStatus.pid))
    } while (-not $watcherAlive -and (Get-Date) -lt $deadline)
    if (-not $watcherAlive) {
        Write-Status "arm_failed" "F126 watcher did not become alive" @{
            run_dir = $runDir
            arm_pid = $armProc.Id
            arm_stdout = $armOut
            arm_stderr = $armErr
        }
        throw "F126 watcher did not become alive; see $armOut and $armErr"
    }
}

$monitor = Get-LatestF126Monitor
$monitorAlive = [bool]($monitor -and $monitor.status -and ($monitor.status.PSObject.Properties.Name -contains "process_id") -and (Test-ProcessAlive $monitor.status.process_id))
if ($ReplaceMonitor -and $monitorAlive) {
    Stop-Process -Id ([int]$monitor.status.process_id) -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    $monitorAlive = $false
}

if (-not $monitorAlive) {
    $monitorDir = Join-Path $Root "outputs\postflash\f126-5g-assoc-only-monitor-$stamp"
    New-Item -ItemType Directory -Force -Path $monitorDir | Out-Null
    $monitorArgs = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "monitor_f126_flash_then_assoc_only_5g.ps1"),
        "-RunDir", $runDir,
        "-OutputDir", $monitorDir,
        "-PollSeconds", "10",
        "-TimeoutSeconds", "$BootWaitSeconds",
        "-AssocTimeoutSeconds", "180",
        "-RadioReadyTimeoutSeconds", "120",
        "-Min2gMbps", "$Min2gMbps",
        "-TwoGTrafficDirection", $TwoGTrafficDirection
    )
    $monitorProc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -PassThru `
        -ArgumentList $monitorArgs `
        -RedirectStandardOutput (Join-Path $monitorDir "monitor-launch.stdout.log") `
        -RedirectStandardError (Join-Path $monitorDir "monitor-launch.stderr.log")
    $monitor = [ordered]@{ dir = $monitorDir; status = [ordered]@{ process_id = $monitorProc.Id; state = "starting" } }
    $monitorAlive = $true
}

Write-Status "armed" "F126 watcher and postflash monitor are active or reused" @{
    run_dir = $runDir
    watcher_pid = [int]$runStatus.pid
    watcher_state = [string]$runStatus.state
    monitor_dir = [string]$monitor.dir
    monitor_pid = [int]$monitor.status.process_id
    monitor_state = [string]$monitor.status.state
}
Write-Host "OMF126_SUPERVISOR_ARMED=1 status=$StatusPath watcher_pid=$($runStatus.pid) monitor_pid=$($monitor.status.process_id)"
