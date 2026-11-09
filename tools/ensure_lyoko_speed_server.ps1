[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("Ensure", "Status", "Stop")]
    [string]$Action = "Ensure",
    [string]$BindAddress = "0.0.0.0",
    [int]$Port = 8008,
    [int]$PayloadMiB = 32,
    [string]$AllowedClient = "192.168.1.63"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$state = Join-Path $root ".codex_tmp\lyoko-speed-server"
$pidFile = Join-Path $state "server.pid"
$stdout = Join-Path $state "server.stdout.log"
$stderr = Join-Path $state "server.stderr.log"
$server = Join-Path $root "tools\openmitrastar_l2_speed_server.py"
$ruleName = "OpenMitraStar Lyoko Speed Server"

function Get-OwnedProcess {
    if (-not (Test-Path -LiteralPath $pidFile)) { return $null }
    $raw = (Get-Content -Raw -LiteralPath $pidFile).Trim()
    if ($raw -notmatch '^\d+$') { return $null }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$raw" -ErrorAction SilentlyContinue
    if ($process -and $process.CommandLine -like "*openmitrastar_l2_speed_server.py*") { return $process }
    return $null
}

function Test-ManagedConfiguration($Process) {
    if (-not $Process) { return $false }
    return (
        $Process.CommandLine -like "*--port $Port*" -and
        $Process.CommandLine -like "*--allowed-client $AllowedClient*"
    )
}

function Test-Listening {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

$owned = Get-OwnedProcess
$managed = if (Test-ManagedConfiguration $owned) { $owned } else { $null }
if ($Action -eq "Status") {
    $status = if ($managed -and (Test-Listening)) { "READY" } elseif ($owned) { "MISCONFIGURED" } else { "STOPPED" }
    [ordered]@{ status = $status; pid = if ($owned) { $owned.ProcessId } else { 0 }; port = $Port; allowed_client = $AllowedClient } | ConvertTo-Json
    exit 0
}

if ($Action -eq "Stop") {
    if ($owned) { Stop-Process -Id $owned.ProcessId -Force }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    try {
        Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction Stop
    } catch {
        # The application ACL remains the primary boundary when elevation is unavailable.
    }
    [ordered]@{ status = "STOPPED"; port = $Port } | ConvertTo-Json
    exit 0
}

if ($managed -and (Test-Listening)) {
    [ordered]@{ status = "READY"; pid = $managed.ProcessId; port = $Port; reused = $true } | ConvertTo-Json
    exit 0
}
if ($owned) {
    Stop-Process -Id $owned.ProcessId -Force
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 250
}
if (Test-Listening) { throw "TCP port $Port is occupied by an unmanaged process" }

New-Item -ItemType Directory -Force -Path $state | Out-Null
$python = (Get-Command python.exe -ErrorAction Stop).Source
$existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
$firewall = "unavailable"
try {
    if ($existingRule) { $existingRule | Remove-NetFirewallRule -ErrorAction Stop }
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -RemoteAddress $AllowedClient -ErrorAction Stop | Out-Null
    $firewall = "scoped-rule"
} catch {
    $firewall = "app-acl-only"
}
$process = Start-Process -FilePath $python `
    -ArgumentList @($server, "--bind", $BindAddress, "--port", [string]$Port, "--mib", [string]$PayloadMiB, "--max-upload-mib", "64", "--allowed-client", $AllowedClient) `
    -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ascii
Start-Sleep -Seconds 1
$response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "http://127.0.0.1:$Port/"
if ($response.StatusCode -ne 200 -or -not (Test-Listening)) { throw "Lyoko speed server failed readiness" }
[ordered]@{ status = "READY"; pid = $process.Id; port = $Port; allowed_client = $AllowedClient; download_mib = $PayloadMiB; firewall = $firewall; reused = $false } | ConvertTo-Json
