[CmdletBinding()]
param(
    [string]$SubnetPrefix = "192.168.1",
    [string[]]$ExpectedMac = @("CC-6B-1E-77-2D-5B", "48-9E-BD-4D-3B-C4"),
    [switch]$ActiveProbe,
    [int]$PingTimeoutMs = 250
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Normalize-Mac([string]$Value) {
    ($Value -replace '[^0-9A-Fa-f]', '').ToUpperInvariant()
}

function Test-Tcp([string]$HostName, [int]$Port, [int]$TimeoutMs = 700) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $pending = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne($TimeoutMs)) { return $false }
        $client.EndConnect($pending)
        return $true
    } catch { return $false } finally { $client.Dispose() }
}

$wanted = @($ExpectedMac | ForEach-Object { Normalize-Mac $_ })
if ($ActiveProbe) {
    $probes = foreach ($last in 1..254) {
        $ping = [Net.NetworkInformation.Ping]::new()
        [pscustomobject]@{ Ping = $ping; Task = $ping.SendPingAsync("$SubnetPrefix.$last", $PingTimeoutMs) }
    }
    [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]$probes.Task)
    foreach ($probe in $probes) { $probe.Ping.Dispose() }
}

$matches = @()
foreach ($neighbor in Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue) {
    $normalized = Normalize-Mac ([string]$neighbor.LinkLayerAddress)
    if ($wanted -contains $normalized) {
        $matches += [ordered]@{
            ip = [string]$neighbor.IPAddress
            mac = [string]$neighbor.LinkLayerAddress
            interface = [string]$neighbor.InterfaceAlias
            neighbor_state = [string]$neighbor.State
            ssh = Test-Tcp ([string]$neighbor.IPAddress) 22
        }
    }
}

$status = if ($matches | Where-Object { $_.ssh }) { "FOUND_SSH" } elseif ($matches.Count) { "FOUND_NO_SSH" } else { "NOT_FOUND" }
[ordered]@{
    schema = "openmitrastar.aelita-discovery/v1"
    status = $status
    active_probe = $ActiveProbe.IsPresent
    subnet = "$SubnetPrefix.0/24"
    matches = $matches
    router_changes = $false
    client_changes = $false
} | ConvertTo-Json -Depth 6

if ($status -eq "FOUND_SSH") { exit 0 }
if ($status -eq "FOUND_NO_SSH") { exit 20 }
exit 21
