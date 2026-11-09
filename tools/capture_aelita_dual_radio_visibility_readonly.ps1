[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RouterHost = "192.168.1.90",
    [string]$AelitaHost = "192.168.1.63",
    [string]$AelitaUser = "AELITA",
    [string]$Radio2Ssid = "OpenMitraStar-Lab",
    [string]$Radio5Ssid = "MOVISTAR_PLUS_55CB",
    [ValidateRange(1, 12)][int]$ScanCount = 6,
    [ValidateRange(1, 30)][int]$ScanIntervalSeconds = 4,
    [ValidateRange(5, 60)][int]$CounterIntervalSeconds = 20,
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDirectory) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $OutputDirectory = Join-Path $root "outputs\postflash\dual-radio-visibility-$stamp"
}
$output = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $output | Out-Null

function Match-Number([string]$Text, [string]$Name) {
    $match = [regex]::Match($Text, "(?m)^$([regex]::Escape($Name))=(\d+)\s*$")
    if (-not $match.Success) { return $null }
    return [long]$match.Groups[1].Value
}

$remoteScan = @"
`$ProgressPreference = 'SilentlyContinue'
1..$ScanCount | ForEach-Object {
    Write-Output ('SCAN={0} TIME={1}' -f `$_, (Get-Date).ToString('o'))
    & "`$env:WINDIR\System32\netsh.exe" wlan show networks mode=bssid
    Start-Sleep -Seconds $ScanIntervalSeconds
}
"@
$encodedScan = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($remoteScan))
$scanCommand = "powershell.exe -NoProfile -NonInteractive -OutputFormat Text -EncodedCommand $encodedScan"
$scanOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\connect_aelita_auto.ps1") `
    -Mode ssh -HostAddress $AelitaHost -User $AelitaUser -RemoteCommand $scanCommand 2>&1
$scanRc = $LASTEXITCODE
$scanText = ($scanOutput | Out-String)

$routerCommand = @'
set +e
/usr/sbin/om-radioctl status 2g
/usr/sbin/om-radioctl status 5g
/usr/sbin/iwpriv-qtn wifi0 get_mode 2>/dev/null
printf 'WLAN0_TX_BEFORE='; cat /sys/class/net/wlan0/statistics/tx_packets 2>/dev/null
printf 'WIFI0_TX_BEFORE='; cat /sys/class/net/wifi0/statistics/tx_packets 2>/dev/null
sleep COUNTER_INTERVAL_SECONDS
printf 'WLAN0_TX_AFTER='; cat /sys/class/net/wlan0/statistics/tx_packets 2>/dev/null
printf 'WIFI0_TX_AFTER='; cat /sys/class/net/wifi0/statistics/tx_packets 2>/dev/null
fatal_count=$(dmesg | grep -Eic 'Misaligned Access|kernel panic|Oops:|BUG:|QDRV.*fatal|MuC.*fatal|DMA.*fatal' || true)
printf 'FATAL_COUNT=%s\n' "$fatal_count"
exit 0
'@
$routerCommand = $routerCommand.Replace("COUNTER_INTERVAL_SECONDS", [string]$CounterIntervalSeconds)
$routerOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\ssh_openmitrastar_510.ps1") $routerCommand 2>&1
$routerRc = $LASTEXITCODE
$routerText = ($routerOutput | Out-String)
$routerText | Set-Content -LiteralPath (Join-Path $output "router-radio.log") -Encoding utf8

$wlanBefore = Match-Number $routerText "WLAN0_TX_BEFORE"
$wlanAfter = Match-Number $routerText "WLAN0_TX_AFTER"
$wifiBefore = Match-Number $routerText "WIFI0_TX_BEFORE"
$wifiAfter = Match-Number $routerText "WIFI0_TX_AFTER"
$fatalCount = Match-Number $routerText "FATAL_COUNT"
$radio2Ready = $routerText -match '"id":"2g","lifecycle":"ap-ready"'
$radio5Ready = $routerText -match '"id":"5g","lifecycle":"ap-ready"'
$radio2Visible = $scanText -match ("(?m)^SSID\s+\d+\s*:\s*" + [regex]::Escape($Radio2Ssid) + "\s*$")
$radio5Visible = $scanText -match ("(?m)^SSID\s+\d+\s*:\s*" + [regex]::Escape($Radio5Ssid) + "\s*$")
$radio2Hits = [regex]::Matches($scanText, "(?m)^SSID\s+\d+\s*:\s*" + [regex]::Escape($Radio2Ssid) + "\s*$").Count
$radio5Hits = [regex]::Matches($scanText, "(?m)^SSID\s+\d+\s*:\s*" + [regex]::Escape($Radio5Ssid) + "\s*$").Count
$wlanDelta = if ($null -ne $wlanBefore -and $null -ne $wlanAfter) { $wlanAfter - $wlanBefore } else { $null }
$wifiDelta = if ($null -ne $wifiBefore -and $null -ne $wifiAfter) { $wifiAfter - $wifiBefore } else { $null }

$classification = if ($scanRc -ne 0 -or $routerRc -ne 0) {
    "ERROR_CAPTURE"
} elseif ($radio2Visible -and $radio5Visible) {
    "PASS_BOTH_VISIBLE"
} elseif (-not $radio2Visible -and -not $radio5Visible -and $radio2Ready -and $radio5Ready -and $wlanDelta -gt 0 -and $wifiDelta -gt 0) {
    "CLIENT_SEES_NEITHER_ROUTER_TX_ADVANCES"
} else {
    "PARTIAL_VISIBILITY"
}

$result = [ordered]@{
    schema = "openmitrastar.dual-radio-visibility/v1"
    classification = $classification
    read_only = $true
    router = $RouterHost
    oracle = "$AelitaUser@$AelitaHost"
    scan_count = $ScanCount
    radio2 = [ordered]@{
        ssid = $Radio2Ssid
        router_ap_ready = $radio2Ready
        client_visible = $radio2Visible
        visible_scan_hits = $radio2Hits
        tx_packet_delta = $wlanDelta
    }
    radio5 = [ordered]@{
        ssid = $Radio5Ssid
        router_ap_ready = $radio5Ready
        client_visible = $radio5Visible
        visible_scan_hits = $radio5Hits
        tx_packet_delta = $wifiDelta
    }
    fatal_count = $fatalCount
    counter_interval_seconds = $CounterIntervalSeconds
    client_connection_changed = $false
    router_state_changed = $false
    created_at = (Get-Date).ToString("o")
}
$resultPath = Join-Path $output "result.json"
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $resultPath -Encoding ascii
[ordered]@{
    schema = "openmitrastar.aelita-scan-summary/v1"
    scan_count = $ScanCount
    radio2_ssid = $Radio2Ssid
    radio2_visible_scan_hits = $radio2Hits
    radio5_ssid = $Radio5Ssid
    radio5_visible_scan_hits = $radio5Hits
    raw_neighbor_scan_persisted = $false
} | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $output "aelita-scan-summary.json") -Encoding ascii
$result | ConvertTo-Json -Depth 5
Write-Output "OM_DUAL_RADIO_VISIBILITY_CAPTURE=$classification result=$resultPath"

if ($scanRc -ne 0 -or $routerRc -ne 0) { exit 20 }
exit 0
