[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RunDir = "",
    [int]$TimeoutSeconds = 21600,
    [int]$PollSeconds = 20,
    [int]$AelitaScanEveryPolls = 6,
    [string]$HostAddress = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "/workspace/user-home\Desktop\MitraStar\.codex_tmp\openmitrastar_ramssh_client_ed25519",
    [string]$OracleHost = "192.168.1.63",
    [string]$OracleUser = "AELITA",
    [double]$Min2gMbps = 5.0,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f65-mgmt-watch-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$statusOut = Join-Path $OutputDir "monitor-status.json"
$logPath = Join-Path $OutputDir "monitor.log"

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

function Get-LatestRunDir {
    $latest = Get-ChildItem -LiteralPath (Join-Path $Root "outputs\flash-watch") -Directory -Filter "f65-isolated-5g-*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latest) { return $latest.FullName }
    return ""
}

function Write-MgmtStatus(
    [string]$State,
    [string]$Message,
    [object]$WatcherStatus,
    [bool]$PingOk,
    [bool]$Tcp22,
    [string]$AelitaScanPath = "",
    [string]$GateResult = ""
) {
    [ordered]@{
        schema = "openmitrastar.f65-mgmt-gate-monitor/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        run_dir = $RunDir
        output_dir = $OutputDir
        host = $HostAddress
        ping = $PingOk
        tcp22 = $Tcp22
        aelita_scan = $AelitaScanPath
        watcher = $WatcherStatus
        gate_result = $GateResult
    } | ConvertTo-Json -Depth 12 | Set-Content -Encoding ascii -LiteralPath $statusOut
}

function Invoke-AelitaScan([int]$Poll) {
    $scanPath = Join-Path $OutputDir ("aelita-scan-{0:0000}.log" -f $Poll)
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "connect_aelita_auto.ps1") `
        -Mode ssh `
        -HostAddress $OracleHost `
        -User $OracleUser `
        -RemoteCommand "netsh wlan show networks mode=bssid" *> $scanPath
    return $scanPath
}

if (-not $RunDir) {
    $RunDir = Get-LatestRunDir
}
if (-not $RunDir) {
    Write-MgmtStatus "no_watcher" "no f65 watcher run directory found" $null $false $false
    exit 2
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$poll = 0
"MGMT_MONITOR_START at=$(Get-Date -Format o) run_dir=$RunDir host=$HostAddress" |
    Add-Content -Encoding ascii -LiteralPath $logPath

while ((Get-Date) -lt $deadline) {
    $poll += 1
    $raw = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "status_f65_isolated_5g_flash_watch.ps1") -RunDir $RunDir -TailLines 40
    $watcher = $raw | ConvertFrom-Json
    $classification = [string]$watcher.classification
    $pingOk = [bool](Test-Connection -ComputerName $HostAddress -Count 1 -Quiet -ErrorAction SilentlyContinue)
    $tcp22 = [bool](Test-TcpPort $HostAddress 22 3)
    $scanPath = ""

    if ($poll -eq 1 -or (($poll % [Math]::Max(1, $AelitaScanEveryPolls)) -eq 0)) {
        try {
            $scanPath = Invoke-AelitaScan $poll
        } catch {
            $scanPath = "scan_failed: $($_.Exception.Message)"
        }
    }

    "MGMT_MONITOR_POLL at=$(Get-Date -Format o) poll=$poll classification=$classification ping=$pingOk tcp22=$tcp22 scan=$scanPath" |
        Add-Content -Encoding ascii -LiteralPath $logPath

    if ($tcp22) {
        $gateDir = Join-Path $OutputDir "post-flash-gate"
        "MGMT_MONITOR_TCP22_PASS at=$(Get-Date -Format o) gate_dir=$gateDir" |
            Add-Content -Encoding ascii -LiteralPath $logPath
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "post_flash_f65_radio_gate.ps1") `
            -HostAddress $HostAddress `
            -RouterUser $RouterUser `
            -RouterKey $RouterKey `
            -OracleHost $OracleHost `
            -OracleUser $OracleUser `
            -OutputDir $gateDir `
            -Run2gProbe `
            -Min2gMbps $Min2gMbps *> (Join-Path $OutputDir "post-flash-gate.stdout.log")
        $rc = $LASTEXITCODE
        $resultPath = Join-Path $gateDir "result.json"
        Write-MgmtStatus $(if ($rc -eq 0) { "pass" } else { "gate_failed" }) "post-flash gate rc=$rc" $watcher $pingOk $tcp22 $scanPath $resultPath
        exit $rc
    }

    if ($classification -eq "FLASH_PASS" -or [bool]$watcher.markers.flash_pass) {
        Write-MgmtStatus "flash_pass_waiting_ssh" "flash pass seen but tcp22 not ready" $watcher $pingOk $tcp22 $scanPath
    } else {
        Write-MgmtStatus "watching" "classification=$classification" $watcher $pingOk $tcp22 $scanPath
    }

    Start-Sleep -Seconds $PollSeconds
}

Write-MgmtStatus "timeout" "monitor timeout waiting for management SSH" $watcher $pingOk $tcp22 $scanPath
exit 1
