[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RouterHost = "192.168.1.90",
    [string]$SubnetPrefix = "192.168.1",
    [int[]]$Ports = @(22, 80, 443, 23, 8080),
    [string[]]$KnownNonRouterHosts = @("192.168.1.1", "192.168.1.63"),
    [ValidateRange(50, 5000)]
    [int]$TcpTimeoutMs = 350,
    [switch]$SweepSubnet,
    [switch]$IncludeInactiveNeighbors
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Test-TcpPortFast([string]$HostName, [int]$Port, [int]$TimeoutMs) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne([TimeSpan]::FromMilliseconds($TimeoutMs))) {
            return $false
        }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-PingFast([string]$HostName, [int]$TimeoutMs) {
    try {
        $ping = [Net.NetworkInformation.Ping]::new()
        $reply = $ping.Send($HostName, $TimeoutMs)
        return [bool]($reply.Status -eq [Net.NetworkInformation.IPStatus]::Success)
    } catch {
        return $false
    }
}

function Is-UsefulNeighbor([object]$Neighbor) {
    $ip = [string]$Neighbor.IPAddress
    $mac = [string]$Neighbor.LinkLayerAddress
    if ($ip -notmatch '^(\d{1,3}\.){3}\d{1,3}$') { return $false }
    if ($ip -match '\.255$') { return $false }
    if ($ip -match '^(224|239)\.') { return $false }
    if (-not $IncludeInactiveNeighbors -and ($mac -eq "" -or $mac -eq "00-00-00-00-00-00")) { return $false }
    return $true
}

$hostIps = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notmatch '^169\.254\.' } |
    Select-Object InterfaceAlias, InterfaceIndex, IPAddress, PrefixLength)

$neighbors = @(Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { Is-UsefulNeighbor $_ } |
    Sort-Object InterfaceAlias, IPAddress |
    Select-Object InterfaceAlias, ifIndex, IPAddress, LinkLayerAddress, State)

$targetSet = [ordered]@{}
foreach ($ip in @($RouterHost, "$SubnetPrefix.1", "$SubnetPrefix.90", "$SubnetPrefix.200", "$SubnetPrefix.201", "$SubnetPrefix.202")) {
    if ($ip -match '^(\d{1,3}\.){3}\d{1,3}$') { $targetSet[$ip] = $true }
}
foreach ($n in $neighbors) {
    $targetSet[[string]$n.IPAddress] = $true
}
if ($SweepSubnet) {
    foreach ($i in 1..254) {
        $targetSet["$SubnetPrefix.$i"] = $true
    }
}

$scan = foreach ($ip in $targetSet.Keys) {
    $portMap = [ordered]@{}
    foreach ($p in $Ports) {
        $portMap["tcp$p"] = (Test-TcpPortFast $ip $p $TcpTimeoutMs)
    }
    $neighbor = @($neighbors | Where-Object { [string]$_.IPAddress -eq $ip } | Select-Object -First 1)
    [ordered]@{
        ip = $ip
        is_expected_router_ip = [bool]($ip -eq $RouterHost)
        ping = (Test-PingFast $ip $TcpTimeoutMs)
        mac = if ($neighbor.Count -gt 0) { [string]$neighbor[0].LinkLayerAddress } else { "" }
        neighbor_state = if ($neighbor.Count -gt 0) { [string]$neighbor[0].State } else { "" }
        ports = $portMap
    }
}

$candidates = @($scan | Where-Object {
    $_.is_expected_router_ip -or
    $_.ports.tcp22 -or
    $_.ports.tcp80 -or
    $_.ports.tcp8080 -or
    ($_.mac -and $_.mac -ne "00-00-00-00-00-00")
})

$expected = @($scan | Where-Object { $_.is_expected_router_ip } | Select-Object -First 1)
$unknownSshHosts = @($candidates | Where-Object {
    $_.ports.tcp22 -and -not $_.is_expected_router_ip -and -not ($KnownNonRouterHosts -contains $_.ip)
})
$conclusion = if ($expected.Count -gt 0 -and $expected[0].ports.tcp22) {
    "EXPECTED_ROUTER_SSH_UP"
} elseif ($expected.Count -gt 0 -and $expected[0].mac -and $expected[0].mac -ne "00-00-00-00-00-00") {
    "EXPECTED_ROUTER_LAYER2_ONLY"
} elseif ($unknownSshHosts.Count -gt 0) {
    "UNKNOWN_SSH_HOSTS_PRESENT_NO_EXPECTED_ROUTER"
} else {
    "EXPECTED_ROUTER_NOT_ON_LAN"
}

[ordered]@{
    schema = "openmitrastar.network-discovery/v1"
    checked_at = (Get-Date).ToString("o")
    router_host = $RouterHost
    subnet_prefix = $SubnetPrefix
    known_non_router_hosts = $KnownNonRouterHosts
    tcp_timeout_ms = $TcpTimeoutMs
    sweep_subnet = [bool]$SweepSubnet
    host_ips = $hostIps
    arp_neighbors = $neighbors
    scan = $scan
    candidates = $candidates
    unknown_ssh_hosts = $unknownSshHosts
    conclusion = $conclusion
} | ConvertTo-Json -Depth 8
