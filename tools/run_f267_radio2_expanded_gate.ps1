[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$RouterHost = "192.168.1.90",
    [string]$KeyPath = "$HOME\.ssh\id_ed25519",
    [string]$KnownHostsPath = "$HOME\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f267-device-bound\known_hosts.f267",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$requiredAck = "OPENMITRASTAR_F267_RADIO2_EXPANDED_CONTROL"
$expectedVersion = "lyoko-foundation-6.1.0-f267-radio-workbench-device"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
if (-not $OutputDir) { $OutputDir = Join-Path $root "outputs\postflash\f267-radio2-expanded-$stamp" }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$key = [IO.Path]::GetFullPath($KeyPath)
$knownHosts = [IO.Path]::GetFullPath($KnownHostsPath)

function Invoke-Router([string]$Command) {
    $output = & $ssh -i $key -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 `
        -o ServerAliveInterval=5 -o ServerAliveCountMax=3 -o ConnectionAttempts=1 `
        -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$knownHosts" -o LogLevel=ERROR "root@$RouterHost" $Command 2>&1
    [pscustomobject]@{ Rc = $LASTEXITCODE; Text = ($output -join "`n") }
}

function Read-JsonBody([string]$Text) {
    $line = ($Text -split "`r?`n" | Where-Object { $_ -match '^\{' } | Select-Object -Last 1)
    if (-not $line) { throw "No JSON payload in router response" }
    $line | ConvertFrom-Json
}

function Get-RadioContract([string]$Band) {
    $result = Invoke-Router "/usr/sbin/om-radioctl contract $Band"
    if ($result.Rc -ne 0) { throw "Cannot read $Band contract: $($result.Text)" }
    Read-JsonBody $result.Text
}

function Assert-PlatformHealthy {
    $result = Invoke-Router 'test -e /sys/class/net/br0/brif/eth0 -a -e /sys/class/net/br0/brif/wlan0 -a -e /sys/class/net/br0/brif/wifi0 && /usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 ping && /usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping && test "$(cat /run/openmitrastar/boot-state)" = ready && test "$(dmesg | grep -Eic ''MuC:.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|Misaligned Access'')" = 0'
    if ($result.Rc -ne 0 -or ([regex]::Matches($result.Text, 'PONG')).Count -lt 2) { throw "Platform health gate failed: $($result.Text)" }
}

$plan = [ordered]@{
    schema = "openmitrastar.f267-radio2-expanded-gate-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    router = $RouterHost
    required_firmware = $expectedVersion
    mutations = @("channel", "bandwidth", "ssid_broadcast", "client_isolation", "wmm", "short_gi", "beacon_interval", "dtim_period", "max_clients")
    rollback = "mandatory"
    five_ghz_mutation = $false
    flash = $false
    uart = $false
}
$plan | ConvertTo-Json -Depth 5
if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing physical gate: exact -Ack is required" }

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$release = Invoke-Router "sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release"
if ($release.Rc -ne 0 -or $release.Text.Trim() -ne $expectedVersion) { throw "Expected F267 runtime is not installed" }
Assert-PlatformHealthy
$before = Get-RadioContract "2g"
$before5 = Get-RadioContract "5g"
$status = $before.snapshot.status
$channel = if ([int]$status.channel -eq 6) { 1 } else { 6 }
$bandwidth = if ([int]$status.bandwidth -eq 40) { 20 } else { 40 }
$broadcast = if ([bool]$status.ssid_broadcast) { "false" } else { "true" }
$isolation = if ([bool]$status.client_isolation) { "false" } else { "true" }
$shortGi = if ([bool]$status.short_gi) { "false" } else { "true" }
$beacon = if ([int]$status.beacon_interval -eq 120) { 100 } else { 120 }
$dtim = if ([int]$status.dtim_period -eq 2) { 3 } else { 2 }
$maxClients = if ([int]$status.max_clients -eq 24) { 32 } else { 24 }
$body = "channel=$channel&bandwidth=$bandwidth&ssid_broadcast=$broadcast&client_isolation=$isolation&wmm=true&short_gi=$shortGi&beacon_interval=$beacon&dtim_period=$dtim&max_clients=$maxClients"
$owner = -join ((1..64) | ForEach-Object { '0123456789abcdef'[(Get-Random -Maximum 16)] })
$stage = Invoke-Router "printf '%s' '$body' | OM_CONFIG_OWNER=$owner /usr/sbin/om-radioctl stage_config 2g"
if ($stage.Rc -ne 0) { throw "2g stage failed: $($stage.Text)" }
$stageJson = Read-JsonBody $stage.Text
$transactionId = [string]$stageJson.transaction_id
if ($transactionId -notmatch '^[0-9a-f]{64}$') { throw "Invalid transaction id" }
$applied = $false
try {
    $apply = Invoke-Router "OM_CONFIG_OWNER=$owner OM_CONFIG_TXN_ID=$transactionId /usr/sbin/om-radioctl apply_config"
    if ($apply.Rc -ne 0) { throw "2g apply failed: $($apply.Text)" }
    $applyJson = Read-JsonBody $apply.Text
    if ($applyJson.verified -ne $true) { throw "2g apply did not verify" }
    $applied = $true
    Start-Sleep -Seconds 8
    Assert-PlatformHealthy
    $tested = Get-RadioContract "2g"
    foreach ($entry in @{ channel=$channel; bandwidth=$bandwidth; ssid_broadcast=$broadcast; client_isolation=$isolation; wmm='true'; short_gi=$shortGi; beacon_interval=$beacon; dtim_period=$dtim; max_clients=$maxClients }.GetEnumerator()) {
        if ([string]$tested.snapshot.status.($entry.Key) -ne [string]$entry.Value) { throw "2g readback mismatch: $($entry.Key)" }
    }
} finally {
    if ($applied) {
        $rollback = Invoke-Router "OM_CONFIG_OWNER=$owner OM_CONFIG_TXN_ID=$transactionId /usr/sbin/om-radioctl rollback_config"
        if ($rollback.Rc -ne 0 -or (Read-JsonBody $rollback.Text).verified -ne $true) { throw "2g rollback failed: $($rollback.Text)" }
    }
}

Start-Sleep -Seconds 8
Assert-PlatformHealthy
$restored = Get-RadioContract "2g"
$after5 = Get-RadioContract "5g"
foreach ($keyName in @("channel", "bandwidth", "ssid_broadcast", "client_isolation", "wmm", "short_gi", "beacon_interval", "dtim_period", "max_clients")) {
    if ([string]$restored.snapshot.status.$keyName -ne [string]$before.snapshot.status.$keyName) { throw "2g rollback mismatch: $keyName" }
}
foreach ($keyName in @("state", "ssid", "channel", "bandwidth", "tx_power_dbm", "region")) {
    if ([string]$after5.snapshot.status.$keyName -ne [string]$before5.snapshot.status.$keyName) { throw "5g changed unexpectedly: $keyName" }
}

$result = [ordered]@{
    schema = "openmitrastar.f267-radio2-expanded-gate/v1"
    generated_at = [DateTime]::UtcNow.ToString("o")
    firmware = $expectedVersion
    tested = @{ channel=$channel; bandwidth=$bandwidth; ssid_broadcast=$broadcast; client_isolation=$isolation; wmm=$true; short_gi=$shortGi; beacon_interval=$beacon; dtim_period=$dtim; max_clients=$maxClients }
    restored = $true
    five_ghz_unchanged = $true
    platform = "PASS"
    status = "PASS"
}
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDir "result.json") -Encoding ascii
Write-Output "OMF267_RADIO2_EXPANDED_GATE_PASS=1 output=$OutputDir"
