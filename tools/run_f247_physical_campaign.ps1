[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$RouterHost = "192.168.1.90",
    [string]$OracleHost = "192.168.1.63",
    [string]$OracleUser = "AELITA",
    [string]$ControllerUrl = "http://192.168.1.43:8008/speed.bin",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$requiredAck = "OPENMITRASTAR_F247_RXRING256_PHYSICAL"
$expectedVersion = "lyoko-foundation-4.9-f245-device"
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f247-device-bound"
$knownHosts = Join-Path $build "known_hosts.f247"
$baseline = Join-Path $root "outputs\f3-certification\f219-realtek-2g-napi128-evaluation.json"

if (-not $OutputDir) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $OutputDir = Join-Path $root "outputs\f3-certification\f247-emac-rxring256-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
$manifest = Get-Content -Raw -LiteralPath (Join-Path $build "manifest.json") | ConvertFrom-Json
if ($manifest.schema -ne "openmitrastar.f247-integrated-physical-test-candidate/v1" -or
    $manifest.candidate_eligible -ne $true -or $manifest.flash_supported -ne $true -or
    $manifest.integration.kernel_contract.rx_ring_descriptors -ne 256 -or
    $manifest.integration.kernel_contract.napi_weight -ne 128) {
    throw "F247 physical campaign manifest mismatch"
}

[ordered]@{
    mode = if ($Execute) { "execute" } else { "dry-run" }
    router = $RouterHost
    oracle = $OracleHost
    runs = 3
    bytes_per_direction = 33554432
    expected_rx_ring = 256
    expected_napi_weight = 128
    candidate_sha256 = $manifest.artifacts.webformat.sha256
    required_firmware = $expectedVersion
    flash = $false
    router_mutation = $false
    client_wifi_temporary_mutation = $Execute.IsPresent
} | ConvertTo-Json -Depth 4

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing physical campaign: exact -Ack is required" }

$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$probe = & $ssh -i "$env:USERPROFILE\.ssh\id_ed25519" -o IdentitiesOnly=yes -o BatchMode=yes `
    -o ConnectTimeout=8 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$knownHosts" -o LogLevel=ERROR `
    "root@$RouterHost" 'sed -n "s/^OPENMITRASTAR_PRODUCT_VERSION=//p" /etc/openmitrastar/release; cat /run/openmitrastar/boot-state; grep "^napi_weight=128$" /sys/bus/platform/devices/e8000000.ethernet/lyoko_emac_stats; dmesg | grep "descriptor DDR" | tail -1'
if ($LASTEXITCODE -ne 0 -or ($probe -notcontains $expectedVersion) -or ($probe -notcontains "ready") -or ($probe -notcontains "napi_weight=128") -or -not ($probe -match "tx=1024 rx=4096")) {
    throw "F247 runtime identity or ready state not proven"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$summaries = @()
for ($run = 1; $run -le 3; $run++) {
    $runDir = Join-Path $OutputDir ("run-{0}" -f $run)
    & python (Join-Path $root "tools\run_aelita_2g_wpa2_speed_router_probe.py") `
        --router-host $RouterHost --oracle-host $OracleHost --oracle-user $OracleUser `
        --controller-url $ControllerUrl --traffic-direction both --interval 3 `
        --wait-result 300 --child-timeout 240 --recovery-window 90 `
        --restore-watchdog-minutes 5 --soak-seconds 10 --output-dir $runDir
    if ($LASTEXITCODE -ne 0) { throw "F247 physical run $run failed" }
    $summary = Join-Path $runDir "summary.json"
    if (-not (Test-Path -LiteralPath $summary)) { throw "missing summary for F247 run $run" }
    $runResult = Get-Content -Raw -LiteralPath $summary | ConvertFrom-Json
    if ([long]$runResult.controller_download.bytes -lt 33554432 -or [long]$runResult.controller_upload.bytes -lt 33554432) {
        throw "F247 physical run $run transferred fewer than 32 MiB per direction"
    }
    $fatal = & $ssh -i "$env:USERPROFILE\.ssh\id_ed25519" -o IdentitiesOnly=yes -o BatchMode=yes `
        -o ConnectTimeout=8 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$knownHosts" -o LogLevel=ERROR `
        "root@$RouterHost" 'dmesg | grep -Eic "MuC:.*exception|MuC has halted|QMAC.*(fatal|halt)|DMA.*(fatal|error)|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|Misaligned Access|Machine Check" || true'
    if ($LASTEXITCODE -ne 0 -or [int]($fatal | Select-Object -Last 1) -ne 0) { throw "F247 fatal marker after physical run $run" }
    $summaries += $summary
}

$evaluation = Join-Path $OutputDir "f247-evaluation.json"
$args = @((Join-Path $root "tools\evaluate_f223_emac_rxring256_result.py"), "--baseline", $baseline)
foreach ($summary in $summaries) { $args += @("--candidate-summary", $summary) }
$args += @("--output", $evaluation)
& python @args
if ($LASTEXITCODE -ne 0) { throw "F247 physical campaign did not meet acceptance thresholds" }

Write-Output "OMF247_PHYSICAL_CAMPAIGN_PASS=1 output=$OutputDir"
