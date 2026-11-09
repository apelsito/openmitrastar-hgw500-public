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
$requiredAck = "OPENMITRASTAR_F287_NAPI256_PHYSICAL"
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f287-device-bound"
$knownHosts = Join-Path $build "known_hosts.f287"
$baseline = Join-Path $root "outputs\f3-certification\f285-realtek-2g-current-evaluation-20260903.json"
$expectedVersion = "lyoko-foundation-6.4.0-f287-emac-napi256-device"

if (-not $OutputDir) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $OutputDir = Join-Path $root "outputs\f3-certification\f287-emac-napi256-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
$manifest = Get-Content -Raw -LiteralPath (Join-Path $build "manifest.json") | ConvertFrom-Json

[ordered]@{
    schema = "openmitrastar.f287-physical-campaign-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    firmware = $expectedVersion
    router = $RouterHost
    oracle = "$OracleUser@$OracleHost"
    realtek_runs = 3
    bytes_per_direction = 33554432
    expected_rx_ring = 256
    expected_napi_weight = 256
    quantenna_sanity_seconds = 120
    candidate_sha256 = $manifest.artifacts.webformat.sha256
    flash = $false
    router_mutation = $false
    client_wifi_temporary_mutation = $Execute.IsPresent
} | ConvertTo-Json -Depth 4

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing physical campaign: exact -Ack is required" }

$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$probe = & $ssh -i "$env:USERPROFILE\.ssh\id_ed25519" -o IdentitiesOnly=yes -o BatchMode=yes `
    -o ConnectTimeout=8 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$knownHosts" -o LogLevel=ERROR `
    "root@$RouterHost" 'set -eu; test "$(sed -n ''s/^OPENMITRASTAR_PRODUCT_VERSION=//p'' /etc/openmitrastar/release)" = lyoko-foundation-6.4.0-f287-emac-napi256-device; test "$(cat /run/openmitrastar/boot-state)" = ready; grep -q "^napi_weight=256$" /sys/bus/platform/devices/e8000000.ethernet/lyoko_emac_stats; dmesg | grep -Eq ''descriptor.*DDR.*tx=1024.*rx=4096''; echo OMF287_RUNTIME_PREFLIGHT_PASS'
if ($LASTEXITCODE -ne 0 -or $probe -notcontains "OMF287_RUNTIME_PREFLIGHT_PASS") {
    throw "F287 runtime identity, NAPI or RX ring preflight failed"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\ensure_lyoko_speed_server.ps1") -Action Ensure -Port 8008 -PayloadMiB 32 -AllowedClient $OracleHost
if ($LASTEXITCODE -ne 0) { throw "speed server preflight failed" }

try {
    $summaries = @()
    foreach ($run in 1..3) {
        $runDir = Join-Path $OutputDir ("realtek-run-{0}" -f $run)
        & python (Join-Path $root "tools\run_aelita_2g_wpa2_speed_router_probe.py") `
            --router-host $RouterHost --router-known-hosts $knownHosts `
            --oracle-host $OracleHost --oracle-user $OracleUser `
            --controller-url $ControllerUrl --traffic-direction both --interval 3 `
            --wait-result 360 --child-timeout 300 --recovery-window 120 `
            --restore-watchdog-minutes 5 --soak-seconds 120 --output-dir $runDir
        if ($LASTEXITCODE -ne 0) { throw "F287 Realtek run $run failed" }
        $summary = Join-Path $runDir "summary.json"
        if (-not (Test-Path -LiteralPath $summary)) { throw "missing F287 summary for run $run" }
        $summaries += $summary
    }

    $evaluation = Join-Path $OutputDir "f287-evaluation.json"
    $evalArgs = @((Join-Path $root "tools\evaluate_f287_emac_napi256_result.py"), "--baseline", $baseline)
    foreach ($summary in $summaries) { $evalArgs += @("--candidate-summary", $summary) }
    $evalArgs += @("--output", $evaluation)
    & python @evalArgs
    if ($LASTEXITCODE -ne 0) { throw "F287 NAPI-256 hard acceptance thresholds failed" }
    $evaluationData = Get-Content -Raw -LiteralPath $evaluation | ConvertFrom-Json

    $qtnDir = Join-Path $OutputDir "quantenna-sanity"
    & python (Join-Path $root "tools\run_f287_5g_aelita_traffic.py") `
        --execute --ack OPENMITRASTAR_F287_5G_AELITA_TRAFFIC `
        --router-host $RouterHost --oracle-host $OracleHost --oracle-user $OracleUser `
        --controller-url $ControllerUrl --soak-seconds 120 --output-dir $qtnDir
    if ($LASTEXITCODE -ne 0) { throw "F287 Quantenna sanity gate failed" }

    [ordered]@{
        schema = "openmitrastar.f287-physical-campaign/v1"
        status = if ($evaluationData.status -eq "PASS") { "PASS" } else { "PARTIAL" }
        datapath_decision = $evaluationData.decision
        firmware = $expectedVersion
        realtek_evaluation = $evaluation
        quantenna_evidence = $qtnDir
        flash = $false
        router_mutation = $false
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutputDir "campaign.json") -Encoding ascii
    Write-Output "OMF287_PHYSICAL_CAMPAIGN_PASS=1 output=$OutputDir"
} finally {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\ensure_lyoko_speed_server.ps1") -Action Stop -Port 8008 -AllowedClient $OracleHost | Out-Null
}
