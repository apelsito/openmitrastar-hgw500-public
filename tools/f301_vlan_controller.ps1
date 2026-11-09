[CmdletBinding()]
param(
    [ValidateSet('Audit', 'Snapshot', 'Apply', 'Restore', 'Watchdog')]
    [string]$Action = 'Audit',
    [string]$InterfaceAlias = '',
    [string]$SnapshotPath = '',
    [string]$StateDirectory = '',
    [ValidateRange(60, 900)]
    [int]$TimeoutSeconds = 300,
    [string]$VlanAddress = '10.254.90.2',
    [ValidateRange(1, 32)]
    [int]$PrefixLength = 30,
    [ValidateRange(1, 4094)]
    [int]$VlanId = 4090
)

$ErrorActionPreference = 'Stop'

function Write-AtomicJson([string]$Path, [object]$Payload) {
    $directory = Split-Path -Parent $Path
    if ($directory) { New-Item -ItemType Directory -Force -Path $directory | Out-Null }
    $temporary = $Path + '.tmp'
    [IO.File]::WriteAllText(
        $temporary,
        (($Payload | ConvertTo-Json -Depth 8) + "`n"),
        [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Get-VlanProperty([string]$Alias) {
    $properties = @(
        Get-NetAdapterAdvancedProperty -Name $Alias -ErrorAction Stop |
            Where-Object {
                $_.RegistryKeyword -match '^(\*?VlanID|VlanId)$' -or
                $_.DisplayName -match '^(VLAN ID|VLAN-ID|802\.1Q VLAN ID)$'
            }
    )
    if ($properties.Count -ne 1) {
        throw "Expected one VLAN ID property on '$Alias'; found $($properties.Count)"
    }
    return $properties[0]
}

function Get-AdapterState([string]$Alias) {
    $adapter = Get-NetAdapter -Name $Alias -Physical -ErrorAction Stop
    $property = Get-VlanProperty $Alias
    $addresses = @(
        Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -ne $VlanAddress } |
            Sort-Object IPAddress |
            ForEach-Object {
                [ordered]@{
                    address = [string]$_.IPAddress
                    prefix_length = [int]$_.PrefixLength
                    prefix_origin = [string]$_.PrefixOrigin
                    suffix_origin = [string]$_.SuffixOrigin
                }
            }
    )
    return [ordered]@{
        schema = 'openmitrastar.f301-vlan-controller-snapshot/v1'
        interface_alias = [string]$adapter.Name
        interface_guid = [string]$adapter.InterfaceGuid
        interface_index = [int]$adapter.ifIndex
        description = [string]$adapter.InterfaceDescription
        status = [string]$adapter.Status
        link_speed = [string]$adapter.LinkSpeed
        vlan_property = [ordered]@{
            registry_keyword = [string]$property.RegistryKeyword
            registry_value = @($property.RegistryValue)
            display_name = [string]$property.DisplayName
            display_value = [string]$property.DisplayValue
        }
        ipv4 = $addresses
        sensitive_identifiers_logged = $false
    }
}

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Read-Snapshot([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
        throw 'SnapshotPath is required and must exist'
    }
    return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
}

function Assert-SnapshotIdentity([object]$Snapshot) {
    $adapter = Get-NetAdapter -Name ([string]$Snapshot.interface_alias) -Physical -ErrorAction Stop
    if ([string]$adapter.InterfaceGuid -ne [string]$Snapshot.interface_guid) {
        throw 'Controller adapter identity changed'
    }
    return $adapter
}

function Wait-AdapterUp([string]$Alias, [int]$Seconds = 45) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    do {
        $adapter = Get-NetAdapter -Name $Alias -ErrorAction SilentlyContinue
        if ($adapter -and $adapter.Status -eq 'Up') { return }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Adapter '$Alias' did not return Up"
}

function Restore-Adapter([object]$Snapshot) {
    $adapter = Assert-SnapshotIdentity $Snapshot
    Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -eq $VlanAddress } |
        Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue

    $keyword = [string]$Snapshot.vlan_property.registry_keyword
    $original = @($Snapshot.vlan_property.registry_value)
    if ($original.Count -eq 0) { throw 'Original VLAN registry value is empty' }
    Set-NetAdapterAdvancedProperty -Name $adapter.Name -RegistryKeyword $keyword `
        -RegistryValue $original -NoRestart:$false -ErrorAction Stop
    Wait-AdapterUp $adapter.Name
    $expectedIpv4 = @($Snapshot.ipv4 | ForEach-Object { "$($_.address)/$($_.prefix_length)" } | Sort-Object)
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    $current = $null
    $currentIpv4 = @()
    do {
        $current = Get-AdapterState $adapter.Name
        $currentIpv4 = @($current.ipv4 | ForEach-Object { "$($_.address)/$($_.prefix_length)" } | Sort-Object)
        if (($currentIpv4 -join ',') -eq ($expectedIpv4 -join ',')) { break }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    $propertyRestored = (@($current.vlan_property.registry_value) -join ',') -eq ($original -join ',')
    $addressAbsent = -not [bool](Get-NetIPAddress -InterfaceIndex $adapter.ifIndex `
        -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -eq $VlanAddress })
    $ipv4Restored = ($currentIpv4 -join ',') -eq ($expectedIpv4 -join ',')
    return [ordered]@{
        schema = 'openmitrastar.f301-vlan-controller-restore/v1'
        restored = ($propertyRestored -and $addressAbsent -and $ipv4Restored)
        interface_alias = $adapter.Name
        vlan_property_restored = $propertyRestored
        vlan_address_absent = $addressAbsent
        ipv4_restored_exactly = $ipv4Restored
        sensitive_identifiers_logged = $false
    }
}

if ($VlanId -ne 4090) { throw 'This gate is pinned to isolated VLAN 4090' }

if ($Action -eq 'Audit') {
    if (-not $InterfaceAlias) { throw 'InterfaceAlias is required for Audit' }
    $state = Get-AdapterState $InterfaceAlias
    $propertyValue = @($state.vlan_property.registry_value) -join ','
    $vlanDisabled = @('', '0', '0x00000000') -contains $propertyValue
    [ordered]@{
        schema = 'openmitrastar.f301-vlan-controller-audit/v1'
        ready = ($state.status -eq 'Up' -and [bool]$state.vlan_property.registry_keyword -and $vlanDisabled)
        administrator = Test-Administrator
        interface = $state
        existing_vlan_value = $propertyValue
        existing_vlan_disabled = $vlanDisabled
        mutation_performed = $false
    } | ConvertTo-Json -Depth 8 -Compress
    exit 0
}

if ($Action -eq 'Snapshot') {
    if (-not $InterfaceAlias -or -not $SnapshotPath) { throw 'InterfaceAlias and SnapshotPath are required' }
    $snapshot = Get-AdapterState $InterfaceAlias
    $snapshot['captured_at'] = [DateTimeOffset]::UtcNow.ToString('o')
    Write-AtomicJson $SnapshotPath $snapshot
    $snapshot | ConvertTo-Json -Depth 8 -Compress
    exit 0
}

if ($Action -eq 'Apply') {
    if (-not (Test-Administrator)) { throw 'Administrator privileges are required for VLAN apply' }
    $snapshot = Read-Snapshot $SnapshotPath
    $adapter = Assert-SnapshotIdentity $snapshot
    $property = Get-VlanProperty $adapter.Name
    if ((@($property.RegistryValue) -join ',') -ne (@($snapshot.vlan_property.registry_value) -join ',')) {
        throw 'VLAN property changed after snapshot'
    }
    if (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -eq $VlanAddress }) {
        throw "Temporary VLAN address $VlanAddress is already in use"
    }
    Set-NetAdapterAdvancedProperty -Name $adapter.Name `
        -RegistryKeyword ([string]$snapshot.vlan_property.registry_keyword) `
        -RegistryValue $VlanId -NoRestart:$false -ErrorAction Stop
    Wait-AdapterUp $adapter.Name
    New-NetIPAddress -InterfaceIndex $adapter.ifIndex -IPAddress $VlanAddress `
        -PrefixLength $PrefixLength -AddressFamily IPv4 -Type Unicast -ErrorAction Stop | Out-Null
    [ordered]@{
        schema = 'openmitrastar.f301-vlan-controller-apply/v1'
        applied = $true
        interface_alias = $adapter.Name
        vlan_id = $VlanId
        vlan_address = $VlanAddress
        prefix_length = $PrefixLength
        default_gateway_added = $false
        dns_changed = $false
        mutation_scope = 'temporary-controller-adapter-only'
    } | ConvertTo-Json -Depth 6 -Compress
    exit 0
}

if ($Action -eq 'Restore') {
    if (-not (Test-Administrator)) { throw 'Administrator privileges are required for VLAN restore' }
    Restore-Adapter (Read-Snapshot $SnapshotPath) | ConvertTo-Json -Depth 6 -Compress
    exit 0
}

if (-not $StateDirectory) { throw 'StateDirectory is required for Watchdog' }
if (-not (Test-Administrator)) { throw 'Administrator privileges are required for VLAN watchdog' }
$stateRoot = [IO.Path]::GetFullPath($StateDirectory)
New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null
$readyPath = Join-Path $stateRoot 'controller-watchdog-ready.json'
$resultPath = Join-Path $stateRoot 'controller-watchdog-result.json'
$triggerPath = Join-Path $stateRoot 'controller-watchdog-trigger'
$stopPath = Join-Path $stateRoot 'controller-watchdog-stop'
$snapshot = Read-Snapshot $SnapshotPath
[void](Assert-SnapshotIdentity $snapshot)
Write-AtomicJson $readyPath ([ordered]@{
    schema = 'openmitrastar.f301-vlan-controller-watchdog/v1'
    ready = $true
    pid = $PID
    deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds).ToString('o')
    interface_alias = [string]$snapshot.interface_alias
})
$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$reason = ''
while ([DateTime]::UtcNow -lt $deadline) {
    if (Test-Path -LiteralPath $triggerPath) { $reason = 'trigger'; break }
    if (Test-Path -LiteralPath $stopPath) { $reason = 'disarmed'; break }
    Start-Sleep -Milliseconds 200
}
if (-not $reason) { $reason = 'timeout' }
if ($reason -eq 'disarmed') {
    Write-AtomicJson $resultPath ([ordered]@{
        schema = 'openmitrastar.f301-vlan-controller-watchdog/v1'
        status = 'DISARMED'
        restored = $false
    })
    exit 0
}
try {
    $restore = Restore-Adapter $snapshot
    Write-AtomicJson $resultPath ([ordered]@{
        schema = 'openmitrastar.f301-vlan-controller-watchdog/v1'
        status = 'RESTORED'
        reason = $reason
        restored = [bool]$restore.restored
        vlan_address_absent = [bool]$restore.vlan_address_absent
        ipv4_restored_exactly = [bool]$restore.ipv4_restored_exactly
    })
    exit 0
} catch {
    Write-AtomicJson $resultPath ([ordered]@{
        schema = 'openmitrastar.f301-vlan-controller-watchdog/v1'
        status = 'FAILED'
        reason = $reason
        restored = $false
        error = $_.Exception.Message
    })
    exit 1
}
