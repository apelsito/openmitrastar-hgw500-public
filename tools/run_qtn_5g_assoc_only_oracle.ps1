[CmdletBinding()]
param(
    [switch]$Execute,
    [string]$Ack = '',
    [ValidateLength(1, 32)][string]$TestSsid = 'OpenMitraStar-5G-DIAG',
    [ValidateLength(1, 32)][string]$RestoreSsid = 'MOVISTAR-WIFI6-A348',
    [ValidateNotNullOrEmpty()][string]$WifiInterface = 'Wi-Fi',
    [string]$ExpectedBssid = '',
    [ValidateNotNullOrEmpty()][string]$OutputPath = 'C:\ProgramData\OpenMitraStar\oracle\qtn-5g-assoc-only-result.json',
    [ValidateRange(5, 120)][int]$ScanTimeoutSeconds = 20,
    [ValidateRange(5, 120)][int]$ConnectTimeoutSeconds = 45,
    [ValidateRange(5, 180)][int]$RestoreTimeoutSeconds = 60
)

$ErrorActionPreference = 'Stop'
$requiredAck = 'OPENMITRASTAR_QTN_5G_ASSOC_ONLY_ORACLE'
$netsh = Join-Path $env:WINDIR 'System32\netsh.exe'

foreach ($value in @($TestSsid, $RestoreSsid, $WifiInterface, $ExpectedBssid)) {
    if ($value -match '[\x00-\x1f]') {
        throw 'SSID, BSSID and interface values must not contain control characters'
    }
}
if ($TestSsid -eq $RestoreSsid) { throw 'TestSsid and RestoreSsid must be different' }
if ($ExpectedBssid -and $ExpectedBssid -notmatch '^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$') {
    throw 'ExpectedBssid must be empty or a colon-separated MAC address'
}

if (-not $Execute) {
    [ordered]@{
        schema = 'openmitrastar.qtn-5g-assoc-only-oracle-plan/v1'
        execute = $false
        test_ssid = $TestSsid
        restore_ssid = $RestoreSsid
        interface = $WifiInterface
        expected_bssid = if ($ExpectedBssid) { $ExpectedBssid.ToLowerInvariant() } else { $null }
        phases = @('scan-visible', 'connect-readback', 'restore')
        policy = [ordered]@{
            association_only = $true
            router_mutations = $false
            serial_uart = $false
            static_ip_allowed = $false
            ping_allowed = $false
            traffic_allowed = $false
            flash = $false
        }
    } | ConvertTo-Json -Depth 5
    Write-Output 'OMQTN5G_ASSOC_ONLY_ORACLE_DRY_RUN_PASS=1 execute=0 l3=0 traffic=0'
    exit 0
}
if ($Ack -ne $requiredAck) { throw "Require -Ack $requiredAck" }

function Invoke-Netsh {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $text = (& $netsh @Arguments 2>&1 | Out-String).Trim()
    [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = $text }
}

function Get-CurrentWifiReadback {
    param([Parameter(Mandatory)][string]$InterfaceName)
    $shown = (& $netsh wlan show interfaces "interface=$InterfaceName" 2>&1 | Out-String)
    $ssidMatch = [regex]::Match($shown, '(?m)^\s*SSID\s*:\s*(?!BSSID)(.+?)\s*$')
    $bssidMatch = [regex]::Match($shown, '(?mi)^\s*BSSID\s*:\s*([0-9a-f:]{17})\s*$')
    [ordered]@{
        ssid = if ($ssidMatch.Success) { $ssidMatch.Groups[1].Value.Trim() } else { '' }
        bssid = if ($bssidMatch.Success) { $bssidMatch.Groups[1].Value.ToLowerInvariant() } else { '' }
        raw = $shown.Trim()
    }
}

function Wait-CurrentSsid {
    param(
        [Parameter(Mandatory)][string]$InterfaceName,
        [Parameter(Mandatory)][string]$Ssid,
        [Parameter(Mandatory)][int]$TimeoutSeconds
    )
    for ($attempt = 0; $attempt -lt $TimeoutSeconds; $attempt++) {
        $readback = Get-CurrentWifiReadback -InterfaceName $InterfaceName
        if ($readback.ssid -eq $Ssid) { return $readback }
        Start-Sleep -Seconds 1
    }
    return Get-CurrentWifiReadback -InterfaceName $InterfaceName
}

function Find-VisibleSsid {
    param(
        [Parameter(Mandatory)][string]$InterfaceName,
        [Parameter(Mandatory)][string]$Ssid,
        [Parameter(Mandatory)][int]$TimeoutSeconds
    )
    $last = ''
    for ($attempt = 0; $attempt -lt $TimeoutSeconds; $attempt++) {
        $scan = Invoke-Netsh -Arguments @('wlan', 'show', 'networks', 'mode=bssid', "interface=$InterfaceName")
        $last = $scan.Output
        if ($scan.Output -match [regex]::Escape($Ssid)) {
            $bssids = @()
            foreach ($match in [regex]::Matches($scan.Output, '(?mi)^\s*BSSID\s+\d+\s*:\s*([0-9a-f:]{17})\s*$')) {
                $bssids += $match.Groups[1].Value.ToLowerInvariant()
            }
            return [ordered]@{ pass = $true; raw = $scan.Output; bssids = $bssids }
        }
        Start-Sleep -Seconds 1
    }
    return [ordered]@{ pass = $false; raw = $last; bssids = @() }
}

function Save-OracleResult {
    param(
        [Parameter(Mandatory)]$Data,
        [Parameter(Mandatory)][string]$LiteralPath
    )
    $json = $Data | ConvertTo-Json -Depth 8
    $temporary = "$LiteralPath.tmp"
    [IO.File]::WriteAllText($temporary, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $LiteralPath -Force
}

$outputDirectory = Split-Path -Parent $OutputPath
if ([string]::IsNullOrWhiteSpace($outputDirectory)) { throw 'OutputPath must include a parent directory' }
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$profilePath = Join-Path $outputDirectory "openmitrastar-5g-assoc-only-$PID.xml"
$profileName = "OpenMitraStar-5G-AssocOnly-$PID"
$escapedSsid = [Security.SecurityElement]::Escape($TestSsid)
$escapedProfileName = [Security.SecurityElement]::Escape($profileName)
$expected = if ($ExpectedBssid) { $ExpectedBssid.ToLowerInvariant() } else { $null }

$result = [ordered]@{
    schema = 'openmitrastar.qtn-5g-assoc-only-oracle/v1'
    started = (Get-Date).ToString('o')
    status = 'FAIL_CONNECT'
    policy = [ordered]@{
        association_only = $true
        router_mutations = $false
        serial_uart = $false
        static_ip_allowed = $false
        ping_allowed = $false
        traffic_allowed = $false
        flash = $false
    }
    network = [ordered]@{
        test_ssid = $TestSsid
        restore_ssid = $RestoreSsid
        interface = $WifiInterface
        expected_bssid = $expected
        test_profile = $profileName
    }
    phases = [ordered]@{
        scan_visible = [ordered]@{ attempted = $false; pass = $false; matches = @(); raw = '' }
        connect = [ordered]@{ attempted = $false; pass = $false; ssid_readback = ''; bssid = ''; bssid_match = if ($expected) { $false } else { $null } }
        static_ip = [ordered]@{ attempted = $false; pass = $null; skipped_reason = 'association_only' }
        ping = [ordered]@{ attempted = $false; pass = $null; skipped_reason = 'association_only' }
        traffic = [ordered]@{ attempted = $false; ap_to_client = 'not_run'; client_to_ap = 'not_run'; skipped_reason = 'association_only' }
    }
    restore = [ordered]@{ attempted = $false; pass = $false; ssid_readback = ''; error = $null }
    created_test_profile = $false
    test_profile_removed = $false
    error = $null
    result_claim = 'scan_and_association_only_no_l3_no_traffic'
}

$scriptExitCode = 0
$resultWriteError = $null
try {
    $restoreProfileCheck = Invoke-Netsh -Arguments @('wlan', 'show', 'profile', "name=$RestoreSsid", "interface=$WifiInterface")
    if ($restoreProfileCheck.ExitCode -ne 0) {
        throw "Restore profile is unavailable: $($restoreProfileCheck.Output)"
    }

    $result.phases.scan_visible.attempted = $true
    $visible = Find-VisibleSsid -InterfaceName $WifiInterface -Ssid $TestSsid -TimeoutSeconds $ScanTimeoutSeconds
    $result.phases.scan_visible.pass = [bool]$visible.pass
    $result.phases.scan_visible.matches = @($visible.bssids)
    $result.phases.scan_visible.raw = $visible.raw
    if (-not $visible.pass) {
        $result.status = 'FAIL_NOT_VISIBLE'
        throw "Test SSID is not visible: $TestSsid"
    }

    $profile = @"
<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>$escapedProfileName</name>
  <SSIDConfig><SSID><name>$escapedSsid</name></SSID></SSIDConfig>
  <connectionType>ESS</connectionType>
  <connectionMode>manual</connectionMode>
  <MSM><security><authEncryption>
    <authentication>open</authentication><encryption>none</encryption><useOneX>false</useOneX>
  </authEncryption></security></MSM>
</WLANProfile>
"@
    [IO.File]::WriteAllText($profilePath, $profile, [Text.UTF8Encoding]::new($false))
    $addProfile = Invoke-Netsh -Arguments @('wlan', 'add', 'profile', "filename=$profilePath", "interface=$WifiInterface", 'user=all')
    if ($addProfile.ExitCode -ne 0) {
        throw "Could not install test WLAN profile: $($addProfile.Output)"
    }
    $result.created_test_profile = $true

    $result.phases.connect.attempted = $true
    $connect = Invoke-Netsh -Arguments @('wlan', 'connect', "name=$profileName", "ssid=$TestSsid", "interface=$WifiInterface")
    if ($connect.ExitCode -ne 0) {
        throw "netsh refused test connection: $($connect.Output)"
    }
    $readback = Wait-CurrentSsid -InterfaceName $WifiInterface -Ssid $TestSsid -TimeoutSeconds $ConnectTimeoutSeconds
    $result.phases.connect.ssid_readback = $readback.ssid
    $result.phases.connect.bssid = $readback.bssid
    $result.phases.connect.pass = $readback.ssid -eq $TestSsid
    if ($expected) { $result.phases.connect.bssid_match = $readback.bssid -eq $expected }
    if (-not $result.phases.connect.pass) {
        throw "Could not connect interface '$WifiInterface' to '$TestSsid'"
    }
    if ($expected -and -not $result.phases.connect.bssid_match) {
        throw "Connected BSSID '$($readback.bssid)' did not match expected '$expected'"
    }
    $result.status = 'PASS_ASSOC_ONLY'
} catch {
    if ($result.status -eq 'PASS_ASSOC_ONLY') { $result.status = 'FAIL_CONNECT' }
    $result.error = $_.Exception.Message
    $scriptExitCode = 10
} finally {
    try {
        $result.restore.attempted = $true
        $restore = Invoke-Netsh -Arguments @('wlan', 'connect', "name=$RestoreSsid", "ssid=$RestoreSsid", "interface=$WifiInterface")
        if ($restore.ExitCode -ne 0) {
            throw "netsh refused restore connection: $($restore.Output)"
        }
        $restoreReadback = Wait-CurrentSsid -InterfaceName $WifiInterface -Ssid $RestoreSsid -TimeoutSeconds $RestoreTimeoutSeconds
        $result.restore.ssid_readback = $restoreReadback.ssid
        $result.restore.pass = $restoreReadback.ssid -eq $RestoreSsid
        if (-not $result.restore.pass) {
            throw "Could not restore interface '$WifiInterface' to '$RestoreSsid'"
        }
    } catch {
        $result.status = 'FAIL_RESTORE'
        $result.restore.error = $_.Exception.Message
        $scriptExitCode = 20
    }

    try {
        if ($result.created_test_profile) {
            $deleteProfile = Invoke-Netsh -Arguments @('wlan', 'delete', 'profile', "name=$profileName", "interface=$WifiInterface")
            $result.test_profile_removed = $deleteProfile.ExitCode -eq 0
        }
    } catch {
        $result.test_profile_removed = $false
    }
    Remove-Item -LiteralPath $profilePath -Force -ErrorAction SilentlyContinue
    $result.finished = (Get-Date).ToString('o')
    try {
        Save-OracleResult -Data $result -LiteralPath $OutputPath
    } catch {
        $resultWriteError = $_.Exception.Message
        if ($scriptExitCode -eq 0) { $scriptExitCode = 30 }
    }
}

if ($resultWriteError) {
    [Console]::Error.WriteLine("Assoc-only oracle result write failed after restoration attempt: $resultWriteError")
}
Write-Output ("OMQTN5G_ASSOC_ONLY_ORACLE_COMPLETE=1 status={0} restored={1} output={2}" -f `
    $result.status, $result.restore.pass, $OutputPath)
exit $scriptExitCode
