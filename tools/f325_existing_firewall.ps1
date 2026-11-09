Set-StrictMode -Version Latest
# Read-only use of one permission already present in Windows. This file contains
# no rule creation/removal, privilege request, fallback or firewall policy write.
$script:F325ExistingRuleName = 'UDP Query User{B53A0DF9-DAAE-4615-9572-87C57A3EF67B}/workspace/user-home\appdata\local\programs\python\python312\python.exe'
$script:F325ExistingProgram = '/workspace/user-home\AppData\Local\Programs\Python\Python312\python.exe'
$script:F325ExistingPermissionSha = '4c92fd4156139a0985d8aed2c913e11c91b6c04aef3b35a326aa3efc6ec8bb21'
$script:F325ExistingFingerprint = 'df0c7fac07a2dfae253bd0cef8f4b9a76e8b46b6965ba635be6831ccbbd8270f'

function Get-F325PermissionFileSha256 {
    param([string]$Path)
    $stream=[IO.File]::OpenRead($Path)
    $sha=[Security.Cryptography.SHA256]::Create()
    try { return (-join ($sha.ComputeHash($stream) | ForEach-Object { $_.ToString('x2') })) }
    finally { $sha.Dispose();$stream.Dispose() }
}

function Assert-F325ExistingPermissionPlan {
    param([object]$Plan)
    if ($Plan.network.firewall_mode -cne 'existing-permission') { throw 'Explicit existing-permission mode required' }
    $permission = $Plan.network.existing_permission
    if ($permission -isnot [pscustomobject] -or $permission.sha256 -cne $script:F325ExistingPermissionSha -or
        $permission.fingerprint_sha256 -cne $script:F325ExistingFingerprint -or
        $permission.rule_name -cne $script:F325ExistingRuleName -or
        $permission.python_executable -ine $script:F325ExistingProgram -or
        $permission.program_sha256 -cne '4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a' -or
        $permission.firewall_changes_allowed -isnot [bool] -or $permission.firewall_changes_allowed -or
        $permission.require_administrator -isnot [bool] -or $permission.require_administrator -or
        $permission.fallback_allowed -isnot [bool] -or $permission.fallback_allowed -or
        -not [IO.Path]::IsPathRooted($permission.path)) { throw 'Existing-permission plan binding mismatch' }
    $file = [IO.FileInfo]::new($permission.path)
    if (-not $file.Exists -or $file.Length -gt 32768 -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        (Get-F325PermissionFileSha256 -Path $file.FullName) -cne $script:F325ExistingPermissionSha) {
        throw 'Pinned existing-permission record changed'
    }
}

function Assert-F325ExistingPermission {
    param([object]$Plan)
    Assert-F325ExistingPermissionPlan -Plan $Plan
    $snapshot = Get-F325ExistingPermissionSnapshot -Plan $Plan
    if ($snapshot.fingerprint_sha256 -cne $script:F325ExistingFingerprint) {
        throw 'Existing Windows permission, executable or active profile changed'
    }
    return $snapshot
}

function Get-F325PermissionProjectionSha256 {
    param([System.Collections.IDictionary]$Projection)
    [string[]]$names = @($Projection.Keys)
    [Array]::Sort($names, [StringComparer]::Ordinal)
    $lines = @($names | ForEach-Object {
        $_ + '=' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes([string]$Projection[$_]))
    })
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return (-join ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(($lines -join "`n"))) | ForEach-Object { $_.ToString('x2') })) }
    finally { $sha.Dispose() }
}

function Get-F325ExistingPermissionSnapshot {
    param([object]$Plan)
    if ($Plan.network.server_ipv4 -cne '192.168.1.49' -or $Plan.network.interface_index -ne 18 -or
        $Plan.network.interface_alias -cne 'Ethernet' -or $Plan.network.python_executable -ine $script:F325ExistingProgram) {
        throw 'Existing permission is bound to exact Python312 and Ethernet .49/18'
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
    $connection = @(Get-NetConnectionProfile -InterfaceIndex 18 -ErrorAction Stop)
    $profile = @(Get-NetFirewallProfile -PolicyStore ActiveStore -Name Public -ErrorAction Stop)
    foreach ($count in @($app.Count,$port.Count,$address.Count,$iface.Count,$type.Count,$service.Count,$security.Count,$connection.Count,$profile.Count)) {
        if ($count -ne 1) { throw 'Existing-permission filter/profile cardinality is not exact' }
    }
    if ($app[0].Program -ine $script:F325ExistingProgram -or [string]$port[0].Protocol -notin @('UDP','17') -or
        (@($port[0].LocalPort) -join '|') -cne 'Any' -or (@($port[0].RemotePort) -join '|') -cne 'Any' -or
        (@($address[0].LocalAddress) -join '|') -cne 'Any' -or (@($address[0].RemoteAddress) -join '|') -cne 'Any' -or
        [string]$connection[0].NetworkCategory -cne 'Public' -or $connection[0].InterfaceIndex -ne 18 -or
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
