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
$requiredAck = "OPENMITRASTAR_F299_HW_DEMAND_EARLY_RESTART_PHYSICAL"
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f299-device-bound"
$manifestPath = Join-Path $build "manifest.json"
$knownHosts = Join-Path $build "known_hosts.f299"
$baseline = Join-Path $root "outputs\f3-certification\f290-emac-restart-context-20260903\f290-evaluation.json"
$expectedVersion = "lyoko-foundation-6.5.2-f299-emac-hw-demand-early-restart-device"
$expectedSha256 = "92ddc564fc264e3e7e0e1fd1300e798af959bf6c4280f8972a0b8dba20c6221a"
$expectedBytes = 5259264

function Test-Tcp([string]$HostName, [int]$TcpPort, [int]$TimeoutMs = 1200) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $pending = $client.BeginConnect($HostName, $TcpPort, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne($TimeoutMs)) { return $false }
        $client.EndConnect($pending)
        return $true
    } catch { return $false } finally { $client.Dispose() }
}

function Invoke-Router([string]$Command) {
    $ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
    $lastOutput = ""
    foreach ($attempt in 1..5) {
        $output = & $ssh -i "$env:USERPROFILE\.ssh\id_ed25519" -o IdentitiesOnly=yes -o BatchMode=yes `
            -o ConnectTimeout=8 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$knownHosts" `
            -o LogLevel=ERROR "root@$RouterHost" $Command 2>&1
        $lastOutput = ($output | Out-String).Trim()
        if ($LASTEXITCODE -eq 0) { return $lastOutput }
        if ($attempt -lt 5) { Start-Sleep -Seconds 3 }
    }
    throw "router SSH command failed after 5 attempts: $lastOutput"
}

function Get-FatalCount {
    $value = Invoke-Router "dmesg | grep -Eic 'kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset|qdrv.*fatal|muc.*fatal|auc.*fatal' || true"
    return [int]$value
}

if (-not (Test-Path -LiteralPath $manifestPath) -or -not (Test-Path -LiteralPath $baseline)) {
    throw "F299 manifest or F290 baseline is missing"
}
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.schema -ne "openmitrastar.f299-emac-hw-demand-early-restart-from-f293/v1" -or
    $manifest.artifacts.webformat.sha256 -ne $expectedSha256 -or
    [int64]$manifest.artifacts.webformat.bytes -ne $expectedBytes -or
    [int]$manifest.binary_contract.fallback_restart_pokes -ne 16 -or
    [int]$manifest.binary_contract.early_restart_samples -ne 4) {
    throw "F299 physical campaign artifact contract mismatch"
}

if (-not $OutputDir) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $OutputDir = Join-Path $root "outputs\f3-certification\f299-emac-hw-demand-early-restart-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)

[ordered]@{
    schema = "openmitrastar.f299-physical-campaign-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    firmware = $expectedVersion
    candidate_sha256 = $expectedSha256
    router = $RouterHost
    oracle = "$OracleUser@$OracleHost"
    realtek_runs = 3
    bytes_per_direction = 33554432
    required_median_ratio_to_f290 = 0.95
    required_early_restart = @{
        reason = "rx_restart_reason_hw_demand"
        trigger_pokes_less_than = 16
        minimum_mac_progress_streak = 4
        mac_ingress = $true
    }
    radio5_requirement = "32 MiB each direction plus 120-second sustained client traffic"
    flash = $false
    mtd_writes = $false
    hardware_preflight = if ($Execute) { "REQUIRED" } else { "DEFERRED_TO_EXECUTE" }
    hardware_actions_performed = $false
} | ConvertTo-Json -Depth 5

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing physical campaign: exact -Ack is required" }
if (-not (Test-Tcp $RouterHost 22)) { throw "Router SSH preflight failed" }
if (-not (Test-Tcp $OracleHost 22)) { throw "AELITA SSH preflight failed" }

$runtimeProbeCommand = 'set +e; printf ''FIRMWARE=''; sed -n ''s/^OPENMITRASTAR_PRODUCT_VERSION=//p'' /etc/openmitrastar/release; printf ''BOOT=''; cat /run/openmitrastar/boot-state 2>/dev/null; stats=/sys/bus/platform/devices/e8000000.ethernet/lyoko_emac_stats; printf ''NAPI=''; sed -n ''s/^napi_weight=//p'' "$stats" 2>/dev/null; printf ''DEMAND_REASON=''; grep -c ''^rx_restart_reason_hw_demand='' "$stats" 2>/dev/null; printf ''TRIGGER_POKES=''; grep -c ''^rx_restart_last_trigger_pokes='' "$stats" 2>/dev/null; printf ''DEMAND_STREAK=''; grep -c ''^rx_restart_last_mac_rx_progress_streak='' "$stats" 2>/dev/null; printf ''RADIO2=''; /usr/sbin/om-radioctl status 2g 2>/dev/null; printf ''RADIO5=''; /usr/sbin/om-radioctl status 5g 2>/dev/null'
$runtimeReady = $false
$runtimeProbe = ""
foreach ($attempt in 1..24) {
    $runtimeProbe = Invoke-Router $runtimeProbeCommand
    $runtimeReady = (
        $runtimeProbe -match "(?m)^FIRMWARE=$([regex]::Escape($expectedVersion))\s*$" -and
        $runtimeProbe -match "(?m)^BOOT=ready\s*$" -and
        $runtimeProbe -match "(?m)^NAPI=256\s*$" -and
        $runtimeProbe -match "(?m)^DEMAND_REASON=1\s*$" -and
        $runtimeProbe -match "(?m)^TRIGGER_POKES=1\s*$" -and
        $runtimeProbe -match "(?m)^DEMAND_STREAK=1\s*$" -and
        $runtimeProbe -match '(?m)^RADIO2=.*"lifecycle"\s*:\s*"ap-ready"' -and
        $runtimeProbe -match '(?m)^RADIO5=.*"lifecycle"\s*:\s*"(ap-ready|traffic-ready)"'
    )
    if ($runtimeReady) { break }
    Start-Sleep -Seconds 5
}
if (-not $runtimeReady) {
    throw "F299 runtime, telemetry or dual-radio health did not converge: $runtimeProbe"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\ensure_lyoko_speed_server.ps1") `
    -Action Ensure -Port 8008 -PayloadMiB 32 -AllowedClient $OracleHost
if ($LASTEXITCODE -ne 0) { throw "speed server preflight failed" }

try {
    $summaries = @()
    foreach ($runNumber in 1..3) {
        $runDir = Join-Path $OutputDir ("realtek-run-{0}" -f $runNumber)
        $fatalBefore = Get-FatalCount
        & python (Join-Path $root "tools\run_aelita_2g_wpa2_speed_router_probe.py") `
            --router-host $RouterHost --router-known-hosts $knownHosts `
            --oracle-host $OracleHost --oracle-user $OracleUser `
            --controller-url $ControllerUrl --traffic-direction both --interval 3 `
            --wait-result 360 --child-timeout 300 --recovery-window 120 `
            --restore-watchdog-minutes 5 --soak-seconds 120 --output-dir $runDir
        if ($LASTEXITCODE -ne 0) { throw "F299 Realtek run $runNumber failed" }
        $fatalAfter = Get-FatalCount
        $summaryPath = Join-Path $runDir "summary.json"
        if (-not (Test-Path -LiteralPath $summaryPath)) { throw "missing F299 summary for run $runNumber" }
        $summary = Get-Content -Raw -LiteralPath $summaryPath | ConvertFrom-Json
        $summary | Add-Member -NotePropertyName fatal_count_before -NotePropertyValue $fatalBefore -Force
        $summary | Add-Member -NotePropertyName fatal_count_after -NotePropertyValue $fatalAfter -Force
        $evaluationSummary = Join-Path $runDir "evaluation-summary.json"
        $summary | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $evaluationSummary -Encoding ascii
        $summaries += $evaluationSummary
    }

    $evaluation = Join-Path $OutputDir "f299-evaluation.json"
    $evalArgs = @(
        (Join-Path $root "tools\evaluate_f299_emac_hw_demand_early_restart_result.py"),
        "--baseline", $baseline
    )
    foreach ($summary in $summaries) { $evalArgs += @("--candidate-summary", $summary) }
    $evalArgs += @("--output", $evaluation)
    & python @evalArgs
    $evaluationRc = $LASTEXITCODE
    if ($evaluationRc -eq 2) { throw "F299 early branch was not observed; campaign is PARTIAL" }
    if ($evaluationRc -ne 0) { throw "F299 physical acceptance thresholds failed" }
    $evaluationData = Get-Content -Raw -LiteralPath $evaluation | ConvertFrom-Json
    if ($evaluationData.status -ne "PASS") { throw "F299 evaluator did not return PASS" }

    $qtnDir = Join-Path $OutputDir "quantenna-sanity"
    & python (Join-Path $root "tools\run_f293_5g_aelita_traffic.py") `
        --profile f299 --execute --ack OPENMITRASTAR_F299_5G_AELITA_TRAFFIC `
        --router-host $RouterHost --oracle-host $OracleHost --oracle-user $OracleUser `
        --controller-url $ControllerUrl --soak-seconds 120 --output-dir $qtnDir
    if ($LASTEXITCODE -ne 0) { throw "F299 Quantenna traffic sanity gate failed" }

    $qtnResult = Get-ChildItem -LiteralPath $qtnDir -Filter "result-*.json" |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $qtnResult) { throw "F299 Quantenna traffic result is missing" }
    $qtnData = Get-Content -Raw -LiteralPath $qtnResult.FullName | ConvertFrom-Json
    if ($qtnData.status -ne "PASS") { throw "F299 Quantenna traffic result is not PASS" }

    $finalHealth = Invoke-Router 'set -eu; test "$(cat /run/openmitrastar/boot-state)" = ready; test "$(dmesg | grep -Eic ''kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset|qdrv.*fatal|muc.*fatal|auc.*fatal'' || true)" = 0; /usr/sbin/om-radioctl status 2g | grep -Eq ''"lifecycle"[[:space:]]*:[[:space:]]*"ap-ready"''; /usr/sbin/om-radioctl status 5g | grep -Eq ''"lifecycle"[[:space:]]*:[[:space:]]*"(ap-ready|traffic-ready)"''; echo OMF299_FINAL_HEALTH_PASS'
    if ($finalHealth -notmatch "OMF299_FINAL_HEALTH_PASS") { throw "F299 final dual-radio health gate failed" }

    [ordered]@{
        schema = "openmitrastar.f299-physical-campaign/v1"
        status = "PASS"
        firmware = $expectedVersion
        realtek_evaluation = $evaluation
        early_restart_proven = $true
        radio5_health = "PASS"
        radio5_traffic = $qtnResult.FullName
        flash = $false
        mtd_writes = $false
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $OutputDir "campaign.json") -Encoding ascii
    Write-Output "OMF299_PHYSICAL_CAMPAIGN_PASS=1 output=$OutputDir"
} finally {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\ensure_lyoko_speed_server.ps1") `
        -Action Stop -Port 8008 -AllowedClient $OracleHost | Out-Null
}
