[CmdletBinding()]
param(
    [string]$Ssid = 'OpenMitraStar-2G-DIAG',
    [string]$WifiInterface = '',
    [string]$RouterIp = '192.168.1.90',
    [string]$ControllerUrl = 'http://192.168.1.43:8081/downlink.bin',
    [int]$Cycles = 0,
    [int]$CooldownSeconds = 5,
    [string]$OutputDirectory = "$env:ProgramData\OpenMitraStar\wifi-oracle"
)

$ErrorActionPreference = 'Stop'
if ($Cycles -lt 0 -or $CooldownSeconds -lt 0) { throw 'Invalid cycles/cooldown' }

if (-not $WifiInterface) {
    $candidate = Get-NetAdapter -Physical | Where-Object {
        $_.InterfaceDescription -match 'Wireless|Wi-Fi|802\.11|Intel.*Wi'
    } | Select-Object -First 1
    if (-not $candidate) { throw 'No physical Wi-Fi adapter found' }
    $WifiInterface = $candidate.Name
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$profilePath = Join-Path $OutputDirectory 'openmitrastar-open.xml'
$escapedSsid = [Security.SecurityElement]::Escape($Ssid)
$profile = @"
<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>$escapedSsid</name>
  <SSIDConfig><SSID><name>$escapedSsid</name></SSID></SSIDConfig>
  <connectionType>ESS</connectionType>
  <connectionMode>manual</connectionMode>
  <MSM><security><authEncryption>
    <authentication>open</authentication><encryption>none</encryption><useOneX>false</useOneX>
  </authEncryption></security></MSM>
</WLANProfile>
"@
[IO.File]::WriteAllText($profilePath, $profile, [Text.UTF8Encoding]::new($false))
netsh wlan add profile filename="$profilePath" interface="$WifiInterface" user=current | Out-Null

$cycle = 0
while ($Cycles -eq 0 -or $cycle -lt $Cycles) {
    $cycle++
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    netsh wlan connect name="$Ssid" ssid="$Ssid" interface="$WifiInterface" | Out-Null

    $connected = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        $shown = netsh wlan show interfaces
        if (($shown | Select-String -Pattern "^\s*SSID\s*:\s*$([regex]::Escape($Ssid))\s*$")) {
            $connected = $true
            break
        }
    }

    $ip = Get-NetIPAddress -InterfaceAlias $WifiInterface -AddressFamily IPv4 `
        -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '169.254.*' } `
        | Select-Object -First 1 -ExpandProperty IPAddress

    $pingOutput = ''
    $curlOutput = ''
    if ($connected -and $ip) {
        $pingOutput = (ping.exe -S $ip -n 4 -w 1500 $RouterIp | Out-String).Trim()
        $curlOutput = (& curl.exe --interface $ip --silent --show-error --max-time 30 `
            --output NUL --write-out 'http=%{http_code};bytes=%{size_download};speed_Bps=%{speed_download};seconds=%{time_total}' `
            $ControllerUrl 2>&1 | Out-String).Trim()
    }

    $result = [ordered]@{
        schema = 'openmitrastar.windows-wifi-oracle/v1'
        timestamp = (Get-Date).ToString('o')
        cycle = $cycle
        ssid = $Ssid
        interface = $WifiInterface
        connected = $connected
        wifi_ipv4 = $ip
        router_ip = $RouterIp
        controller_url = $ControllerUrl
        ping_output = $pingOutput
        curl_output = $curlOutput
    }
    $result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath `
        (Join-Path $OutputDirectory "$stamp-result.json") -Encoding UTF8
    Write-Output ("OM2G_ORACLE cycle={0} connected={1} ip={2} curl={3}" -f `
        $cycle, $connected, $ip, $curlOutput)
    Start-Sleep -Seconds $CooldownSeconds
}

