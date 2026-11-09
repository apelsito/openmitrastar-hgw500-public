# R9 recovery host binding v2. Read-only; historical F325/F336 guards stay intact.
# Snapshot function is exact F325 body with only its name and index 18 -> 17.
. (Join-Path $PSScriptRoot 'f325_existing_firewall.ps1')
. (Join-Path $PSScriptRoot 'f367r9_return_context.ps1')

function Get-R9Host17ExpectedIdentity {
    return [ordered]@{interface_index=17;interface_alias='Ethernet';interface_guid='b75315d5-9f01-448f-a259-c9d8f25d2233';
        pnp_device_id='PCI\VEN_10EC&DEV_8168&SUBSYS_E0001458&REV_16\6E8F9B4DC018000000';source_ipv4='192.168.1.49';prefix_length=24;
        target_ipv4='192.168.1.90';route_prefix='192.168.1.0/24';next_hop='0.0.0.0';link_speed_bps=1000000000}
}

function ConvertTo-R9Host17Map {
    param([Parameter(Mandatory=$true)]$Object)
    $map=[ordered]@{}
    if($Object -is [System.Collections.IDictionary]){foreach($key in $Object.Keys){$map[$key]=$Object[$key]}}
    else{foreach($property in $Object.PSObject.Properties){$map[$property.Name]=$property.Value}}
    return $map
}

function Assert-R9Host17Projection {
    param([Parameter(Mandatory=$true)]$Original,[Parameter(Mandatory=$true)]$Current)
    $old=ConvertTo-R9Host17Map $Original;$now=ConvertTo-R9Host17Map $Current
    if((@($old.Keys|Sort-Object) -join '|') -cne (@($now.Keys|Sort-Object) -join '|')){throw 'R9_HOST17_PROJECTION_KEYS_CHANGED'}
    if((Get-F325PermissionProjectionSha256 -Projection $old) -cne $script:F325ExistingFingerprint){throw 'R9_HOST17_ORIGINAL_PROJECTION_CHANGED'}
    $changed=@()
    foreach($key in $old.Keys){
        if([string]$old[$key] -cne [string]$now[$key]){$changed+=,$key}
        if($key -ceq 'connection_interface_index'){
            if([string]$old[$key] -cne '18' -or [string]$now[$key] -cne '17'){throw 'R9_HOST17_INDEX_NOT_EXACT_TRANSITION'}
        }elseif([string]$old[$key] -cne [string]$now[$key]){throw ('R9_HOST17_PERMISSION_CHANGED_'+$key)}
    }
    if($changed.Count -ne 1 -or $changed[0] -cne 'connection_interface_index'){throw 'R9_HOST17_ONLY_INDEX_DIFFERENCE_REQUIRED'}
    return [pscustomobject]@{status='PASS_ONLY_CONNECTION_INTERFACE_INDEX_CHANGED';changed_fields=$changed;
        original_fingerprint_sha256=$script:F325ExistingFingerprint;current_fingerprint_sha256=(Get-F325PermissionProjectionSha256 -Projection $now)}
}

function Get-R9Host17NetworkSnapshot {
    param([switch]$RequireFreeUdp)
    $expected=Get-R9Host17ExpectedIdentity
    $adapters=@(Get-NetAdapter -IncludeHidden -ErrorAction Stop | Where-Object {$_.ifIndex -eq 17})
    $cim=@(Get-CimInstance Win32_NetworkAdapter -Filter 'InterfaceIndex=17' -ErrorAction Stop)
    if($adapters.Count -ne 1 -or $cim.Count -ne 1){throw 'R9_HOST17_ADAPTER_CARDINALITY'}
    $adapter=$adapters[0];$device=$cim[0]
    if([string]$adapter.Name -cne 'Ethernet' -or [string]$adapter.Status -cne 'Up' -or [string]$adapter.MediaType -cne '802.3' -or
       ([Guid]$adapter.InterfaceGuid).ToString('D') -cne $expected.interface_guid -or ([Guid]$device.GUID).ToString('D') -cne $expected.interface_guid -or
       [string]$device.PNPDeviceID -ine $expected.pnp_device_id -or [string]$device.NetConnectionID -cne 'Ethernet' -or
       [uint64]$device.Speed -ne 1000000000 -or $device.NetEnabled -isnot [bool] -or -not $device.NetEnabled){throw 'R9_HOST17_ADAPTER_IDENTITY'}
    $addresses=@(Get-NetIPAddress -InterfaceIndex 17 -AddressFamily IPv4 -ErrorAction Stop | Where-Object {$_.IPAddress -ceq '192.168.1.49'})
    if($addresses.Count -ne 1 -or $addresses[0].PrefixLength -ne 24 -or [string]$addresses[0].AddressState -cne 'Preferred' -or
       $addresses[0].SkipAsSource -isnot [bool] -or $addresses[0].SkipAsSource){throw 'R9_HOST17_SOURCE_ADDRESS'}
    $oldAddresses=@(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop | Where-Object {$_.InterfaceIndex -eq 18})
    if($oldAddresses.Count -ne 0){throw 'R9_HOST17_OLD_INDEX_HAS_IPV4'}
    $selection=@(Find-NetRoute -RemoteIPAddress '192.168.1.90' -ErrorAction Stop)
    $source=@($selection|Where-Object {$_.PSObject.Properties['IPAddress']});$route=@($selection|Where-Object {$_.PSObject.Properties['DestinationPrefix']})
    if($source.Count -ne 1 -or $route.Count -ne 1 -or $selection.Count -ne 2 -or $source[0].IPAddress -cne '192.168.1.49' -or
       $source[0].InterfaceIndex -ne 17 -or $route[0].InterfaceIndex -ne 17 -or $route[0].DestinationPrefix -cne '192.168.1.0/24' -or
       $route[0].NextHop -cne '0.0.0.0'){throw 'R9_HOST17_DIRECT_ROUTE'}
    if($RequireFreeUdp -and @(Get-NetUDPEndpoint -ErrorAction Stop|Where-Object {$_.LocalPort -eq 69}).Count -ne 0){throw 'R9_HOST17_UDP69_OCCUPIED'}
    return [pscustomobject]@{schema='openmitrastar.r9-host17-network/v1';identity=$expected;adapter_status=[string]$adapter.Status;
        media_type=[string]$adapter.MediaType;adapter_description=[string]$adapter.InterfaceDescription;device_name=[string]$device.Name;
        address_state=[string]$addresses[0].AddressState;skip_as_source=[bool]$addresses[0].SkipAsSource;old_index18_ipv4_count=0;
        direct_route=$true;host_mutation=$false;device_access=$false}
}

function Assert-R9Host17ObservationFile {
    param([Parameter(Mandatory=$true)]$Plan)
    Assert-F325ExistingPermissionPlan -Plan $Plan
    if($Plan.network.interface_index -ne 17 -or $Plan.network.interface_alias -cne 'Ethernet' -or $Plan.network.server_ipv4 -cne '192.168.1.49' -or
       $Plan.network.client_ipv4 -cne '192.168.1.90'){throw 'R9_HOST17_PLAN_NETWORK'}
    $ref=$Plan.network.host17_observation
    $path=Assert-R9ReturnPath $ref.path
    if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $ref.sha256){throw 'R9_HOST17_OBSERVATION_HASH'}
    $observation=Get-Content -LiteralPath $path -Raw|ConvertFrom-Json
    if($observation.schema -cne 'openmitrastar.r9-host17-observation/v1' -or $observation.status -cne 'PASS_HOST17_ONLY_INDEX_REBIND' -or
       $observation.host_mutation -isnot [bool] -or $observation.host_mutation -or $observation.device_access -isnot [bool] -or $observation.device_access){throw 'R9_HOST17_OBSERVATION_SCOPE'}
    $expected=Get-R9Host17ExpectedIdentity
    $actual=ConvertTo-R9Host17Map $observation.network.identity
    if((@($expected.Keys|Sort-Object) -join '|') -cne (@($actual.Keys|Sort-Object) -join '|')){throw 'R9_HOST17_IDENTITY_FIELDS'}
    foreach($key in $expected.Keys){if([string]$expected[$key] -cne [string]$actual[$key]){throw 'R9_HOST17_PINNED_IDENTITY'}}
    [void](Assert-R9Host17Projection -Original $Plan.network.existing_permission.projection -Current $observation.permission.projection)
    foreach($entry in $observation.source_pins.PSObject.Properties){if((Get-FileHash -LiteralPath $entry.Name -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value){throw 'R9_HOST17_COLLECTOR_DRIFT'}}
    return $observation
}

function Assert-R9Host17Permission {
    param([Parameter(Mandatory=$true)]$Plan)
    $bound=Assert-R9Host17ObservationFile -Plan $Plan
    $current=Get-R9Host17PermissionSnapshot -Plan $Plan
    $comparison=Assert-R9Host17Projection -Original $Plan.network.existing_permission.projection -Current $current.projection
    if($comparison.current_fingerprint_sha256 -cne $bound.permission.fingerprint_sha256){throw 'R9_HOST17_PERMISSION_FINGERPRINT_DRIFT'}
    return $current
}

function Assert-R9Host17Network {
    param([Parameter(Mandatory=$true)]$Plan,[switch]$RequireFreeUdp)
    $bound=Assert-R9Host17ObservationFile -Plan $Plan
    $current=Get-R9Host17NetworkSnapshot -RequireFreeUdp:$RequireFreeUdp
    foreach($key in @('adapter_status','media_type','adapter_description','device_name','address_state','skip_as_source','old_index18_ipv4_count','direct_route')){
        if([string]$current.$key -cne [string]$bound.network.$key){throw ('R9_HOST17_NETWORK_DRIFT_'+$key)}
    }
}

function Get-R9Host17PermissionSnapshot {
    param([object]$Plan)
    if ($Plan.network.server_ipv4 -cne '192.168.1.49' -or $Plan.network.interface_index -ne 17 -or
        $Plan.network.interface_alias -cne 'Ethernet' -or $Plan.network.python_executable -ine $script:F325ExistingProgram) {
        throw 'Existing permission is bound to exact Python312 and Ethernet .49/17'
    }
    $python = [IO.FileInfo]::new($script:F325ExistingProgram)
    if (-not $python.Exists -or ($python.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Existing-permission Python must be a regular pinned executable' }
    $rules = @(Get-NetFirewallRule -PolicyStore ActiveStore -Name $script:F325ExistingRuleName -ErrorAction Stop)
    if ($rules.Count -ne 1) { throw 'Existing firewall permission is missing or ambiguous' }
    $rule = $rules[0]
    if ($rule.Name -ine $script:F325ExistingRuleName -or [string]$rule.Enabled -cne 'True' -or
        [string]$rule.Direction -cne 'Inbound' -or [string]$rule.Action -cne 'Allow' -or
        [string]$rule.Profile -cne 'Public' -or [string]$rule.EnforcementStatus -cne 'Enforced') {
        throw 'Existing firewall permission is not currently enforced for Public inbound traffic'
    }
    $app = @($rule | Get-NetFirewallApplicationFilter -ErrorAction Stop)
    $port = @($rule | Get-NetFirewallPortFilter -ErrorAction Stop)
    $address = @($rule | Get-NetFirewallAddressFilter -ErrorAction Stop)
    $iface = @($rule | Get-NetFirewallInterfaceFilter -ErrorAction Stop)
    $type = @($rule | Get-NetFirewallInterfaceTypeFilter -ErrorAction Stop)
    $service = @($rule | Get-NetFirewallServiceFilter -ErrorAction Stop)
    $security = @($rule | Get-NetFirewallSecurityFilter -ErrorAction Stop)
    $connection = @(Get-NetConnectionProfile -InterfaceIndex 17 -ErrorAction Stop)
    $profile = @(Get-NetFirewallProfile -PolicyStore ActiveStore -Name Public -ErrorAction Stop)
    foreach ($count in @($app.Count,$port.Count,$address.Count,$iface.Count,$type.Count,$service.Count,$security.Count,$connection.Count,$profile.Count)) {
        if ($count -ne 1) { throw 'Existing-permission filter/profile cardinality is not exact' }
    }
    if ($app[0].Program -ine $script:F325ExistingProgram -or [string]$port[0].Protocol -notin @('UDP','17') -or
        (@($port[0].LocalPort) -join '|') -cne 'Any' -or (@($port[0].RemotePort) -join '|') -cne 'Any' -or
        (@($address[0].LocalAddress) -join '|') -cne 'Any' -or (@($address[0].RemoteAddress) -join '|') -cne 'Any' -or
        [string]$connection[0].NetworkCategory -cne 'Public' -or $connection[0].InterfaceIndex -ne 17 -or
        [string]$connection[0].InterfaceAlias -cne 'Ethernet' -or [string]$profile[0].Name -cne 'Public' -or
        [string]$profile[0].Enabled -cne 'True' -or [string]$profile[0].AllowInboundRules -cne 'True' -or
        [string]$profile[0].AllowLocalFirewallRules -cne 'True') {
        throw 'Existing permission program, UDP scope or active Public profile changed'
    }
    $projection = [ordered]@{
        rule_name=([string]$rule.Name).ToLowerInvariant(); enabled=[string]$rule.Enabled
        direction=[string]$rule.Direction; action=[string]$rule.Action; profile=[string]$rule.Profile
        enforcement=[string]$rule.EnforcementStatus; edge=[string]$rule.EdgeTraversalPolicy
        policy_source=[string]$rule.PolicyStoreSource; policy_source_type=[string]$rule.PolicyStoreSourceType
        local_only_mapping=[string]$rule.LocalOnlyMapping; loose_source_mapping=[string]$rule.LooseSourceMapping
        platform=(@($rule.Platform) -join '|'); program=([string]$app[0].Program).ToLowerInvariant()
        program_sha256=(Get-F325PermissionFileSha256 -Path $script:F325ExistingProgram)
        package=[string]$app[0].Package; protocol='UDP'; local_port=(@($port[0].LocalPort) -join '|')
        remote_port=(@($port[0].RemotePort) -join '|'); icmp_type=(@($port[0].IcmpType) -join '|')
        dynamic_target=[string]$port[0].DynamicTarget; local_address=(@($address[0].LocalAddress) -join '|')
        remote_address=(@($address[0].RemoteAddress) -join '|'); interface_alias=(@($iface[0].InterfaceAlias) -join '|')
        interface_type=[string]$type[0].InterfaceType; service=[string]$service[0].Service
        authentication=[string]$security[0].Authentication; encryption=[string]$security[0].Encryption
        override_block_rules=[string]$security[0].OverrideBlockRules
        security_local_user=(@($security[0].LocalUser) -join '|'); remote_user=(@($security[0].RemoteUser) -join '|')
        remote_machine=(@($security[0].RemoteMachine) -join '|'); connection_profile=[string]$connection[0].NetworkCategory
        connection_interface_index=[string]$connection[0].InterfaceIndex; connection_interface_alias=[string]$connection[0].InterfaceAlias
        firewall_profile_enabled=[string]$profile[0].Enabled; default_inbound=[string]$profile[0].DefaultInboundAction
        default_outbound=[string]$profile[0].DefaultOutboundAction; allow_inbound_rules=[string]$profile[0].AllowInboundRules
        allow_local_rules=[string]$profile[0].AllowLocalFirewallRules; disabled_interfaces=(@($profile[0].DisabledInterfaceAliases) -join '|')
    }
    return [pscustomobject]@{schema='openmitrastar.f326-existing-firewall-observation/v1';
        observed_at_utc=[DateTime]::UtcNow.ToString('o');rule_name=[string]$rule.Name;
        projection=$projection;fingerprint_sha256=(Get-F325PermissionProjectionSha256 -Projection $projection);
        firewall_mutation=$false;privilege_request=$false;network_listener_started=$false}
}
