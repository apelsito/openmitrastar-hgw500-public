# Same read-only adapter/address/direct-route contract used by F325 transport.
function Assert-F336HostNetwork {
    param([object]$Plan,[switch]$RequireFreeUdp)
    $net=$Plan.network
    $adapters=@(Get-NetAdapter -IncludeHidden -ErrorAction Stop | Where-Object {$_.ifIndex -eq $net.interface_index})
    if($adapters.Count -ne 1 -or [string]$adapters[0].Name -cne 'Ethernet' -or [string]$adapters[0].Status -cne 'Up' -or [string]$adapters[0].MediaType -cne '802.3'){throw 'F336_ETHERNET_ADAPTER'}
    $addresses=@(Get-NetIPAddress -InterfaceIndex 18 -AddressFamily IPv4 -ErrorAction Stop | Where-Object {$_.IPAddress -ceq '192.168.1.49'})
    if($addresses.Count -ne 1 -or $addresses[0].PrefixLength -ne 24 -or [string]$addresses[0].AddressState -cne 'Preferred' -or $addresses[0].SkipAsSource -ne $false){throw 'F336_SOURCE_ADDRESS'}
    $selection=@(Find-NetRoute -RemoteIPAddress '192.168.1.90' -ErrorAction Stop)
    $source=@($selection | Where-Object {$_.PSObject.Properties['IPAddress']});$route=@($selection | Where-Object {$_.PSObject.Properties['DestinationPrefix']})
    if($source.Count -ne 1 -or $route.Count -ne 1 -or $selection.Count -ne 2 -or $source[0].IPAddress -cne '192.168.1.49' -or $source[0].InterfaceIndex -ne 18 -or $route[0].InterfaceIndex -ne 18 -or $route[0].DestinationPrefix -cne '192.168.1.0/24' -or $route[0].NextHop -cne '0.0.0.0'){throw 'F336_DIRECT_ROUTE'}
    if($RequireFreeUdp -and @(Get-NetUDPEndpoint -ErrorAction Stop | Where-Object {$_.LocalPort -eq 69}).Count -ne 0){throw 'F336_UDP69_OCCUPIED'}
}
