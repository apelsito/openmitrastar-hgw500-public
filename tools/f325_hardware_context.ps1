# Context carries the parent's existing physical ownership and nonce proof.
# It is not authorization: exact ACK and reviewed-artifact gates remain separate.
# Load the F319 lease/device helpers before calling these functions.
Set-StrictMode -Version Latest

function Get-F325PhysicalContextImage {
    param([Parameter(Mandatory = $true)][string]$Direction)
    switch -CaseSensitive ($Direction) {
        'promote' { return 'e18b221dda9a61bd1066c155c0cd7b44aef0d0fe06b1a1752a7e759e7730c7ec' }
        'rollback' { return 'eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18' }
        'fallback' { return 'a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11' }
        default { throw 'Unsupported F325 physical action' }
    }
}

function Assert-F325PhysicalContextData {
    param(
        [Parameter(Mandatory = $true)][object]$Context,
        [Parameter(Mandatory = $true)][string]$CandidateSha256,
        [Parameter(Mandatory = $true)][string]$Direction
    )
    $pnp = 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000'
    $versions = @('lyoko-foundation-6.8.5-f321-classic-ui-f314-device',
                  'lyoko-foundation-6.9.5-f334-radar-once-f321-device')
    if ($CandidateSha256 -cne (Get-F325PhysicalContextImage -Direction $Direction)) {
        throw 'F325 physical action and exact candidate differ'
    }
    if ($Context -isnot [pscustomobject] -or $Context.schema -isnot [string] -or
        $Context.schema -cne 'openmitrastar.f325-physical-context/v1' -or
        $Context.direction -isnot [string] -or $Context.direction -cne $Direction -or
        $Context.candidate_sha256 -isnot [string] -or $Context.candidate_sha256 -cne $CandidateSha256) {
        throw 'F325 physical context schema, action or candidate mismatch'
    }
    if (($Context.owner_pid -isnot [int] -and $Context.owner_pid -isnot [long]) -or
        $Context.owner_pid -le 0 -or $Context.owner_pid -gt [int]::MaxValue -or
        ($Context.owner_start_ticks -isnot [int] -and $Context.owner_start_ticks -isnot [long]) -or
        $Context.owner_start_ticks -le 0 -or $Context.lease_token -isnot [string] -or
        $Context.lease_token -cnotmatch '^[0-9a-f]{32}$' -or
        $Context.physical_lock_dir -isnot [string] -or [string]::IsNullOrWhiteSpace($Context.physical_lock_dir) -or
        -not [IO.Path]::IsPathRooted($Context.physical_lock_dir) -or
        $Context.uart_port -isnot [string] -or $Context.uart_port -cne 'COM3' -or
        $Context.uart_pnp_device_id -isnot [string] -or $Context.uart_pnp_device_id -ine $pnp) {
        throw 'F325 physical context ownership or UART identity mismatch'
    }
    $binding = $Context.binding
    if ($binding -isnot [pscustomobject] -or $binding.NonceObserved -isnot [bool] -or -not $binding.NonceObserved -or
        $binding.Port -isnot [string] -or $binding.Port -cne 'COM3' -or
        $binding.PnpDeviceId -isnot [string] -or $binding.PnpDeviceId -ine $pnp -or
        $binding.RouterHost -isnot [string] -or $binding.RouterHost -cne '192.168.1.90' -or
        $binding.ExpectedVersion -isnot [string] -or $binding.ExpectedVersion -cnotin $versions) {
        throw 'F325 physical context lacks the authenticated HGW nonce binding'
    }
    $issued = [DateTimeOffset]::MinValue; $expires = [DateTimeOffset]::MinValue
    $culture = [Globalization.CultureInfo]::InvariantCulture
    $style = [Globalization.DateTimeStyles]::None
    if ($Context.created_at_utc -isnot [string] -or $Context.expires_at_utc -isnot [string] -or
        -not [DateTimeOffset]::TryParseExact($Context.created_at_utc, 'o', $culture, $style, [ref]$issued) -or
        -not [DateTimeOffset]::TryParseExact($Context.expires_at_utc, 'o', $culture, $style, [ref]$expires)) {
        throw 'F325 physical context has invalid lifetime metadata'
    }
    $now = [DateTimeOffset]::UtcNow
    if ($issued.Offset -ne [TimeSpan]::Zero -or $expires.Offset -ne [TimeSpan]::Zero -or
        ($expires - $issued).TotalSeconds -ne 5400 -or $issued -gt $now -or $expires -le $now) {
        throw 'F325 physical context is stale or outside its 90 minute lifetime'
    }
    # Revalidate the current adapter and the original process/file/mutex lease.
    # No console is opened and no UART byte is sent by these checks.
    [void](Get-F319SerialDevice -Port 'COM3' -ExpectedPnpDeviceId $pnp)
    [void](Assert-F319HardwareLease -PhysicalLockDir $Context.physical_lock_dir -OwnerPid $Context.owner_pid `
        -OwnerStartTicks $Context.owner_start_ticks -LeaseToken $Context.lease_token -Port 'COM3' -ExpectedPnpDeviceId $pnp)
    return $Context
}

function Create-F325PhysicalContext {
    param(
        [Parameter(Mandatory = $true)][object]$Guard,
        [Parameter(Mandatory = $true)][object]$BindingProof,
        [Parameter(Mandatory = $true)][string]$CandidateSha256,
        [Parameter(Mandatory = $true)][ValidateSet('promote', 'rollback', 'fallback')][string]$Direction
    )
    if ($Guard.OwnerPid -ne $PID -or $BindingProof.OwnerPid -ne $PID -or
        $Guard.OwnerStartTicks -ne $BindingProof.OwnerStartTicks -or
        $Guard.LeaseToken -cne $BindingProof.LeaseToken -or
        $Guard.LeaseStream -isnot [IO.Stream] -or -not $Guard.LeaseStream.CanWrite -or
        $Guard.Port -cne 'COM3' -or $Guard.PnpDeviceId -ine 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000') {
        throw 'F325 context requires this process live lease and its original binding proof'
    }
    $now = [DateTimeOffset]::UtcNow
    $context = [pscustomobject]@{
        schema = 'openmitrastar.f325-physical-context/v1'
        direction = $Direction
        candidate_sha256 = $CandidateSha256
        created_at_utc = $now.ToString('o')
        expires_at_utc = $now.AddMinutes(90).ToString('o')
        owner_pid = $Guard.OwnerPid
        owner_start_ticks = $Guard.OwnerStartTicks
        lease_token = $Guard.LeaseToken
        physical_lock_dir = $Guard.PhysicalLockDir
        uart_port = $Guard.Port
        uart_pnp_device_id = $Guard.PnpDeviceId
        binding = $BindingProof.Binding
    }
    [void](Assert-F325PhysicalContextData -Context $context -CandidateSha256 $CandidateSha256 -Direction $Direction)
    return [Convert]::ToBase64String([Text.UTF8Encoding]::new($false).GetBytes(($context | ConvertTo-Json -Depth 6 -Compress)))
}

function Assert-F325InheritedPhysicalContext {
    param(
        [Parameter(Mandatory = $true)][string]$CandidateSha256,
        [Parameter(Mandatory = $true)][ValidateSet('promote', 'rollback', 'fallback')][string]$Direction
    )
    $encoded = $env:OM_F325_PHYSICAL_CONTEXT
    if ([string]::IsNullOrWhiteSpace($encoded) -or $encoded.Length -gt 16384) {
        throw 'Missing or oversized inherited F325 physical context'
    }
    try {
        $bytes = [Convert]::FromBase64String($encoded)
        # Windows PowerShell 5 preserves JSON date strings. PowerShell 7.5+
        # parses them as DateTime by default, which loses the original string
        # representation required by the strict UTC/lifetime contract below.
        # Preserve strings explicitly where the runtime supports DateKind;
        # never weaken the subsequent exact-format, UTC and 90-minute checks.
        $jsonParameters = @{ErrorAction='Stop'}
        if ((Get-Command ConvertFrom-Json -CommandType Cmdlet).Parameters.ContainsKey('DateKind')) {
            $jsonParameters.DateKind = 'String'
        }
        $context = [Text.UTF8Encoding]::new($false, $true).GetString($bytes) | ConvertFrom-Json @jsonParameters
    } catch { throw 'Inherited F325 physical context is not valid base64 JSON' }
    return (Assert-F325PhysicalContextData -Context $context -CandidateSha256 $CandidateSha256 -Direction $Direction)
}
