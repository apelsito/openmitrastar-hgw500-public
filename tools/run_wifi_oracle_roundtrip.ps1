[CmdletBinding()]
param(
    [ValidateLength(1, 32)][string]$TestSsid = 'OpenMitraStar-2G-DIAG',
    [ValidateLength(1, 32)][string]$RestoreSsid = 'MOVISTAR-WIFI6-A348',
    [ValidateNotNullOrEmpty()][string]$WifiInterface = 'Wi-Fi',
    [ValidateNotNullOrEmpty()][string]$RouterIp = '192.168.1.90',
    [ValidateNotNullOrEmpty()][string]$ControllerUrl = 'http://192.168.1.43:8081/downlink-4m.bin',
    [ValidateNotNullOrEmpty()][string]$OutputPath = 'C:\ProgramData\OpenMitraStar\oracle\roundtrip-result.json',
    [ValidateRange(5, 120)][int]$ConnectTimeoutSeconds = 45,
    [ValidateRange(5, 180)][int]$RestoreTimeoutSeconds = 60
)

$ErrorActionPreference = 'Stop'
$netsh = Join-Path $env:WINDIR 'System32\netsh.exe'
$pingExe = Join-Path $env:WINDIR 'System32\PING.EXE'
$curlExe = Join-Path $env:WINDIR 'System32\curl.exe'

foreach ($value in @($TestSsid, $RestoreSsid, $WifiInterface)) {
    if ($value -match '[\x00-\x1f]') {
        throw 'SSID and interface values must not contain control characters'
    }
}
if ($TestSsid -eq $RestoreSsid) {
    throw 'TestSsid and RestoreSsid must be different'
}

function Invoke-Netsh {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $text = (& $netsh @Arguments 2>&1 | Out-String).Trim()
    [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = $text }
}

function Test-ExactWifiConnection {
    param(
        [Parameter(Mandatory)][string]$InterfaceAlias,
        [Parameter(Mandatory)][string]$Ssid
    )
    $connection = Get-NetConnectionProfile -InterfaceAlias $InterfaceAlias -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq $Ssid } |
        Select-Object -First 1
    return $null -ne $connection
}

function Wait-ExactWifiConnection {
    param(
        [Parameter(Mandatory)][string]$InterfaceAlias,
        [Parameter(Mandatory)][string]$Ssid,
        [Parameter(Mandatory)][int]$TimeoutSeconds
    )
    for ($attempt = 0; $attempt -lt $TimeoutSeconds; $attempt++) {
        if (Test-ExactWifiConnection -InterfaceAlias $InterfaceAlias -Ssid $Ssid) {
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Save-OracleResult {
    param(
        [Parameter(Mandatory)]$Data,
        [Parameter(Mandatory)][string]$LiteralPath
    )
    $json = $Data | ConvertTo-Json -Depth 6
    $temporary = "$LiteralPath.tmp"
    [IO.File]::WriteAllText($temporary, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $LiteralPath -Force
}

$outputDirectory = Split-Path -Parent $OutputPath
if ([string]::IsNullOrWhiteSpace($outputDirectory)) {
    throw 'OutputPath must include a parent directory'
}
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$profilePath = Join-Path $outputDirectory 'openmitrastar-open.xml'
$escapedSsid = [Security.SecurityElement]::Escape($TestSsid)
$profileName = "OpenMitraStar-Oracle-$PID"
$escapedProfileName = [Security.SecurityElement]::Escape($profileName)
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

$result = [ordered]@{
    schema = 'openmitrastar.windows-wifi-oracle-roundtrip/v2'
    started = (Get-Date).ToString('o')
    test_ssid = $TestSsid
    test_profile = $profileName
    restore_ssid = $RestoreSsid
    interface = $WifiInterface
    connected = $false
    wifi_ipv4 = $null
    ping_pass = $false
    ping_exit_code = $null
    ping_output = ''
    curl_pass = $false
    curl_exit_code = $null
    curl_output = ''
    interface_before = $null
    interface_after = $null
    error = $null
    restore_command_exit_code = $null
    restore_error = $null
    restored = $false
    test_profile_removed = $false
}

$scriptExitCode = 0
$resultWriteError = $null
try {
    $addProfile = Invoke-Netsh -Arguments @(
        'wlan', 'add', 'profile',
        "filename=$profilePath", "interface=$WifiInterface", 'user=all'
    )
    if ($addProfile.ExitCode -ne 0) {
        throw "Could not install test WLAN profile: $($addProfile.Output)"
    }

    $result.interface_before = (& $netsh wlan show interfaces 2>&1 | Out-String).Trim()
    $connect = Invoke-Netsh -Arguments @(
        'wlan', 'connect',
        "name=$profileName", "ssid=$TestSsid", "interface=$WifiInterface"
    )
    if ($connect.ExitCode -ne 0) {
        throw "netsh refused test connection: $($connect.Output)"
    }

    $result.connected = Wait-ExactWifiConnection -InterfaceAlias $WifiInterface -Ssid $TestSsid -TimeoutSeconds $ConnectTimeoutSeconds
    if (-not $result.connected) {
        throw "Could not connect interface '$WifiInterface' to '$TestSsid'"
    }

    Start-Sleep -Seconds 3
    $ip = Get-NetIPAddress -InterfaceAlias $WifiInterface -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '169.254.*' } |
        Select-Object -First 1 -ExpandProperty IPAddress
    $result.wifi_ipv4 = $ip
    if (-not $ip) {
        throw 'Wi-Fi connected without non-link-local IPv4'
    }

    $result.ping_output = (& $pingExe -S $ip -n 4 -w 2000 $RouterIp 2>&1 | Out-String).Trim()
    $result.ping_exit_code = $LASTEXITCODE
    $result.ping_pass = $result.ping_exit_code -eq 0

    # Do not bind curl to the IPv4 literal on Windows. The bundled curl can
    # reject that with CURLE_INTERFACE_FAILED even though WLAN routing is
    # correct. The test target is on the active Wi-Fi subnet and the Ethernet
    # oracle link has no usable IPv4 route, so normal route selection is the
    # reliable and observable path here.
    $result.curl_output = (& $curlExe --silent --show-error --max-time 90 --output NUL --write-out 'http=%{http_code};bytes=%{size_download};speed_Bps=%{speed_download};seconds=%{time_total}' $ControllerUrl 2>&1 | Out-String).Trim()
    $result.curl_exit_code = $LASTEXITCODE
    $result.curl_pass = $result.curl_exit_code -eq 0 -and $result.curl_output -match 'http=200;'
    $result.interface_after = (& $netsh wlan show interfaces 2>&1 | Out-String).Trim()
    if (-not $result.curl_pass) {
        throw "Controller download failed: exit=$($result.curl_exit_code) $($result.curl_output)"
    }
} catch {
    $scriptExitCode = 10
    $result.error = $_.Exception.Message
} finally {
    # Restoration comes before persistence or cleanup. A JSON/ACL failure must
    # never skip the return to the normal Wi-Fi network.
    try {
        $restore = Invoke-Netsh -Arguments @(
            'wlan', 'connect',
            "name=$RestoreSsid", "ssid=$RestoreSsid", "interface=$WifiInterface"
        )
        $result.restore_command_exit_code = $restore.ExitCode
        if ($restore.ExitCode -ne 0) {
            throw "netsh refused restore connection: $($restore.Output)"
        }
        $result.restored = Wait-ExactWifiConnection -InterfaceAlias $WifiInterface -Ssid $RestoreSsid -TimeoutSeconds $RestoreTimeoutSeconds
        if (-not $result.restored) {
            throw "Could not restore interface '$WifiInterface' to '$RestoreSsid'"
        }
    } catch {
        $scriptExitCode = 20
        $result.restore_error = $_.Exception.Message
    }

    try {
        $deleteProfile = Invoke-Netsh -Arguments @(
            'wlan', 'delete', 'profile',
            "name=$profileName", "interface=$WifiInterface"
        )
        $result.test_profile_removed = $deleteProfile.ExitCode -eq 0
    } catch {
        $result.test_profile_removed = $false
    }

    $result.finished = (Get-Date).ToString('o')
    $result.restored_at = if ($result.restored) { (Get-Date).ToString('o') } else { $null }
    try {
        Save-OracleResult -Data $result -LiteralPath $OutputPath
    } catch {
        $resultWriteError = $_.Exception.Message
        if ($scriptExitCode -eq 0) {
            $scriptExitCode = 30
        }
    }
}

if ($resultWriteError) {
    [Console]::Error.WriteLine("Oracle result write failed after restoration attempt: $resultWriteError")
}
exit $scriptExitCode
