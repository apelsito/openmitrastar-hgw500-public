[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$HostAddress = "192.168.1.90",
    [ValidateRange(5, 3600)]
    [int]$PollSeconds = 15,
    [ValidateRange(60, 86400)]
    [int]$TimeoutSeconds = 21600,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f93-f95-status-watch-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$LatestPath = Join-Path $OutputDir "latest.json"
$HistoryPath = Join-Path $OutputDir "history.jsonl"
$StatusScript = Join-Path $PSScriptRoot "status_f93_f95_chain.ps1"

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutSeconds = 2) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne([TimeSpan]::FromSeconds($TimeoutSeconds))) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Get-ChainStatus {
    $raw = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $StatusScript -HostAddress $HostAddress 2>&1
    $rc = $LASTEXITCODE
    if ($rc -ne 0) {
        return [ordered]@{
            schema = "openmitrastar.f93-f95-status-watch-sample/v1"
            checked_at = (Get-Date).ToString("o")
            status_ok = $false
            status_exit_code = [int]$rc
            status_output = ($raw -join "`n")
        }
    }
    $status = (($raw -join "`n") | ConvertFrom-Json)
    return [ordered]@{
        schema = "openmitrastar.f93-f95-status-watch-sample/v1"
        checked_at = (Get-Date).ToString("o")
        status_ok = $true
        router_ping = [bool](Test-Connection -ComputerName $HostAddress -Count 1 -Quiet -ErrorAction SilentlyContinue)
        router_tcp22 = [bool](Test-TcpPort $HostAddress 22 2)
        chain_state = [string]$status.chain_state
        f93_state = [string]$status.f93_state
        uart_zero_bytes_stale = [bool]$status.uart_zero_bytes_stale
        uart = $status.uart
        blind_space_count = if ($status.PSObject.Properties.Name -contains "blind_space_count") { $status.blind_space_count } else { $null }
        recommendation = if ($status.PSObject.Properties.Name -contains "recommendation") { [string]$status.recommendation } else { "" }
        next_action = if ($status.PSObject.Properties.Name -contains "next_action") { [string]$status.next_action } else { "" }
        active_processes = $status.active_processes
    }
}

$started = Get-Date
$deadline = $started.AddSeconds($TimeoutSeconds)
$sampleCount = 0

while ((Get-Date) -lt $deadline) {
    $sampleCount += 1
    $sample = Get-ChainStatus
    $sample["sample"] = $sampleCount
    $sample["output_dir"] = $OutputDir
    $sample["deadline"] = $deadline.ToString("o")
    $sample | ConvertTo-Json -Depth 10 | Set-Content -Encoding ascii -LiteralPath $LatestPath
    ($sample | ConvertTo-Json -Depth 10 -Compress) | Add-Content -Encoding ascii -LiteralPath $HistoryPath

    $state = if ($sample.Contains("chain_state")) { [string]$sample.chain_state } else { "unknown" }
    $routerTcp22 = if ($sample.Contains("router_tcp22")) { [bool]$sample.router_tcp22 } else { $false }
    $uartBytes = if ($sample.Contains("uart") -and $sample.uart -and $sample.uart.PSObject.Properties.Name -contains "bytes") {
        [int64]$sample.uart.bytes
    } else {
        $null
    }
    Write-Host "OMF93F95_STATUS_WATCH sample=$sampleCount state=$state tcp22=$routerTcp22 uart_bytes=$uartBytes latest=$LatestPath"

    if ($state -in @("pass", "f93_failed", "f95_failed_f93_fallback_armed", "timeout")) {
        break
    }
    Start-Sleep -Seconds $PollSeconds
}

$final = Get-ChainStatus
$final["sample"] = $sampleCount + 1
$final["output_dir"] = $OutputDir
$final["watch_finished_at"] = (Get-Date).ToString("o")
$final | ConvertTo-Json -Depth 10 | Set-Content -Encoding ascii -LiteralPath $LatestPath
($final | ConvertTo-Json -Depth 10 -Compress) | Add-Content -Encoding ascii -LiteralPath $HistoryPath

Write-Host "OMF93F95_STATUS_WATCH_DONE latest=$LatestPath history=$HistoryPath"
