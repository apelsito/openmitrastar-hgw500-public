[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$RouterHost = "192.168.1.90",
    [string]$Port = "COM3",
    [ValidateRange(30, 1800)][int]$WaitSeconds = 900,
    [ValidateRange(2, 30)][int]$PollSeconds = 5
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$requiredAck = "OPENMITRASTAR_F264_DETACHED_JOBS_8B53DD2B"
$promoter = Join-Path $PSScriptRoot "promote_f264_mtd4_direct.ps1"

function Test-Tcp([string]$HostName, [int]$TcpPort, [int]$TimeoutMs = 1200) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $pending = $client.BeginConnect($HostName, $TcpPort, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne($TimeoutMs)) { return $false }
        $client.EndConnect($pending)
        return $true
    } catch { return $false } finally { $client.Dispose() }
}

if ($Execute -and $Ack -ne $requiredAck) {
    throw "Refusing F264 promotion: exact -Ack is required"
}

$deadline = [DateTime]::UtcNow.AddSeconds($WaitSeconds)
$attempt = 0
while ([DateTime]::UtcNow -lt $deadline) {
    $attempt++
    if (Test-Tcp $RouterHost 22) { break }
    Write-Output "OMF264_WAITING_POWER_CYCLE attempt=$attempt host=$RouterHost"
    Start-Sleep -Seconds $PollSeconds
}
if (-not (Test-Tcp $RouterHost 22)) {
    throw "F263 did not return on SSH within $WaitSeconds seconds"
}

Write-Output "OMF264_ROUTER_RETURNED=1 host=$RouterHost attempts=$attempt"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $promoter -Port $Port -RouterHost $RouterHost
if ($LASTEXITCODE -ne 0) { throw "F264 dry-run failed after power-cycle" }

if (-not $Execute) {
    Write-Output "OMF264_RESUME_DRY_RUN_PASS=1"
    exit 0
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $promoter `
    -Execute -Ack $requiredAck -Port $Port -RouterHost $RouterHost -Transport auto
if ($LASTEXITCODE -ne 0) { throw "F264 promotion failed" }
Write-Output "OMF264_RESUME_AND_PROMOTE_PASS=1"
