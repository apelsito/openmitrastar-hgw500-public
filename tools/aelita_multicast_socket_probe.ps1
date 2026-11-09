param(
    [string]$WifiInterface = 'Wi-Fi',
    [string]$Group = '239.255.77.77',
    [int[]]$Ports = @(33972, 33975)
)

$ErrorActionPreference = 'Stop'
$ip = Get-NetIPAddress -InterfaceAlias $WifiInterface -AddressFamily IPv4 -ErrorAction Stop |
    Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' } |
    Select-Object -First 1
if (-not $ip) { throw 'Wi-Fi IPv4 address is unavailable' }

$rows = foreach ($port in $Ports) {
    $udp = $null
    $stage = 'create'
    try {
        $udp = [Net.Sockets.UdpClient]::new()
        $stage = 'reuse'
        $udp.ExclusiveAddressUse = $false
        $udp.Client.SetSocketOption(
            [Net.Sockets.SocketOptionLevel]::Socket,
            [Net.Sockets.SocketOptionName]::ReuseAddress,
            $true
        )
        $stage = 'bind'
        $udp.Client.Bind([Net.IPEndPoint]::new([Net.IPAddress]::Any, $port))
        $stage = 'join'
        $udp.JoinMulticastGroup([Net.IPAddress]::Parse($Group), [Net.IPAddress]::Parse($ip.IPAddress))
        [ordered]@{ port = $port; status = 'PASS'; stage = 'joined'; error_type = $null }
    } catch {
        [ordered]@{ port = $port; status = 'FAIL'; stage = $stage; error_type = $_.Exception.GetType().FullName }
    } finally {
        if ($udp) { $udp.Close() }
    }
}

[ordered]@{
    schema = 'openmitrastar.aelita-multicast-socket-probe/v1'
    interface = $WifiInterface
    ipv4 = $ip.IPAddress
    group = $Group
    results = @($rows)
    mutation = $false
} | ConvertTo-Json -Compress -Depth 4
