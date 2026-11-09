Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f325_mtd4_runtime.ps1')
. (Join-Path $PSScriptRoot 'f325_existing_firewall.ps1')
$script:F325EthernetRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not (Get-Variable F325EthernetUncertain -Scope Script -ErrorAction SilentlyContinue)) {
    $script:F325EthernetUncertain = $false
}

function Test-F325EthernetUncertain {
    return ($script:F321ContainmentFailed -or $script:F325SshContainmentFailed -or $script:F325EthernetUncertain)
}

function Test-F325EthernetAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    try { return ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) }
    finally { $identity.Dispose() }
}

function Get-F325EthernetBytesSha256 {
    param([byte[]]$Bytes)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return (-join ($sha.ComputeHash($Bytes) | ForEach-Object { $_.ToString('x2') })) }
    finally { $sha.Dispose() }
}

function Write-F325EthernetJson {
    param([string]$Path, [object]$Value)
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($Value | ConvertTo-Json -Depth 16) + "`n")
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    } finally { $stream.Dispose() }
}

function Invoke-F325EthernetPlanProcess {
    param([string[]]$Arguments)
    # File-only planning has no hardware Job, lease or host-network inspection.
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = 'python'
    $start.Arguments = (($Arguments | ForEach-Object { ConvertTo-F319NativeArgument $_ }) -join ' ')
    $start.UseShellExecute = $false; $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true; $start.RedirectStandardError = $true
    $start.WorkingDirectory = $script:F325EthernetRoot
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $start
    $started = $false
    try {
        if (-not $process.Start()) { throw 'Ethernet plan process did not start' }
        $started = $true
        $stdout = $process.StandardOutput.ReadToEndAsync(); $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(180000)) { throw 'File-only Ethernet plan timed out' }
        if (-not [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($stdout,$stderr),5000)) { throw 'Plan output did not close' }
        if ($process.ExitCode -ne 0) { throw ('Ethernet plan refused: ' + $stderr.GetAwaiter().GetResult()) }
        return $stdout.GetAwaiter().GetResult()
    } finally {
        try {
            if ($started -and -not $process.HasExited) {
                $process.Kill()
                if (-not $process.WaitForExit(5000)) { $script:F325EthernetUncertain=$true; throw 'Plan process exit unproved' }
            }
        } catch { $script:F325EthernetUncertain=$true; throw }
        finally { $process.Dispose() }
    }
}

function Get-F325EthernetPlan {
    param([ValidateSet('promote','rollback')][string]$Direction = 'promote',
        [string]$ServerIp = '192.168.1.49', [int]$InterfaceIndex = 18,
        [string]$ExecutorReview = '', [string]$ExecutorReviewSha256 = '',
        [string]$NetworkAuthorization = '', [string]$NetworkAuthorizationSha256 = '',
        [ValidateSet('temporary-scoped-rule','existing-permission')][string]$FirewallMode='temporary-scoped-rule',
        [string]$ExistingPermission='', [string]$ExistingPermissionSha256='')
    $arguments = @((Join-Path $script:F325EthernetRoot 'tools/f325_ethernet_execution_contract.py'),
        '--direction',$Direction,'--server-ip',$ServerIp,'--interface-index',[string]$InterfaceIndex,'--firewall-mode',$FirewallMode)
    if ($ExecutorReview -or $ExecutorReviewSha256) { $arguments += @('--executor-review',$ExecutorReview,'--executor-review-sha256',$ExecutorReviewSha256) }
    if ($NetworkAuthorization -or $NetworkAuthorizationSha256) { $arguments += @('--network-authorization',$NetworkAuthorization,'--network-authorization-sha256',$NetworkAuthorizationSha256) }
    if ($ExistingPermission -or $ExistingPermissionSha256) { $arguments += @('--existing-permission',$ExistingPermission,'--existing-permission-sha256',$ExistingPermissionSha256) }
    return ((Invoke-F325EthernetPlanProcess -Arguments $arguments) | ConvertFrom-Json)
}

function Assert-F325EthernetExecutionRequest {
    param([object]$Plan, [string]$Ack, [string]$Port = 'COM3',
        [string]$ExpectedPnpDeviceId = 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000',
        [string]$RouterHost = '192.168.1.90')
    if ($Plan.direction -ceq 'promote') {
        $expectedAck='OPENMITRASTAR_F334_MTD4_E18B221D'; $sha='e18b221dda9a61bd1066c155c0cd7b44aef0d0fe06b1a1752a7e759e7730c7ec'; $bytes=5332992
    } elseif ($Plan.direction -ceq 'rollback') {
        $expectedAck='OPENMITRASTAR_F325_RESTORE_F321_EB8E23AC'; $sha='eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18'; $bytes=5337088
    } else { throw 'Only exact F325 promotion and F321 restoration are allowed' }
    if ($Ack -cne $expectedAck -or $Plan.required_ack -cne $expectedAck) { throw 'Exact Ethernet action ACK required before effects' }
    if ($Plan.schema -cne 'openmitrastar.f325-ethernet-plan/v1' -or $Plan.image.sha256 -cne $sha -or $Plan.image.bytes -ne $bytes) { throw 'Ethernet image/plan mismatch' }
    foreach ($field in @('executor_review_verified','network_authorization_verified','local_preflight_pass')) {
        if ($Plan.$field -isnot [bool] -or -not $Plan.$field) { throw 'Exact review, owner network record and preflight required' }
    }
    if ($Port -ine 'COM3' -or $ExpectedPnpDeviceId -ine 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -or
        $Plan.uart_pnp_device_id -ine $ExpectedPnpDeviceId -or $RouterHost -cne '192.168.1.90' -or $Plan.target_host -cne $RouterHost) { throw 'Ethernet target identity mismatch' }
    if ($Plan.transport -cne 'ethernet-tftp' -or $Plan.write_target -cne 'mtd4/linux_live' -or
        $Plan.offset -cne '0x007e0000' -or $Plan.erase_bytes -ne 0x5e0000 -or $Plan.slot_bytes -ne 0x7a0000 -or
        $Plan.radio_actions_authorized -isnot [bool] -or $Plan.radio_actions_authorized) { throw 'Ethernet physical scope mismatch' }
    $network = $Plan.network
    $firewallMode = Get-F325EthernetFirewallMode -Plan $Plan
    if ($firewallMode -ceq 'existing-permission') { Assert-F325ExistingPermissionPlan -Plan $Plan }
    if ($network.server_ipv4 -cne '192.168.1.49' -or $network.client_ipv4 -cne $RouterHost -or
        ($network.interface_index -isnot [int] -and $network.interface_index -isnot [long]) -or $network.interface_index -ne 18 -or
        $network.interface_alias -cne 'Ethernet' -or $network.python_executable -isnot [string] -or
        -not [IO.Path]::IsPathRooted($network.python_executable) -or
        $network.host_address_or_route_changes_allowed -isnot [bool] -or $network.host_address_or_route_changes_allowed -or
        $Plan.network_authorization.sha256 -cne '3e36ac59c12a0ef61d6a0e564be072a91d23b62c98ec28696d5ac2956b32c572' -or
        -not [IO.Path]::IsPathRooted($Plan.network_authorization.path)) { throw 'Recorded Ethernet network scope mismatch' }
}

function Get-F325EthernetFirewallMode {
    param([object]$Plan)
    if (-not $Plan.network.PSObject.Properties['firewall_mode'] -or
        $Plan.network.firewall_mode -cnotin @('temporary-scoped-rule','existing-permission')) {
        throw 'Exact explicit firewall mode is required'
    }
    if ($Plan.network.firewall_mode -ceq 'temporary-scoped-rule' -and
        $Plan.network.PSObject.Properties['existing_permission'] -and $null -ne $Plan.network.existing_permission) {
        throw 'Existing permission cannot be attached to a different firewall mode'
    }
    return $Plan.network.firewall_mode
}

function Assert-F325EthernetFirewallAccess {
    param([object]$Rule, [object]$Plan, [object]$Guard)
    if ((Get-F325EthernetFirewallMode -Plan $Plan) -ceq 'temporary-scoped-rule') {
        Assert-F325EthernetFirewallRule -Rule $Rule -Plan $Plan -Guard $Guard
        return
    }
    if ($Rule.Kind -cne 'existing-permission' -or $Rule.Name -cne $script:F325ExistingRuleName -or
        $Rule.Fingerprint -cne $script:F325ExistingFingerprint -or $Rule.ExecutorOwnsRule -isnot [bool] -or $Rule.ExecutorOwnsRule -or
        $Rule.OwnerPid -ne $PID -or $Guard.OwnerPid -ne $PID -or
        $Rule.OwnerStartTicks -ne $Guard.OwnerStartTicks -or $Rule.LeaseToken -cne $Guard.LeaseToken) {
        throw 'Existing-permission proof is not bound to this physical lease'
    }
    [void](Assert-F325ExistingPermission -Plan $Plan)
}

function Assert-F325EthernetHostNetwork {
    param([object]$Plan)
    $net = $Plan.network
    if (-not (Test-Path -LiteralPath $net.python_executable -PathType Leaf)) { throw 'Pinned Python executable absent' }
    $adapters = @(Get-NetAdapter -IncludeHidden -ErrorAction Stop | Where-Object { $_.ifIndex -eq $net.interface_index })
    if ($adapters.Count -ne 1 -or [string]$adapters[0].Name -cne $net.interface_alias -or
        [string]$adapters[0].Status -cne 'Up' -or [string]$adapters[0].MediaType -cne '802.3') { throw 'Ethernet adapter changed or is not up' }
    $addresses = @(Get-NetIPAddress -InterfaceIndex $net.interface_index -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object { $_.IPAddress -ceq $net.server_ipv4 })
    if ($addresses.Count -ne 1 -or $addresses[0].PrefixLength -ne 24 -or
        [string]$addresses[0].AddressState -cne 'Preferred' -or $addresses[0].SkipAsSource -ne $false) { throw 'Ethernet source address is not the approved preferred address' }
    $selection = @(Find-NetRoute -RemoteIPAddress '192.168.1.90' -ErrorAction Stop)
    $source = @($selection | Where-Object { $_.PSObject.Properties['IPAddress'] })
    $route = @($selection | Where-Object { $_.PSObject.Properties['DestinationPrefix'] })
    if ($source.Count -ne 1 -or $route.Count -ne 1 -or $selection.Count -ne 2 -or
        $source[0].IPAddress -cne $net.server_ipv4 -or $source[0].InterfaceIndex -ne $net.interface_index -or
        $route[0].InterfaceIndex -ne $net.interface_index -or $route[0].DestinationPrefix -cne '192.168.1.0/24' -or
        $route[0].NextHop -cne '0.0.0.0') { throw 'Selected HGW route/source changed' }
    $listeners = @(Get-NetUDPEndpoint -ErrorAction Stop | Where-Object { $_.LocalPort -eq 69 })
    if ($listeners.Count -ne 0) { throw 'UDP/69 already occupied; its owner must not be stopped' }
    $defaults = @(Get-NetRoute -AddressFamily IPv4 -ErrorAction Stop | Where-Object {
        $_.InterfaceIndex -eq $net.interface_index -and $_.DestinationPrefix -eq '0.0.0.0/0' })
    return [pscustomobject]@{schema='openmitrastar.f325-ethernet-host-check/v1';observed_at_utc=[DateTime]::UtcNow.ToString('o');
        server_ipv4=$net.server_ipv4;target_host='192.168.1.90';interface_index=$net.interface_index;
        interface_alias=$net.interface_alias;direct_route=$true;udp69_empty=$true;shared_default_route=($defaults.Count -gt 0);network_mutation=$false}
}

function Invoke-F325EthernetBaseline {
    param([object]$Plan, [string]$RunDir)
    $version = $Plan.current.version
    if ($version -cnotin @('lyoko-foundation-6.8.5-f321-classic-ui-f314-device','lyoko-foundation-6.9.5-f334-radar-once-f321-device')) { throw 'Unsupported baseline version' }
    $known = Join-Path $Plan.current.directory $Plan.current.known_hosts
    if (-not (Test-Path -LiteralPath $known -PathType Leaf)) { throw 'Baseline pinned SSH identity missing' }
    $ssh = Join-Path $env:WINDIR 'System32/OpenSSH/ssh.exe'
    $arguments = @('-i',(Join-Path $env:USERPROFILE '.ssh/id_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
        '-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o',("UserKnownHostsFile="+$known),'-o','LogLevel=ERROR','root@192.168.1.90','sh','-s')
    $command = "grep -Fqx 'OPENMITRASTAR_PRODUCT_VERSION=$version' /etc/openmitrastar/release && printf '%s\n' 'OMF325_ETHERNET_BASELINE_PASS'"
    $result = Invoke-F319SshScript -SshPath $ssh -Arguments $arguments -Script $command -TimeoutSeconds 15
    if ($result.ExitCode -ne 0 -or $result.Stdout.Trim() -cne 'OMF325_ETHERNET_BASELINE_PASS') { throw 'Pinned read-only SSH baseline did not pass' }
    Write-F325EthernetJson -Path (Join-Path $RunDir 'ssh-baseline.json') -Value @{host='192.168.1.90';version=$version;status='PASS';console_nonce_emitted=$false}
}

function Get-F325EthernetExactFirewallRule {
    param([string]$Name)
    $lookupErrors = @()
    $rules = @(Get-NetFirewallRule -PolicyStore PersistentStore -Name $Name -ErrorAction SilentlyContinue -ErrorVariable lookupErrors)
    foreach ($errorRecord in $lookupErrors) {
        if ([string]$errorRecord.CategoryInfo.Category -ne 'ObjectNotFound') { throw 'Firewall rule lookup could not be completed' }
    }
    return $rules
}

function Assert-F325EthernetFirewallOwner {
    param([object]$Rule, [object]$Guard)
    if ($Rule.Name -cnotmatch '^OpenMitraStar-F325-Ethernet-[0-9a-f]{32}$' -or $Rule.OwnerPid -ne $PID -or
        $Guard.OwnerPid -ne $PID -or $Rule.OwnerStartTicks -ne $Guard.OwnerStartTicks -or $Rule.LeaseToken -cne $Guard.LeaseToken) {
        throw 'Firewall rule is not owned by this live physical cycle'
    }
}

function Assert-F325EthernetFirewallRule {
    param([object]$Rule, [object]$Plan, [object]$Guard)
    Assert-F325EthernetFirewallOwner -Rule $Rule -Guard $Guard
    $rows = @(Get-F325EthernetExactFirewallRule -Name $Rule.Name)
    if ($rows.Count -ne 1 -or $rows[0].Name -cne $Rule.Name -or $rows[0].Description -cne $Rule.Description -or
        [string]$rows[0].Enabled -cne 'True' -or [string]$rows[0].Direction -cne 'Inbound' -or
        [string]$rows[0].Action -cne 'Allow' -or [string]$rows[0].Profile -cne 'Any' -or
        [string]$rows[0].EdgeTraversalPolicy -cne 'Block') { throw 'Owned firewall rule not confirmed' }
    $ports = @($rows[0] | Get-NetFirewallPortFilter -ErrorAction Stop)
    $addresses = @($rows[0] | Get-NetFirewallAddressFilter -ErrorAction Stop)
    $programs = @($rows[0] | Get-NetFirewallApplicationFilter -ErrorAction Stop)
    $interfaces = @($rows[0] | Get-NetFirewallInterfaceFilter -ErrorAction Stop)
    if ($ports.Count -ne 1 -or [string]$ports[0].Protocol -notin @('UDP','17') -or
        (@($ports[0].LocalPort) -join '|') -cne '69' -or (@($ports[0].RemotePort) -join '|') -cne 'Any' -or
        $addresses.Count -ne 1 -or (@($addresses[0].LocalAddress) -join '|') -cne $Plan.network.server_ipv4 -or
        (@($addresses[0].RemoteAddress) -join '|') -cne '192.168.1.90' -or
        $programs.Count -ne 1 -or $programs[0].Program -ine $Plan.network.python_executable -or
        $interfaces.Count -ne 1 -or (@($interfaces[0].InterfaceAlias) -join '|') -cne $Plan.network.interface_alias) {
        throw 'Firewall address, port, program or interface scope differs'
    }
}

function Remove-F325EthernetFirewallRule {
    param([object]$Rule, [object]$Guard)
    Assert-F325EthernetFirewallOwner -Rule $Rule -Guard $Guard
    $rows = @(Get-F325EthernetExactFirewallRule -Name $Rule.Name)
    if ($rows.Count -gt 1) { throw 'Firewall identity is ambiguous' }
    if ($rows.Count -eq 1) {
        if ($rows[0].Name -cne $Rule.Name -or $rows[0].Description -cne $Rule.Description) { throw 'Refusing to remove a foreign firewall rule' }
        Remove-NetFirewallRule -PolicyStore PersistentStore -Name $Rule.Name -ErrorAction Stop
    }
    if (@(Get-F325EthernetExactFirewallRule -Name $Rule.Name).Count -ne 0) { throw 'Owned firewall rule removal unproved' }
}

function New-F325EthernetFirewallRule {
    param([object]$Plan, [object]$Guard, [string]$RunDir)
    $name = 'OpenMitraStar-F325-Ethernet-' + [Guid]::NewGuid().ToString('N')
    $rule = [pscustomobject]@{Name=$name;Description=('Temporary exact HGW transfer '+$name);
        OwnerPid=$PID;OwnerStartTicks=$Guard.OwnerStartTicks;LeaseToken=$Guard.LeaseToken}
    if (@(Get-F325EthernetExactFirewallRule -Name $name).Count -ne 0) { throw 'New firewall rule name is already present' }
    Write-F325EthernetJson -Path (Join-Path $RunDir 'firewall-intent.json') -Value @{name=$name;
        local_address=$Plan.network.server_ipv4;remote_address='192.168.1.90';local_port=69;protocol='UDP';
        program=$Plan.network.python_executable;interface_alias=$Plan.network.interface_alias}
    try {
        [void](New-NetFirewallRule -PolicyStore PersistentStore -Name $name -DisplayName $name -Description $rule.Description `
            -Direction Inbound -Action Allow -Enabled True -Profile Any -EdgeTraversalPolicy Block -Protocol UDP -LocalPort 69 -RemotePort Any `
            -LocalAddress $Plan.network.server_ipv4 -RemoteAddress '192.168.1.90' -InterfaceAlias $Plan.network.interface_alias `
            -Program $Plan.network.python_executable -ErrorAction Stop)
        Assert-F325EthernetFirewallRule -Rule $rule -Plan $Plan -Guard $Guard
        return $rule
    } catch {
        try { Remove-F325EthernetFirewallRule -Rule $rule -Guard $Guard }
        catch { $script:F325EthernetUncertain=$true }
        throw
    }
}

function Get-F325EthernetActionArguments {
    param([object]$Plan, [string]$ExecutorReview, [string]$ExecutorReviewSha256)
    if (-not $ExecutorReview -or $ExecutorReviewSha256 -cnotmatch '^[0-9a-f]{64}$') { throw 'Exact Ethernet review arguments required' }
    $arguments = @('--direction',$Plan.direction,'--server-ip',$Plan.network.server_ipv4,'--interface-index',[string]$Plan.network.interface_index,
        '--executor-review',$ExecutorReview,'--executor-review-sha256',$ExecutorReviewSha256,
        '--network-authorization',$Plan.network_authorization.path,'--network-authorization-sha256',$Plan.network_authorization.sha256,
        '--firewall-mode',(Get-F325EthernetFirewallMode -Plan $Plan))
    if ($Plan.network.firewall_mode -ceq 'existing-permission') {
        $arguments += @('--existing-permission',$Plan.network.existing_permission.path,'--existing-permission-sha256',$Plan.network.existing_permission.sha256)
    }
    return $arguments
}

function Read-F325EthernetNativeResult {
    param([object]$Plan, [string]$WriterDir)
    $directory = Get-Item -LiteralPath $WriterDir -ErrorAction Stop
    $path = Join-Path $directory.FullName 'native-loader-result.json'
    $file = Get-Item -LiteralPath $path -ErrorAction Stop
    if (-not $directory.PSIsContainer -or ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        $file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $file.Length -gt 1048576) { throw 'Native result path is not bounded regular evidence' }
    $bytes = [IO.File]::ReadAllBytes($path)
    if ($bytes.Length -gt 1048576) { throw 'Native result changed beyond the bounded size' }
    $value = [Text.UTF8Encoding]::new($false,$true).GetString($bytes) | ConvertFrom-Json
    if ($value.PSObject.Properties['retain_lease_required'] -and $value.retain_lease_required -ne $false) { $script:F325EthernetUncertain=$true }
    if ($value.PSObject.Properties['native_cleanup_verified'] -and $value.native_cleanup_verified -ne $true) { $script:F325EthernetUncertain=$true }
    if ($value.schema -cne 'openmitrastar.f325-native-ethernet-load/v1' -or $value.status -cne 'PASS_NATIVE_ETHERNET_RAM_LOAD' -or
        $value.candidate_sha256 -cne $Plan.image.sha256 -or $value.candidate_bytes -ne $Plan.image.bytes -or
        $value.target_host -cne '192.168.1.90' -or $value.server_ipv4 -cne $Plan.network.server_ipv4) { throw 'Native loader did not prove the exact image/host' }
    foreach ($field in @('ram_handoff_ready','native_cleanup_verified')) {
        if ($value.$field -isnot [bool] -or -not $value.$field) { throw 'Native loader RAM/cleanup gate unresolved' }
    }
    foreach ($field in @('writer_ready','retain_lease_required','flash_written','rebooted','host_network_or_firewall_changed','loader_process_exit_observed_by_parent')) {
        if ($value.$field -isnot [bool] -or $value.$field) { throw 'Native loader overclaims readiness or changed scope' }
    }
    foreach ($field in @('server','uart','guard_helpers')) {
        if ($value.cleanup.$field -isnot [bool] -or -not $value.cleanup.$field) { $script:F325EthernetUncertain=$true; throw 'Native adapter cleanup incomplete' }
    }
    $ram=$value.ram_result
    if ($ram.status -cne 'PASS_ETHERNET_RAM_GATE' -or $ram.candidate_sha256 -cne $Plan.image.sha256 -or
        $ram.candidate_bytes -ne $Plan.image.bytes -or $ram.candidate_crc32 -cne $Plan.preflight.candidate_crc32 -or
        $ram.server_closed -isnot [bool] -or -not $ram.server_closed -or $ram.flash_writes -ne 0) { throw 'Native RAM identity/integrity proof missing' }
    return [pscustomobject]@{Value=$value;Path=$path;Sha256=(Get-F325EthernetBytesSha256 -Bytes $bytes)}
}

function Invoke-F325EthernetWritePhase {
    param([object]$Plan, [string]$RunDir, [int]$FlashTimeoutSeconds = 1800,
        [string]$ExecutorReview, [string]$ExecutorReviewSha256)
    if ((Get-F325EthernetFirewallMode -Plan $Plan) -ceq 'existing-permission') {
        Write-F325EthernetJson -Path (Join-Path $RunDir 'existing-permission-before-transfer.json') -Value (Assert-F325ExistingPermission -Plan $Plan)
    }
    $writerDir = Join-Path $RunDir 'writer'
    if (Test-Path -LiteralPath $writerDir) { throw 'Fresh writer directory required; loader creates it' }
    $common = @(Get-F325EthernetActionArguments -Plan $Plan -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256)
    $savedPreloaded = [Environment]::GetEnvironmentVariable('OM_F325_ETHERNET_PRELOADED','Process')
    $saved = Set-F321WriterEnvironment -Plan $Plan
    try {
        [Environment]::SetEnvironmentVariable('OM_F325_ETHERNET_PRELOADED',$null,'Process')
        $loaderArgs = @((Join-Path $script:F325EthernetRoot 'tools/f325_ethernet_load_cli.py'),'--execute') + $common + @('--output-dir',$writerDir)
        [void](Invoke-F321Native -Program $Plan.network.python_executable -Arguments $loaderArgs -LogPrefix (Join-Path $RunDir 'ethernet-loader-process') -TimeoutSeconds 900)
        if (Test-F325EthernetUncertain) { throw 'Loader process/Job closure unproved' }
        $native = Read-F325EthernetNativeResult -Plan $Plan -WriterDir $writerDir
        if ([string]::IsNullOrWhiteSpace($env:OM_F325_PHYSICAL_CONTEXT)) { throw 'Physical context missing after loader exit' }
        $preloaded = [ordered]@{schema='openmitrastar.f325-ethernet-preloaded/v1';direction=$Plan.direction;
            candidate_sha256=$Plan.image.sha256;native_result_path=$native.Path;native_result_sha256=$native.Sha256;
            physical_context_sha256=(Get-F325EthernetBytesSha256 -Bytes ([Text.UTF8Encoding]::new($false).GetBytes($env:OM_F325_PHYSICAL_CONTEXT)));
            loader_job_closed=$true}
        $env:OM_F325_ETHERNET_PRELOADED = $preloaded | ConvertTo-Json -Compress
        $writerArgs = @((Join-Path $script:F325EthernetRoot 'tools/f325_ethernet_writer.py'),'--execute') + $common +
            @('--evidence-dir',$writerDir,'--ack',$Plan.required_ack,'--timeout',[string]$FlashTimeoutSeconds)
        [void](Invoke-F321Native -Program $Plan.network.python_executable -Arguments $writerArgs -LogPrefix (Join-Path $RunDir 'ethernet-writer-process') -TimeoutSeconds ($FlashTimeoutSeconds+600))
        if (Test-F325EthernetUncertain) { throw 'Writer process/Job closure unproved' }
        $verifyArgs = @((Join-Path $script:F325EthernetRoot 'tools/f325_ethernet_execution_contract.py')) + $common + @('--verify-writer',$writerDir)
        $verified = Invoke-F321Native -Program $Plan.network.python_executable -Arguments $verifyArgs -TimeoutSeconds 180
        $proof = $verified | ConvertFrom-Json
        if ($proof.status -cne 'PASS_VERIFIED_ETHERNET_WRITER' -or $proof.candidate_sha256_expected -cne $Plan.image.sha256) { throw 'Exact Ethernet writer proof missing' }
        Write-F325EthernetJson -Path (Join-Path $RunDir 'verified-writer.json') -Value $proof
        return $proof
    } finally {
        try { Restore-F321WriterEnvironment -Saved $saved }
        finally { [Environment]::SetEnvironmentVariable('OM_F325_ETHERNET_PRELOADED',$savedPreloaded,'Process') }
    }
}

function Invoke-F325EthernetPhysicalCycle {
    param([object]$Plan, [string]$RunDir, [int]$FlashTimeoutSeconds = 1800,
        [string]$ExecutorReview = '', [string]$ExecutorReviewSha256 = '',
        [object]$BorrowedHardwareGuard = $null, [object]$RecoveryBindingProof = $null,
        [object]$BorrowedFirewallRule = $null, [switch]$CaptureAndRestore)
    $guard=$null; $firewall=$null; $owned=$false; $firewallOwned=$false; $writerVerified=$false; $bindingProof=$null; $failed=$false; $stage='request'; $recoveryAttempted=$false
    $firewallMode=$null; $existingInitial=$null; $permissionPlanArgs=@{}
    $savedContext=[Environment]::GetEnvironmentVariable('OM_F325_PHYSICAL_CONTEXT','Process')
    $savedPreloaded=[Environment]::GetEnvironmentVariable('OM_F325_ETHERNET_PRELOADED','Process')
    $result=[ordered]@{schema='openmitrastar.f325-ethernet-physical-cycle/v1';direction=$Plan.direction;status='STOP_NO_AUTOMATIC_RETRY';
        candidate_sha256=$Plan.image.sha256;write_target='mtd4/linux_live';transport='ethernet-tftp';writer_verified=$false;
        radio_mutation=$false;release_eligible=$false;automatic_recovery_started=$false;firewall_cleanup_verified=$false;
        host_addresses_or_routes_changed=$false;firewall_disabled=$false;failed_stage=$null}
    try {
        Assert-F325EthernetExecutionRequest -Plan $Plan -Ack $Plan.required_ack
        $firewallMode=Get-F325EthernetFirewallMode -Plan $Plan
        $result.firewall_mode=$firewallMode
        $permissionPlanArgs=@{FirewallMode=$firewallMode}
        if ($firewallMode -ceq 'existing-permission') {
            $permissionPlanArgs.ExistingPermission=$Plan.network.existing_permission.path
            $permissionPlanArgs.ExistingPermissionSha256=$Plan.network.existing_permission.sha256
            $result.firewall_changes=$false
            $result.privilege_requested=$false
        }
        if ($Plan.direction -ceq 'rollback') {
            $stage='conditional-rollback'
            # The recorded F321 recovery is conditional on the promoter's
            # verified write and failed postgate, with its same live resources.
            # This is not an independently authorized fresh restore entrypoint.
            if ($BorrowedHardwareGuard -isnot [pscustomobject] -or
                $RecoveryBindingProof -isnot [pscustomobject] -or
                $BorrowedFirewallRule -isnot [pscustomobject]) {
                throw 'Conditional F321 restoration requires the borrowed lease, original binding and firewall rule'
            }
        }
        if (Test-F325EthernetUncertain) { throw 'Earlier containment/cleanup remains unresolved' }
        if ($firewallMode -ceq 'temporary-scoped-rule') {
            $stage='administrator'
            if ((Test-F325EthernetAdministrator) -ne $true) { throw 'Elevated execution is required for the selected temporary firewall rule' }
        } else {
            $stage='existing-permission-before-hardware'
            $existingInitial=Assert-F325ExistingPermission -Plan $Plan
            Write-F325EthernetJson -Path (Join-Path $RunDir 'existing-permission-before-hardware.json') -Value $existingInitial
        }
        [void](Get-F325EthernetActionArguments -Plan $Plan -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256)
        $stage='host-network'
        $hostProof = Assert-F325EthernetHostNetwork -Plan $Plan
        Write-F325EthernetJson -Path (Join-Path $RunDir 'host-network.json') -Value $hostProof
        $stage='recovery-evidence'
        [void](Get-F319VerifiedRecoveryRehearsal -ResultPath $Plan.recovery_rehearsal)
        if (($null -eq $BorrowedHardwareGuard) -ne ($null -eq $RecoveryBindingProof) -or
            ($BorrowedFirewallRule -and -not $BorrowedHardwareGuard)) { throw 'Incomplete borrowed recovery scope' }
        if ($BorrowedHardwareGuard) {
            $stage='borrowed-lease'
            if ($Plan.direction -cne 'rollback') { throw 'Only F321 restoration may borrow ownership' }
            Assert-F325BorrowedRecoveryGuard -Guard $BorrowedHardwareGuard -BindingProof $RecoveryBindingProof -ExpectedPnpDeviceId $Plan.uart_pnp_device_id
            $guard=$BorrowedHardwareGuard; $bindingProof=$RecoveryBindingProof
        } else {
            $stage='ssh-baseline'
            Invoke-F325EthernetBaseline -Plan $Plan -RunDir $RunDir
            $stage='lease'
            $guard=Enter-F319HardwareGuard -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id -PhysicalLockDir $Plan.physical_lock -Owner ('f325-ethernet-'+$Plan.direction) -EvidenceDir $RunDir
            $owned=$true
            $stage='binding'
            $binding=Assert-F319UartBinding -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id -RouterHost '192.168.1.90' `
                -KnownHosts (Join-Path $Plan.current.directory $Plan.current.known_hosts) -ExpectedVersion $Plan.current.version -HardwareLease $guard
            $bindingProof=[pscustomobject]@{OwnerPid=$guard.OwnerPid;OwnerStartTicks=$guard.OwnerStartTicks;LeaseToken=$guard.LeaseToken;Binding=$binding}
        }
        $stage='lease-check'
        [void](Assert-F319HardwareLease -PhysicalLockDir $guard.PhysicalLockDir -OwnerPid $guard.OwnerPid -OwnerStartTicks $guard.OwnerStartTicks `
            -LeaseToken $guard.LeaseToken -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id)
        $stage='firewall'
        if ($BorrowedFirewallRule) {
            Assert-F325EthernetFirewallAccess -Rule $BorrowedFirewallRule -Plan $Plan -Guard $guard
            $firewall=$BorrowedFirewallRule
        } elseif ($firewallMode -ceq 'existing-permission') {
            $firewall=[pscustomobject]@{Kind='existing-permission';Name=$script:F325ExistingRuleName;
                Fingerprint=$script:F325ExistingFingerprint;ExecutorOwnsRule=$false;
                OwnerPid=$PID;OwnerStartTicks=$guard.OwnerStartTicks;LeaseToken=$guard.LeaseToken}
            Assert-F325EthernetFirewallAccess -Rule $firewall -Plan $Plan -Guard $guard
        } else {
            $firewall=New-F325EthernetFirewallRule -Plan $Plan -Guard $guard -RunDir $RunDir
            $firewallOwned=$true
        }
        $result.firewall_rule_name=$firewall.Name
        $stage='physical-context'
        $env:OM_F325_PHYSICAL_CONTEXT=Create-F325PhysicalContext -Guard $guard -BindingProof $bindingProof -CandidateSha256 $Plan.image.sha256 -Direction $Plan.direction
        [Environment]::SetEnvironmentVariable('OM_F325_ETHERNET_PRELOADED',$null,'Process')
        $stage='reboot'
        Invoke-F325Reboot -Plan $Plan -RunDir $RunDir
        $stage='write'
        $result.writer=Invoke-F325EthernetWritePhase -Plan $Plan -RunDir $RunDir -FlashTimeoutSeconds $FlashTimeoutSeconds -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256
        if ($result.writer.status -cne 'PASS_VERIFIED_ETHERNET_WRITER' -or (Test-F325EthernetUncertain)) { throw 'Writer outcome or containment unknown' }
        $writerVerified=$true; $result.writer_verified=$true
        $stage='platform'
        Invoke-F321PlatformGate -Plan $Plan -RunDir $RunDir
        $stage='postbinding'
        [void](Assert-F319UartBinding -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id -RouterHost '192.168.1.90' `
            -KnownHosts (Join-Path $Plan.image.directory $Plan.image.known_hosts) -ExpectedVersion $Plan.image.version -HardwareLease $guard)
        $stage='ui'
        Invoke-F325UiGate -Plan $Plan -RunDir $RunDir
        $result.status=if ($Plan.direction -ceq 'promote') {'PASS_F325_ETHERNET_BOOT_PLATFORM_HTTP'} else {'PASS_EXACT_F321_RESTORED'}
        if ($CaptureAndRestore) {
            if ($Plan.direction -cne 'promote') { throw 'Only promotion can initiate the one-boot diagnostic' }
            $stage='capture'
            $result.radio_mutation_attempted=$true
            $result.radio_mutation=$null
            $result.capture=Invoke-F325CaptureGate -Plan $Plan -RunDir $RunDir
            $result.radio_mutation=$true
            $stage='planned-f321-restoration'
            $rollback=Get-F325EthernetPlan @permissionPlanArgs -Direction rollback -ServerIp $Plan.network.server_ipv4 -InterfaceIndex $Plan.network.interface_index `
                -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256 `
                -NetworkAuthorization $Plan.network_authorization.path -NetworkAuthorizationSha256 $Plan.network_authorization.sha256
            Assert-F325EthernetExecutionRequest -Plan $rollback -Ack $rollback.required_ack
            $rollbackDir=Join-Path $RunDir 'planned-exact-f321-rollback'
            if (Test-Path -LiteralPath $rollbackDir) { throw 'Recovery evidence already exists' }
            [void][IO.Directory]::CreateDirectory($rollbackDir)
            $recoveryAttempted=$true; $result.automatic_recovery_started=$true
            $restored=Invoke-F325EthernetPhysicalCycle -Plan $rollback -RunDir $rollbackDir -FlashTimeoutSeconds $FlashTimeoutSeconds `
                -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256 `
                -BorrowedHardwareGuard $guard -RecoveryBindingProof $bindingProof -BorrowedFirewallRule $firewall
            if ($restored.status -cne 'PASS_EXACT_F321_RESTORED') { throw 'Mandatory F321 restoration unproved' }
            $result.status='PASS_DIAGNOSTIC_COMPLETED_F321_RESTORED'
        }
    } catch {
        $failed=$true; $result.status='STOP_NO_AUTOMATIC_RETRY'; $result.failed_stage=$stage; $result.error_type=$_.Exception.GetType().Name
        if ($Plan.direction -ceq 'promote' -and -not $recoveryAttempted -and $writerVerified -and $guard -and $bindingProof -and $firewall -and -not (Test-F325EthernetUncertain)) {
            try {
                [void](Assert-F319HardwareLease -PhysicalLockDir $guard.PhysicalLockDir -OwnerPid $guard.OwnerPid -OwnerStartTicks $guard.OwnerStartTicks `
                    -LeaseToken $guard.LeaseToken -Port 'COM3' -ExpectedPnpDeviceId $Plan.uart_pnp_device_id)
                Assert-F325EthernetFirewallAccess -Rule $firewall -Plan $Plan -Guard $guard
                $rollback=Get-F325EthernetPlan @permissionPlanArgs -Direction rollback -ServerIp $Plan.network.server_ipv4 -InterfaceIndex $Plan.network.interface_index `
                    -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256 `
                    -NetworkAuthorization $Plan.network_authorization.path -NetworkAuthorizationSha256 $Plan.network_authorization.sha256
                Assert-F325EthernetExecutionRequest -Plan $rollback -Ack $rollback.required_ack
                $rollbackDir=Join-Path $RunDir 'automatic-exact-f321-rollback'
                if (Test-Path -LiteralPath $rollbackDir) { throw 'Recovery evidence already exists' }
                [void][IO.Directory]::CreateDirectory($rollbackDir)
                $result.automatic_recovery_started=$true
                $recoveryAttempted=$true
                $restored=Invoke-F325EthernetPhysicalCycle -Plan $rollback -RunDir $rollbackDir -FlashTimeoutSeconds $FlashTimeoutSeconds `
                    -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256 `
                    -BorrowedHardwareGuard $guard -RecoveryBindingProof $bindingProof -BorrowedFirewallRule $firewall
                if ($restored.status -cne 'PASS_EXACT_F321_RESTORED') { throw 'Exact F321 restoration unproved' }
                $result.status='FAIL_F325_EXACT_F321_RESTORED'
            } catch { $result.status='STOP_NO_AUTOMATIC_RETRY'; $result.recovery_error_type=$_.Exception.GetType().Name }
        }
    } finally {
        try {
            [Environment]::SetEnvironmentVariable('OM_F325_PHYSICAL_CONTEXT',$savedContext,'Process')
            [Environment]::SetEnvironmentVariable('OM_F325_ETHERNET_PRELOADED',$savedPreloaded,'Process')
        } catch { $script:F325EthernetUncertain=$true; $failed=$true }
        try {
            if ($firewallMode -ceq 'existing-permission' -and $null -ne $existingInitial) {
                $existingFinal=Assert-F325ExistingPermission -Plan $Plan
                if ($existingFinal.fingerprint_sha256 -cne $existingInitial.fingerprint_sha256) { throw 'Existing permission changed during the physical cycle' }
                Write-F325EthernetJson -Path (Join-Path $RunDir 'existing-permission-after.json') -Value $existingFinal
                $result.existing_permission_unchanged=$true
                $result.firewall_cleanup_verified=$true
                $result.firewall_cleanup_deferred_to_owner=$false
            } else {
                if ($firewallOwned) { Remove-F325EthernetFirewallRule -Rule $firewall -Guard $guard }
                $result.firewall_cleanup_verified=($firewallOwned -or $null -eq $firewall)
                $result.firewall_cleanup_deferred_to_owner=($null -ne $firewall -and -not $firewallOwned)
            }
        } catch {
            $script:F325EthernetUncertain=$true; $failed=$true; $result.firewall_cleanup_verified=$false
            $result.cleanup_failed_stage='firewall-cleanup'; if (-not $result.failed_stage) {$result.failed_stage='firewall-cleanup'}
        }
        $result.lease_released=$false
        $result.lease_release_deferred_to_owner=(-not $owned -and $null -ne $guard)
        # Preserve the completed physical/cleanup evidence before surrendering
        # ownership. The final result below additionally records release outcome.
        if ($owned -and -not (Test-F325EthernetUncertain)) {
            try { Write-F325EthernetJson -Path (Join-Path $RunDir 'cleanup-before-release.json') -Value $result }
            catch { $script:F325EthernetUncertain=$true; $failed=$true; $result.cleanup_failed_stage='pre-release-evidence' }
        }
        if ($owned -and -not (Test-F325EthernetUncertain)) {
            try { Exit-F319HardwareGuard -Guard $guard; $result.lease_released=$true }
            catch {
                $script:F325EthernetUncertain=$true; $failed=$true; $result.cleanup_failed_stage='lease-release'
                if (-not $result.failed_stage) {$result.failed_stage='lease-release'}
            }
        }
        $result.helper_containment_verified=-not (Test-F325EthernetUncertain)
        $result.retain_lease_required=Test-F325EthernetUncertain
        if (Test-F325EthernetUncertain) { $result.status='STOP_NO_AUTOMATIC_RETRY'; $failed=$true }
        try { Write-F325EthernetJson -Path (Join-Path $RunDir 'result.json') -Value $result }
        catch { $script:F325EthernetUncertain=$true; $failed=$true }
    }
    if ($failed) { throw 'F325 Ethernet cycle stopped; inspect this run evidence before any further action' }
    return [pscustomobject]$result
}

function Invoke-F325CaptureGate {
    param([object]$Plan,[string]$RunDir)
    $out=Join-Path $RunDir 'capture'
    [void](Invoke-F321Native -Program 'python' -Arguments @((Join-Path $script:F325EthernetRoot 'tools/run_f325_capture.py'),
        '--execute','--output-dir',$out) -LogPrefix (Join-Path $RunDir 'capture-process') -TimeoutSeconds 200)
    $result=Get-Content -LiteralPath (Join-Path $out 'result.json') -Raw | ConvertFrom-Json
    if ($result.status -cnotin @('CAPTURE_ACTIVITY_OBSERVED','INCONCLUSIVE_NO_PULSES') -or
        $result.hardware_restore_proven -ne $false -or $result.physical_radar_detection_proven -ne $false) {
        throw 'F325 capture failed or overclaimed physical acceptance'
    }
    return $result
}
