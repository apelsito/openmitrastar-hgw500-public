param(
    [switch]$ExecuteRam,
    [string]$AckRamOnly = "",
    [string]$HostAddress = "192.168.1.90",
    [Parameter(Mandatory = $true)]
    [string]$ClientIp,
    [Parameter(Mandatory = $true)]
    [string]$ClientMac,
    [string]$UartLog = "",
    [int]$Count = 5000,
    [int]$PayloadBytes = 1400,
    [int]$IntervalUs = 1000,
    [int]$SettleMs = 2000
)

$ErrorActionPreference = "Stop"
$AckValue = "OPENMITRASTAR_REALTEK_V4_PERF_RAM_ONLY"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$ExecTool = Join-Path $PSScriptRoot "ramssh_exec.py"
$UploadTool = Join-Path $PSScriptRoot "ramssh_upload.py"
$PerfTool = Join-Path $Root "outputs\kernel-port\realtek-perf-v4\om_icmp_perf"
$PerfSha = "8c6fd3cccc7443f90c3ca271899e0c0322fb5cb75763cdfb2310a85549ac2286"
$RemoteTool = "/tmp/om_icmp_perf"

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        return (($algorithm.ComputeHash($stream) | ForEach-Object { $_.ToString("x2") }) -join '')
    } finally {
        $algorithm.Dispose()
        $stream.Dispose()
    }
}

foreach ($required in @($ExecTool, $UploadTool, $PerfTool)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing input: $required" }
}
if ((Get-Sha256 $PerfTool) -ne $PerfSha) {
    throw "om_icmp_perf identity mismatch"
}
if ($ClientIp -notmatch '^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$') { throw "Invalid client IPv4" }
if ($ClientMac -notmatch '^(?i:[0-9a-f]{2}:){5}[0-9a-f]{2}$') { throw "Invalid client MAC" }
if ($Count -lt 100 -or $Count -gt 20000) { throw "Count must be 100..20000" }
if ($PayloadBytes -lt 64 -or $PayloadBytes -gt 1400) { throw "PayloadBytes must be 64..1400" }
if ($IntervalUs -lt 500 -or $IntervalUs -gt 100000) { throw "IntervalUs must be 500..100000" }
if ($SettleMs -lt 500 -or $SettleMs -gt 10000) { throw "SettleMs must be 500..10000" }

$Plan = [ordered]@{
    schema = "openmitrastar.realtek-v4-local-perf/v1"
    mode = if ($ExecuteRam) { "EXECUTE_RAM" } else { "DRY_RUN" }
    classification = "RAM-ONLY-NO-FLASH"
    host = $HostAddress
    client_ip = $ClientIp
    client_mac = $ClientMac.ToLowerInvariant()
    traffic = [ordered]@{
        protocol = "ICMP echo local router-client"
        count = $Count
        payload_bytes = $PayloadBytes
        interval_us = $IntervalUs
        settle_ms = $SettleMs
        target_wire_mbps = [math]::Round((($PayloadBytes + 8) * 8) / $IntervalUs, 3)
    }
    gates = @("UART pre-traffic marker", "station present", "management SSH after load", "no fatal UART", "HT RX decode marker")
    flash_supported = $false
    persistent_writes_supported = $false
}
$Plan | ConvertTo-Json -Depth 6
if (-not $ExecuteRam) {
    Write-Output "OMRTL_V4_PERF_DRY_RUN_PASS=1"
    exit 0
}
if ($AckRamOnly -cne $AckValue) { throw "Execution requires exact -AckRamOnly $AckValue" }
if (-not $UartLog -or -not (Test-Path -LiteralPath $UartLog -PathType Leaf)) {
    throw "Execution requires -UartLog pointing at the active COM3 capture"
}
$UartLog = [IO.Path]::GetFullPath($UartLog)

function Invoke-Remote([string]$Command, [string]$Label, [int]$Timeout = 40) {
    $saved = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & python $ExecTool $Command --host $HostAddress --timeout $Timeout 2>&1
        $rc = $LASTEXITCODE
    } finally { $ErrorActionPreference = $saved }
    if ($rc -ne 0) { throw "$Label failed (exit $rc): $($output -join ' ')" }
    return @($output)
}

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Evidence = Join-Path $Root "outputs\kernel-port\realtek-perf-v4\hardware-$Stamp-RAM-ONLY"
New-Item -ItemType Directory -Force -Path $Evidence | Out-Null
$Transcript = Join-Path $Evidence "perf-transcript.log"

$CaptureToken = "OMRTL_V4_PERF_CAPTURE_ARMED_" + (Get-Date -Format "yyyyMMddHHmmssfff")
Invoke-Remote "printf '$CaptureToken\n' >/dev/ttyS0" "uart-marker" | Out-Null
$deadline = (Get-Date).AddSeconds(12)
while ((Get-Date) -lt $deadline) {
    if ((Get-Content -LiteralPath $UartLog -Raw -ErrorAction SilentlyContinue) -match [regex]::Escape($CaptureToken)) { break }
    Start-Sleep -Milliseconds 300
}
if ((Get-Content -LiteralPath $UartLog -Raw) -notmatch [regex]::Escape($CaptureToken)) {
    throw "UART capture did not record the pre-traffic marker"
}

& python $UploadTool $PerfTool $RemoteTool --host $HostAddress --mode 0700 *> $null
if ($LASTEXITCODE -ne 0) { throw "om_icmp_perf upload failed" }

$Snapshot = @'
echo __IRQ28__
awk '$1 == "28:" { print $2 }' /proc/interrupts
echo __IRQ20__
awk '$1 == "20:" { print $2 }' /proc/interrupts
echo __WLAN__
for n in rx_bytes tx_bytes rx_packets tx_packets rx_dropped tx_dropped; do printf '%s=' "$n"; cat /sys/class/net/wlan0/statistics/$n; done
echo __STATION__
IW=/tmp/openmitrastar-ap/bundle/bin/iw
[ -x "$IW" ] || IW=/usr/sbin/iw
$IW dev wlan0 station get CLIENT_MAC
'@.Replace("CLIENT_MAC", $ClientMac.ToLowerInvariant())

$before = Invoke-Remote $Snapshot "snapshot-before" 40
$before | Set-Content -LiteralPath (Join-Path $Evidence "before.txt") -Encoding UTF8
$before | Tee-Object -FilePath $Transcript | Write-Output

$expectedSeconds = [math]::Ceiling(($Count * $IntervalUs) / 1000000) + [math]::Ceiling($SettleMs / 1000) + 20
$perfCommand = "$RemoteTool $ClientIp $Count $PayloadBytes $IntervalUs $SettleMs"
$perf = Invoke-Remote $perfCommand "local-icmp-perf" $expectedSeconds
$perf | Tee-Object -FilePath $Transcript -Append | Write-Output
$perfText = $perf -join "`n"
if ($perfText -notmatch 'OMICMPPERF target=.* sent=([0-9]+) received=([0-9]+).* tx_kbps=([0-9]+) rx_kbps=([0-9]+) loss_permille=([0-9]+)') {
    throw "om_icmp_perf output contract missing"
}
$Sent = [int64]$Matches[1]
$Received = [int64]$Matches[2]
$TxKbps = [int64]$Matches[3]
$RxKbps = [int64]$Matches[4]
$LossPermille = [int]$Matches[5]

$after = Invoke-Remote $Snapshot "snapshot-after" 40
$after | Set-Content -LiteralPath (Join-Path $Evidence "after.txt") -Encoding UTF8
$after | Tee-Object -FilePath $Transcript -Append | Write-Output
Invoke-Remote "true" "management-ssh-after" 15 | Out-Null

$uart = Get-Content -LiteralPath $UartLog -Raw
$Fatal = [bool]($uart -match 'Kernel panic|\bOops\b|BUG:|Unable to handle kernel|hard LOCKUP|soft lockup')
$RateMarker = [bool]($uart -match 'OMRTL92 stage=rx-rate-decode ht=1')
$TxMarker = [bool]($uart -match 'OMRTL stage=tx-complete')
$StationAfter = $after -join "`n"
$RxStillOne = [bool]($StationAfter -match '(?m)^\s*rx bitrate:\s*1\.0 MBit/s\s*$')

$Result = [ordered]@{
    schema = "openmitrastar.realtek-v4-local-perf-result/v1"
    classification = "RAM-ONLY-NO-FLASH"
    target = $ClientIp
    sent = $Sent
    received = $Received
    tx_kbps = $TxKbps
    rx_kbps = $RxKbps
    loss_permille = $LossPermille
    uart_rate_decode = $RateMarker
    uart_tx_completion = $TxMarker
    rx_still_reported_1mbps = $RxStillOne
    fatal_uart = $Fatal
    management_ssh_after = $true
    performance_threshold_enforced = $false
    pass = ($Sent -eq $Count -and $Received -gt 0 -and $RateMarker -and -not $Fatal -and -not $RxStillOne)
    evidence = $Evidence
    flash_actions = $false
}
$Result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Evidence "result.json") -Encoding UTF8
$Result | ConvertTo-Json -Depth 5
if (-not $Result.pass) { throw "V4 local perf diagnostic failed; see $Evidence" }
Write-Output "OMRTL_V4_PERF_PASS=1 tx_kbps=$TxKbps rx_kbps=$RxKbps loss_permille=$LossPermille evidence=$Evidence"
