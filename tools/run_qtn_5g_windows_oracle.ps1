[CmdletBinding()]
param(
    [switch]$Execute,
    [switch]$IsolatedL3,
    [switch]$AssociationOnly,
    [switch]$MtuProbe,
    [switch]$SkipThroughput,
    [ValidateRange(0, 5000)][int]$PingStressCount = 0,
    [ValidateRange(32, 1472)][int]$PingStressPayloadBytes = 1400,
    [string]$Ack = '',
    [string]$TestSsid = 'OpenMitraStar-5G-DIAG',
    [string]$RestoreSsid = '',
    [string]$WifiInterface = '',
    [string]$ExpectedBssid = '',
    [string]$RouterIp = '192.168.1.90',
    [string]$ControllerIp = '192.168.1.43',
    [int]$ControllerPort = 8081,
    [string]$InternetUrl = 'https://www.microsoft.com/favicon.ico',
    [string]$DnsName = 'www.microsoft.com',
    [ValidateRange(1, 256)][int]$UploadMiB = 32,
    [ValidateRange(10, 300)][int]$TransferTimeoutSeconds = 180,
    [int]$SoakSeconds = 600,
    [int]$SampleSeconds = 5,
    [string]$IsolatedRouterIp = '192.168.77.1',
    [string]$IsolatedClientIp = '192.168.77.2',
    [string]$OutputPath = "$env:ProgramData\OpenMitraStar\oracle\qtn-5g-result.json"
)

$ErrorActionPreference = 'Stop'
$requiredAck = 'OPENMITRASTAR_QTN_5G_WINDOWS_ORACLE_RAM_ONLY'

if ($AssociationOnly) {
    if ($SoakSeconds -lt 0 -or $SoakSeconds -gt 1800) { throw 'SoakSeconds must be 0..1800 in AssociationOnly mode' }
} elseif ($SoakSeconds -lt 60 -or $SoakSeconds -gt 1800) {
    throw 'SoakSeconds must be 60..1800'
}
if ($SampleSeconds -lt 2 -or $SampleSeconds -gt 30) { throw 'SampleSeconds must be 2..30' }

if (-not $Execute) {
    [ordered]@{
        schema = 'openmitrastar.qtn-5g-windows-oracle-plan/v1'
        execute = $false
        test_ssid = $TestSsid
        restore = 'capture-current-ssid-or-explicit-restore-ssid'
        association_only = [bool]$AssociationOnly
        directions = if ($AssociationOnly) { @('client association', 'optional isolated router ping') } else { @('AP-to-client: controller HTTP GET', 'client-to-AP: controller HTTP PUT') }
        mode = if ($AssociationOnly) { 'association-only' } elseif ($IsolatedL3) { 'isolated-l3-static' } else { 'bridged-dhcp' }
        dhcp = if ($AssociationOnly) { 'skipped' } elseif ($IsolatedL3) { 'restore-only' } else { 'required' }
        dns_https = if ($AssociationOnly -or $IsolatedL3) { 'out-of-scope' } else { 'required' }
        soak_seconds = $SoakSeconds
        restoration_in_finally = $true
        router_mutations = $false
        flash = $false
    } | ConvertTo-Json -Depth 5
    Write-Output 'OMQTN5G_WINDOWS_ORACLE_DRY_RUN_PASS=1 execute=0 restore=finally flash=0'
    exit 0
}
if ($Ack -ne $requiredAck) { throw "Require -Ack $requiredAck" }

function Get-WifiInterfaceName {
    if ($WifiInterface) { return $WifiInterface }
    $adapter = Get-NetAdapter -Physical -ErrorAction Stop | Where-Object {
        $_.InterfaceDescription -match 'Wireless|Wi-Fi|802\.11|Intel.*Wi|Realtek.*Wireless'
    } | Select-Object -First 1
    if (-not $adapter) { throw 'No physical Wi-Fi adapter found' }
    return $adapter.Name
}

function Get-CurrentSsid([string]$InterfaceName) {
    $shown = netsh wlan show interfaces interface="$InterfaceName" | Out-String
    $match = [regex]::Match($shown, '(?m)^\s*SSID\s*:\s*(?!BSSID)(.+?)\s*$')
    if ($match.Success) { return $match.Groups[1].Value.Trim() }
    return ''
}

function Get-CurrentBssid([string]$InterfaceName) {
    $shown = netsh wlan show interfaces interface="$InterfaceName" | Out-String
    $match = [regex]::Match($shown, '(?mi)^\s*(?:AP\s+)?BSSID(?:\s+\d+)?\s*:\s*([0-9a-f:]{17})\s*$')
    if ($match.Success) { return $match.Groups[1].Value.ToLowerInvariant() }
    return ''
}

function Get-ProfileConnectionMode([string]$InterfaceName, [string]$Ssid) {
    $shown = netsh wlan show profile name="$Ssid" interface="$InterfaceName" | Out-String
    if ($LASTEXITCODE -ne 0) { throw "Profile is unavailable: $Ssid" }
    $match = [regex]::Match(
        $shown,
        '(?mi)^\s*(Connection mode|Modo de conexi[oó]n)\s*:\s*(.+?)\s*$'
    )
    if ($match.Success -and $match.Groups[2].Value -match '(?i)auto') { return 'auto' }
    return 'manual'
}

function Wait-Ssid([string]$InterfaceName, [string]$Ssid, [int]$Seconds) {
    for ($attempt = 0; $attempt -lt $Seconds; $attempt++) {
        if ((Get-CurrentSsid $InterfaceName) -eq $Ssid) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Connect-SsidWithRetry(
    [string]$InterfaceName,
    [string]$Ssid,
    [int]$Attempts = 6,
    [int]$WaitSeconds = 30
) {
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        netsh wlan connect name="$Ssid" ssid="$Ssid" interface="$InterfaceName" | Out-Null
        if ($LASTEXITCODE -eq 0 -and (Wait-Ssid $InterfaceName $Ssid $WaitSeconds)) {
            return $attempt
        }
        netsh wlan disconnect interface="$InterfaceName" | Out-Null
        Start-Sleep -Seconds 2
    }
    return 0
}

function Get-Ipv4State([string]$InterfaceName) {
    $ip = Get-NetIPAddress -InterfaceAlias $InterfaceName -AddressFamily IPv4 `
        -ErrorAction SilentlyContinue | Where-Object {
            $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1'
        } | Select-Object -First 1
    $gateway = Get-NetRoute -InterfaceAlias $InterfaceName -AddressFamily IPv4 `
        -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
        Sort-Object RouteMetric | Select-Object -First 1
    $dns = Get-DnsClientServerAddress -InterfaceAlias $InterfaceName `
        -AddressFamily IPv4 -ErrorAction SilentlyContinue
    $dhcp = Get-NetIPInterface -InterfaceAlias $InterfaceName -AddressFamily IPv4 `
        -ErrorAction SilentlyContinue | Select-Object -First 1
    return [ordered]@{
        ipv4 = if ($ip) { $ip.IPAddress } else { $null }
        prefix_length = if ($ip) { $ip.PrefixLength } else { $null }
        gateway = if ($gateway) { $gateway.NextHop } else { $null }
        dns_servers = if ($dns) { @($dns.ServerAddresses) } else { @() }
        dhcp_enabled = [bool]($dhcp -and $dhcp.Dhcp -eq 'Enabled')
    }
}

function Invoke-BoundPing([string]$SourceIp, [string]$TargetIp) {
    $outputs = @()
    $replyPattern = '(?mi)^\s*(Respuesta desde|Reply from)\s+' + [regex]::Escape($TargetIp) + ':\s+bytes='
    $replyCount = 0
    $sentCount = 0
    Start-Sleep -Seconds 4
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        $output = ping.exe -S $SourceIp -n 2 -w 1200 $TargetIp | Out-String
        $exitCode = $LASTEXITCODE
        $outputs += "attempt=$attempt exit_code=$exitCode`r`n$($output.Trim())"
        $replyCount += [regex]::Matches($output, $replyPattern).Count
        $sentCount += 2
        Start-Sleep -Seconds 2
    }
    return [ordered]@{
        pass = $replyCount -gt 0
        attempts = 5
        sent = $sentCount
        replies = $replyCount
        loss_percent = if ($sentCount) {
            [math]::Round((1.0 - ($replyCount / [double]$sentCount)) * 100, 1)
        } else {
            100.0
        }
        output = ($outputs -join "`r`n")
    }
}

function Invoke-BoundPingPayload([string]$SourceIp, [string]$TargetIp, [int]$PayloadBytes) {
    $output = ping.exe -S $SourceIp -n 5 -w 1500 -f -l $PayloadBytes $TargetIp | Out-String
    $replyPattern = '(?mi)^\s*(Respuesta desde|Reply from)\s+' + [regex]::Escape($TargetIp) + ':\s+bytes='
    $replies = [regex]::Matches($output, $replyPattern).Count
    return [ordered]@{
        payload_bytes = $PayloadBytes
        sent = 5
        replies = $replies
        loss_percent = [math]::Round((1.0 - ($replies / 5.0)) * 100, 1)
        pass = $replies -eq 5
        exit_code = $LASTEXITCODE
    }
}

function Invoke-FastPingStress(
    [string]$TargetIp,
    [int]$Count,
    [int]$PayloadBytes
) {
    $ping = [Net.NetworkInformation.Ping]::new()
    $options = [Net.NetworkInformation.PingOptions]::new(64, $true)
    $buffer = New-Object byte[] $PayloadBytes
    $received = 0
    $watch = [Diagnostics.Stopwatch]::StartNew()
    try {
        for ($i = 0; $i -lt $Count; $i++) {
            try {
                $reply = $ping.Send($TargetIp, 1500, $buffer, $options)
                if ($reply.Status -eq [Net.NetworkInformation.IPStatus]::Success) {
                    $received++
                }
            } catch {}
        }
    } finally {
        $watch.Stop()
        $ping.Dispose()
    }
    $seconds = [math]::Max($watch.Elapsed.TotalSeconds, 0.001)
    return [ordered]@{
        payload_bytes = $PayloadBytes
        sent = $Count
        replies = $received
        loss_percent = [math]::Round((1.0 - ($received / [double]$Count)) * 100, 2)
        seconds = [math]::Round($seconds, 3)
        payload_mbps = [math]::Round(($received * $PayloadBytes * 8.0 / $seconds / 1000000.0), 3)
        pass = $received -eq $Count
    }
}

function Convert-CurlMetric([string]$Raw, [int]$ExitCode) {
    $match = [regex]::Match($Raw, 'http=(\d+);bytes=(\d+);speed_Bps=([0-9.]+);seconds=([0-9.]+)')
    if (-not $match.Success) {
        return [ordered]@{ pass = $false; exit_code = $ExitCode; raw = $Raw.Trim() }
    }
    $bytes = [double]$match.Groups[2].Value
    $seconds = [double]$match.Groups[4].Value
    $mbps = if ($seconds -gt 0) { ($bytes * 8.0 / $seconds / 1000000.0) } else { 0.0 }
    return [ordered]@{
        pass = ($ExitCode -eq 0 -and [int]$match.Groups[1].Value -ge 200 -and [int]$match.Groups[1].Value -lt 400)
        exit_code = $ExitCode
        http_code = [int]$match.Groups[1].Value
        bytes = [long]$bytes
        speed_Bps = [double]$match.Groups[3].Value
        seconds = $seconds
        mbps = [math]::Round($mbps, 3)
        raw = $Raw.Trim()
    }
}

function Invoke-CurlDownload([string]$Url, [int]$Timeout) {
    # The current AELITA Windows curl returns CURLE_INTERFACE_FAILED when bound
    # to the DHCP IPv4 literal.  The Ethernet-side oracle path has no competing
    # usable route during the test; correlate normal route selection with the
    # router wifi0/eth0 counters instead of forcing curl --interface.
    $savedErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $raw = (& curl.exe --silent --show-error --location `
            --max-time $Timeout --output NUL `
            --write-out 'http=%{http_code};bytes=%{size_download};speed_Bps=%{speed_download};seconds=%{time_total}' `
            $Url 2>&1 | Out-String)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedErrorAction
    }
    return Convert-CurlMetric $raw $exitCode
}

function Invoke-CurlUpload([string]$Url, [string]$FilePath, [int]$Timeout) {
    $savedErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $raw = (& curl.exe --silent --show-error --request PUT `
            --upload-file $FilePath --max-time $Timeout --output NUL `
            --write-out 'http=%{http_code};bytes=%{size_upload};speed_Bps=%{speed_upload};seconds=%{time_total}' `
            $Url 2>&1 | Out-String)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedErrorAction
    }
    return Convert-CurlMetric $raw $exitCode
}

$WifiInterface = Get-WifiInterfaceName
$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$profilePath = Join-Path $outputDirectory 'openmitrastar-5g-open.xml'
$uploadPath = Join-Path $outputDirectory 'qtn-5g-upload.bin'
$initialSsid = Get-CurrentSsid $WifiInterface
if (-not $RestoreSsid) { $RestoreSsid = $initialSsid }
if (-not $RestoreSsid) { throw 'No connected primary Wi-Fi and no RestoreSsid supplied' }
if ($RestoreSsid -eq $TestSsid) { throw 'RestoreSsid must differ from TestSsid' }

$restoreProfile = netsh wlan show profile name="$RestoreSsid" interface="$WifiInterface" | Out-String
if ($LASTEXITCODE -ne 0) { throw "Restore profile is unavailable: $RestoreSsid" }
$restoreConnectionMode = Get-ProfileConnectionMode $WifiInterface $RestoreSsid
$testProfileBefore = netsh wlan show profile name="$TestSsid" interface="$WifiInterface" | Out-String
$createdTestProfile = $LASTEXITCODE -ne 0

$result = [ordered]@{
    schema = 'openmitrastar.qtn-5g-windows-oracle/v1'
    started = (Get-Date).ToString('o')
    association_only = [bool]$AssociationOnly
    test_ssid = $TestSsid
    restore_ssid = $RestoreSsid
    wifi_interface = $WifiInterface
    expected_bssid = if ($ExpectedBssid) { $ExpectedBssid.ToLowerInvariant() } else { $null }
    before = [ordered]@{ ssid = $initialSsid; ipv4 = Get-Ipv4State $WifiInterface }
    test = [ordered]@{
        mode = if ($AssociationOnly) { 'association-only' } elseif ($IsolatedL3) { 'isolated-l3-static' } else { 'bridged-dhcp' }
        association_only = [bool]$AssociationOnly
        connected = $false
        bssid = $null
        bssid_match = if ($ExpectedBssid) { $false } else { $null }
        ipv4 = $null
        router_ping = $null
        router_ping_static_neighbor = $null
        mtu_probe = @()
        ping_stress = $null
        gateway_ping = $null
        controller_ping = $null
        dhcp = $false
        static_ipv4_applied = $false
        dns_ok = $false
        dns_answers = @()
        internet_https = $null
        ap_to_client = $null
        client_to_ap = $null
        soak = [ordered]@{
            requested_seconds = $SoakSeconds
            samples = 0
            disconnects = 0
            connected_samples = 0
            sample_details = @()
        }
    }
    restore = [ordered]@{ attempted = $false; connected = $false; ssid = $RestoreSsid; ipv4 = $null }
    restore_profile_mode_before = $restoreConnectionMode
    restore_profile_autoconnect_suspended = $false
    test_profile_roaming_suppressed = $false
    created_test_profile = $createdTestProfile
    execution_error = $null
    flash = $false
    router_mutations = $false
}

$switched = $false
try {
    if ($restoreConnectionMode -eq 'auto') {
        netsh wlan set profileparameter name="$RestoreSsid" interface="$WifiInterface" connectionmode=manual | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Failed to suspend restore-profile autoconnect' }
        $result.restore_profile_autoconnect_suspended = $true
    }
    if ($createdTestProfile) {
        $escapedSsid = [Security.SecurityElement]::Escape($TestSsid)
        $profile = @"
<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>$escapedSsid</name>
  <SSIDConfig><SSID><name>$escapedSsid</name></SSID></SSIDConfig>
  <connectionType>ESS</connectionType><connectionMode>manual</connectionMode>
  <MSM><security><authEncryption><authentication>open</authentication>
  <encryption>none</encryption><useOneX>false</useOneX>
  </authEncryption></security></MSM>
</WLANProfile>
"@
        [IO.File]::WriteAllText($profilePath, $profile, [Text.UTF8Encoding]::new($false))
        netsh wlan add profile filename="$profilePath" interface="$WifiInterface" user=all | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Failed to add temporary open 5 GHz profile' }
    }

    netsh wlan set profileparameter name="$TestSsid" interface="$WifiInterface" `
        connectionmode=manual autoswitch=no | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to suppress 5 GHz test-profile roaming' }
    $result.test_profile_roaming_suppressed = $true

    $testConnectAttempt = Connect-SsidWithRetry $WifiInterface $TestSsid 3 30
    if ($testConnectAttempt -eq 0) { throw "Could not connect to $TestSsid" }
    $switched = $true
    $result.test.connected = $true
    Start-Sleep -Seconds 3
    $result.test.bssid = Get-CurrentBssid $WifiInterface
    if ($ExpectedBssid) { $result.test.bssid_match = $result.test.bssid -eq $ExpectedBssid.ToLowerInvariant() }
    if ($AssociationOnly) {
        $result.test.ipv4 = [ordered]@{ skipped_reason = 'association_only' }
        $result.test.router_ping = [ordered]@{ attempted = $false; pass = $null; skipped_reason = 'association_only' }
        $result.test.controller_ping = [ordered]@{ attempted = $false; pass = $null; skipped_reason = 'association_only' }
    } elseif ($IsolatedL3) {
        Set-NetIPInterface -InterfaceAlias $WifiInterface -AddressFamily IPv4 -Dhcp Disabled -ErrorAction Stop
        Get-NetIPAddress -InterfaceAlias $WifiInterface -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -ne '127.0.0.1' } |
            Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
        New-NetIPAddress -InterfaceAlias $WifiInterface -AddressFamily IPv4 `
            -IPAddress $IsolatedClientIp -PrefixLength 24 -PolicyStore ActiveStore -ErrorAction Stop | Out-Null
        Start-Sleep -Seconds 1
        $result.test.ipv4 = Get-Ipv4State $WifiInterface
        $ip = $result.test.ipv4.ipv4
        if ($ip -ne $IsolatedClientIp) { throw 'Isolated 5 GHz static IPv4 readback failed' }
        $result.test.static_ipv4_applied = $true
        $result.test.router_ping = Invoke-BoundPing $ip $IsolatedRouterIp
        if ($ExpectedBssid) {
            $neighborMac = $ExpectedBssid.Replace(':', '-')
            try {
                Remove-NetNeighbor -InterfaceAlias $WifiInterface -IPAddress $IsolatedRouterIp `
                    -Confirm:$false -ErrorAction SilentlyContinue
                New-NetNeighbor -InterfaceAlias $WifiInterface -IPAddress $IsolatedRouterIp `
                    -LinkLayerAddress $neighborMac -PolicyStore ActiveStore -ErrorAction Stop | Out-Null
                Start-Sleep -Seconds 2
                $result.test.router_ping_static_neighbor = Invoke-BoundPing $ip $IsolatedRouterIp
            } catch {
                $result.test.router_ping_static_neighbor = [ordered]@{
                    pass = $false
                    error = $_.Exception.Message
                }
            }
        }
        if ($PingStressCount -gt 0) {
            $result.test.ping_stress = Invoke-FastPingStress `
                $IsolatedRouterIp $PingStressCount $PingStressPayloadBytes
        }
    } else {
        $result.test.ipv4 = Get-Ipv4State $WifiInterface
        $ip = $result.test.ipv4.ipv4
        if (-not $ip) { throw 'Connected to 5 GHz without non-APIPA IPv4' }
        $result.test.dhcp = [bool]($result.test.ipv4.dhcp_enabled -and $result.test.ipv4.gateway -and $result.test.ipv4.dns_servers.Count -gt 0)
        $result.test.router_ping = Invoke-BoundPing $ip $RouterIp
        $result.test.controller_ping = Invoke-BoundPing $ip $ControllerIp
        if ($result.test.ipv4.gateway) {
            $result.test.gateway_ping = Invoke-BoundPing $ip $result.test.ipv4.gateway
        }
    }

    if ($MtuProbe) {
        $mtuTarget = if ($IsolatedL3) { $IsolatedRouterIp } else { $result.test.ipv4.gateway }
        if ($mtuTarget) {
            foreach ($payloadBytes in @(32, 256, 512, 1000, 1400, 1472)) {
                $result.test.mtu_probe += Invoke-BoundPingPayload $ip $mtuTarget $payloadBytes
            }
        }
    }

    if (-not $IsolatedL3) { try {
        $answers = Resolve-DnsName -Name $DnsName -Type A -ErrorAction Stop |
            Where-Object { $_.IPAddress } | Select-Object -ExpandProperty IPAddress
        $result.test.dns_answers = @($answers)
        $result.test.dns_ok = $result.test.dns_answers.Count -gt 0
    } catch { $result.test.dns_ok = $false } }

    if (-not $IsolatedL3 -and -not $SkipThroughput) {
        $downloadUrl = "http://$ControllerIp`:$ControllerPort/speed.bin"
        $uploadUrl = "http://$ControllerIp`:$ControllerPort/upload.bin"
        $result.test.ap_to_client = Invoke-CurlDownload $downloadUrl $TransferTimeoutSeconds
        $stream = [IO.File]::Open($uploadPath, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $stream.SetLength($UploadMiB * 1MB) } finally { $stream.Dispose() }
        $result.test.client_to_ap = Invoke-CurlUpload $uploadUrl $uploadPath $TransferTimeoutSeconds
        $result.test.internet_https = Invoke-CurlDownload $InternetUrl 45
    }

    if ($AssociationOnly) {
        $result.test.soak.skipped = $true
    } else {
        $deadline = (Get-Date).AddSeconds($SoakSeconds)
        $wasConnected = $true
        while ((Get-Date) -lt $deadline) {
            $ssid = Get-CurrentSsid $WifiInterface
            $adapter = Get-NetAdapter -Name $WifiInterface -ErrorAction SilentlyContinue
            $ipv4State = Get-Ipv4State $WifiInterface
            $routerPing = $false
            $controllerPing = $false
            if ($ipv4State.ipv4) {
                ping.exe -S $ipv4State.ipv4 -n 1 -w 800 $RouterIp | Out-Null
                $routerPing = $LASTEXITCODE -eq 0
                ping.exe -S $ipv4State.ipv4 -n 1 -w 800 $ControllerIp | Out-Null
                $controllerPing = $LASTEXITCODE -eq 0
            }
            $result.test.soak.samples++
            $result.test.soak.sample_details += [ordered]@{
                at = (Get-Date).ToString('o')
                ssid = if ($ssid) { $ssid } else { $null }
                ssid_match = $ssid -eq $TestSsid
                adapter_status = if ($adapter) { [string]$adapter.Status } else { $null }
                media_state = if ($adapter) { [string]$adapter.MediaConnectionState } else { $null }
                ipv4 = $ipv4State.ipv4
                router_ping = $routerPing
                controller_ping = $controllerPing
            }
            if ($ssid -eq $TestSsid) {
                $result.test.soak.connected_samples++
                $wasConnected = $true
            } else {
                if ($wasConnected) { $result.test.soak.disconnects++ }
                $wasConnected = $false
            }
            Start-Sleep -Seconds $SampleSeconds
        }
    }
} catch {
    $result.execution_error = $_.Exception.Message
} finally {
    Remove-Item -LiteralPath $uploadPath -Force -ErrorAction SilentlyContinue
    if ($IsolatedL3) {
        Remove-NetNeighbor -InterfaceAlias $WifiInterface -IPAddress $IsolatedRouterIp `
            -Confirm:$false -ErrorAction SilentlyContinue
        Get-NetIPAddress -InterfaceAlias $WifiInterface -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -eq $IsolatedClientIp } |
            Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
        Set-NetIPInterface -InterfaceAlias $WifiInterface -AddressFamily IPv4 -Dhcp Enabled -ErrorAction SilentlyContinue
        Set-DnsClientServerAddress -InterfaceAlias $WifiInterface -ResetServerAddresses -ErrorAction SilentlyContinue
    }
    if ($switched) {
        $result.restore.attempted = $true
        $restoreAttempt = Connect-SsidWithRetry $WifiInterface $RestoreSsid 6 30
        $result.restore.attempts = $restoreAttempt
        $result.restore.connected = $restoreAttempt -gt 0
        if ($result.restore.connected) {
            if ($IsolatedL3) { ipconfig.exe /renew "$WifiInterface" | Out-Null }
            Start-Sleep -Seconds 3
            $result.restore.ipv4 = Get-Ipv4State $WifiInterface
        }
    } else {
        $result.restore.connected = (Get-CurrentSsid $WifiInterface) -eq $RestoreSsid
        $result.restore.ipv4 = Get-Ipv4State $WifiInterface
    }
    if ($createdTestProfile) {
        netsh wlan delete profile name="$TestSsid" interface="$WifiInterface" | Out-Null
    }
    if ($restoreConnectionMode -eq 'auto') {
        netsh wlan set profileparameter name="$RestoreSsid" interface="$WifiInterface" connectionmode=auto | Out-Null
    }
    Remove-Item -LiteralPath $profilePath -Force -ErrorAction SilentlyContinue
    $result.finished = (Get-Date).ToString('o')
    [IO.File]::WriteAllText(
        $OutputPath,
        ($result | ConvertTo-Json -Depth 10) + "`r`n",
        [Text.UTF8Encoding]::new($false)
    )
}

Write-Output ("OMQTN5G_WINDOWS_ORACLE_CAPTURE_COMPLETE=1 connected={0} restored={1} association_only={2} output={3}" -f `
    $result.test.connected, $result.restore.connected, $result.association_only, $OutputPath)
if (-not $result.restore.connected) { exit 3 }
if ($result.execution_error) { exit 2 }
exit 0
