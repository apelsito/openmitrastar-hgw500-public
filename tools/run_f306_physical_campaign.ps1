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
$requiredAck = "OPENMITRASTAR_F306_INTEGRATED_PHYSICAL"
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f306-device-bound"
$manifestPath = Join-Path $build "manifest.json"
$knownHosts = Join-Path $build "known_hosts.f306"
$expectedVersion = "lyoko-foundation-6.7.3-f306-unified-product-device"
$expectedSha256 = "a245ab177e9ce7688c638b34161265bcdc70c5d21da54715530801fe20e33dc2"
$expectedBytes = 5267456
$transferBytes = 33554432
$requiredMetrics = @(
    "rx_restart_reason_hw_demand", "mac_rx_progress_streak", "mac_rx_progress_streak_max",
    "rx_restart_last_mac_rx_progress_streak", "rx_restart_last_trigger_pokes"
)

function Test-Tcp([string]$HostName, [int]$TcpPort, [int]$TimeoutMs = 1200) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $pending = $client.BeginConnect($HostName, $TcpPort, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne($TimeoutMs)) { return $false }
        $client.EndConnect($pending)
        return $true
    } catch { return $false } finally { $client.Dispose() }
}

function Invoke-RouterWithRetry([string]$Label, [string]$Command) {
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
    throw "$Label failed after 5 attempts: $lastOutput"
}

function Get-RouterJsonWithRetry([string]$Label, [string]$Command) {
    try {
        $raw = Invoke-RouterWithRetry $Label $Command
        $jsonStart = $raw.IndexOf("{")
        if ($jsonStart -lt 0) { throw "JSON object not found" }
        return $raw.Substring($jsonStart) | ConvertFrom-Json
    } catch {
        throw "$Label returned invalid JSON: $($_.Exception.Message)"
    }
}

function Get-FatalCount {
    return [int](Invoke-RouterWithRetry "fatal marker read" "dmesg | grep -Eic 'kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset|qdrv.*fatal|muc.*fatal|auc.*fatal' || true")
}

if (-not (Test-Path -LiteralPath $manifestPath)) { throw "F306 manifest is missing" }
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.schema -ne "openmitrastar.f306-unified-product-candidate/v1" -or
    $manifest.artifacts.webformat.sha256 -ne $expectedSha256 -or
    [int64]$manifest.artifacts.webformat.bytes -ne $expectedBytes -or
    $manifest.integration.f301_kernel_artifacts_byte_identical -ne $true -or
    $manifest.integration.radio_payload_byte_identical_to_f301 -ne $true -or
    [int]$manifest.binary_contract.early_restart_samples -ne 2 -or
    [int]$manifest.binary_contract.fallback_restart_pokes -ne 16) {
    throw "F306 physical campaign artifact contract mismatch"
}

if (-not $OutputDir) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $OutputDir = Join-Path $root "outputs\f3-certification\f306-integrated-regression-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)

[ordered]@{
    schema = "openmitrastar.f306-physical-campaign-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    firmware = $expectedVersion
    candidate_sha256 = $expectedSha256
    router = $RouterHost
    oracle = "$OracleUser@$OracleHost"
    realtek_runs = 1
    realtek_bytes_per_direction = $transferBytes
    realtek_reason = "F306 kernel and radio payload are byte-identical to installed and physically accepted F301"
    radio5_profile = "f306"
    radio5_bytes_per_direction = $transferBytes
    radio5_soak_seconds = 120
    final_health = @{
        retries_per_read = 5
        separate_reads = @("firmware", "boot-state", "fatal-count", "radio2", "radio5", "diagnostics")
        monolithic_command = $false
    }
    flash = $false
    mtd_writes = $false
    hardware_preflight = if ($Execute) { "REQUIRED" } else { "DEFERRED_TO_EXECUTE" }
    hardware_actions_performed = $false
} | ConvertTo-Json -Depth 6

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing physical campaign: exact -Ack is required" }
if (-not (Test-Tcp $RouterHost 22)) { throw "Router SSH preflight failed" }
if (-not (Test-Tcp $OracleHost 22)) { throw "AELITA SSH preflight failed" }

$firmwareBefore = Invoke-RouterWithRetry "firmware identity" "sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release"
$bootBefore = Invoke-RouterWithRetry "boot state" "cat /run/openmitrastar/boot-state"
$radio2Before = Get-RouterJsonWithRetry "2.4 GHz state" "/usr/sbin/om-radioctl status 2g"
$radio5Before = Get-RouterJsonWithRetry "5 GHz state" "/usr/sbin/om-radioctl status 5g"
$diagnosticsBefore = Get-RouterJsonWithRetry "diagnostics" "OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET /usr/libexec/openmitrastar/om-api-v1 diagnostics"
$metricNamesBefore = @($diagnosticsBefore.emac.PSObject.Properties.Name)
if ($firmwareBefore -ne $expectedVersion -or $bootBefore -ne "ready" -or
    $radio2Before.lifecycle -ne "ap-ready" -or
    $radio5Before.lifecycle -notin @("ap-ready", "traffic-ready") -or
    $diagnosticsBefore.schema -ne "lyoko.api.diagnostics/v1" -or
    @($requiredMetrics | Where-Object { $_ -notin $metricNamesBefore }).Count -ne 0) {
    throw "F306 runtime, telemetry or dual-radio state is not ready"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\ensure_lyoko_speed_server.ps1") `
    -Action Ensure -Port 8008 -PayloadMiB 32 -AllowedClient $OracleHost
if ($LASTEXITCODE -ne 0) { throw "speed server preflight failed" }

try {
    $realtekDir = Join-Path $OutputDir "realtek-run-1"
    $fatalBefore = Get-FatalCount
    & python (Join-Path $root "tools\run_aelita_2g_wpa2_speed_router_probe.py") `
        --router-host $RouterHost --router-known-hosts $knownHosts `
        --oracle-host $OracleHost --oracle-user $OracleUser `
        --controller-url $ControllerUrl --traffic-direction both --interval 3 `
        --wait-result 360 --child-timeout 300 --recovery-window 120 `
        --restore-watchdog-minutes 5 --soak-seconds 120 --output-dir $realtekDir
    if ($LASTEXITCODE -ne 0) { throw "F306 Realtek regression failed" }
    $fatalAfter = Get-FatalCount
    $summaryPath = Join-Path $realtekDir "summary.json"
    if (-not (Test-Path -LiteralPath $summaryPath)) { throw "F306 Realtek summary is missing" }
    $summary = Get-Content -Raw -LiteralPath $summaryPath | ConvertFrom-Json
    $realtekPass = [bool](
        $summary.effective_aelita_rc -eq 0 -and
        $summary.effective_probe_rc -eq 0 -and
        $summary.timed_out -eq $false -and
        $summary.controller_download.pass -eq $true -and
        [int64]$summary.controller_download.bytes -ge $transferBytes -and
        $summary.controller_upload.pass -eq $true -and
        [int64]$summary.controller_upload.bytes -ge $transferBytes -and
        $summary.router_health_gate.pass -eq $true -and
        [int]$summary.emac_stats_last.napi_weight -eq 256 -and
        $fatalBefore -eq 0 -and $fatalAfter -eq 0
    )
    $realtekResult = [ordered]@{
        schema = "openmitrastar.f306-realtek-regression/v1"
        status = if ($realtekPass) { "PASS" } else { "FAIL" }
        summary = $summaryPath
        download_bytes = [int64]$summary.controller_download.bytes
        upload_bytes = [int64]$summary.controller_upload.bytes
        download_mbps = [math]::Round([double]$summary.controller_download.speed_Bps * 8 / 1000000, 3)
        upload_mbps = [math]::Round([double]$summary.controller_upload.speed_Bps * 8 / 1000000, 3)
        fatal_count_before = $fatalBefore
        fatal_count_after = $fatalAfter
        router_health = $summary.router_health_gate.pass
    }
    $realtekResultPath = Join-Path $OutputDir "realtek-result.json"
    $realtekResult | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $realtekResultPath -Encoding ascii
    if (-not $realtekPass) { throw "F306 Realtek regression result is not PASS" }

    $qtnDir = Join-Path $OutputDir "quantenna-sanity"
    & python (Join-Path $root "tools\run_f293_5g_aelita_traffic.py") `
        --profile f306 --execute --ack OPENMITRASTAR_F306_5G_AELITA_TRAFFIC `
        --router-host $RouterHost --oracle-host $OracleHost --oracle-user $OracleUser `
        --controller-url $ControllerUrl --soak-seconds 120 --output-dir $qtnDir
    if ($LASTEXITCODE -ne 0) { throw "F306 Quantenna traffic regression failed" }
    $qtnResult = Get-ChildItem -LiteralPath $qtnDir -Filter "result-*.json" |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $qtnResult) { throw "F306 Quantenna traffic result is missing" }
    $qtnData = Get-Content -Raw -LiteralPath $qtnResult.FullName | ConvertFrom-Json
    if ($qtnData.status -ne "PASS" -or
        [int64]$qtnData.download.bytes -lt $transferBytes -or
        [int64]$qtnData.upload.bytes -lt $transferBytes -or
        [int]$qtnData.soak.requested_seconds -lt 120 -or
        [int]$qtnData.soak.disconnects -ne 0) {
        throw "F306 Quantenna traffic result is not PASS"
    }

    $firmwareFinal = Invoke-RouterWithRetry "final firmware identity" "sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release"
    $bootFinal = Invoke-RouterWithRetry "final boot state" "cat /run/openmitrastar/boot-state"
    $fatalFinal = Get-FatalCount
    $radio2Final = Get-RouterJsonWithRetry "final 2.4 GHz state" "/usr/sbin/om-radioctl status 2g"
    $radio5Final = Get-RouterJsonWithRetry "final 5 GHz state" "/usr/sbin/om-radioctl status 5g"
    $diagnosticsFinal = Get-RouterJsonWithRetry "final diagnostics" "OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET /usr/libexec/openmitrastar/om-api-v1 diagnostics"
    $metricNamesFinal = @($diagnosticsFinal.emac.PSObject.Properties.Name)
    $finalChecks = [ordered]@{
        firmware = $firmwareFinal -eq $expectedVersion
        boot_ready = $bootFinal -eq "ready"
        fatal_zero = $fatalFinal -eq 0 -and [int]$diagnosticsFinal.fatal_count -eq 0
        radio2_ready = $radio2Final.lifecycle -eq "ap-ready"
        radio5_ready = $radio5Final.lifecycle -in @("ap-ready", "traffic-ready")
        diagnostics_schema = $diagnosticsFinal.schema -eq "lyoko.api.diagnostics/v1"
        f300_metrics_present = @($requiredMetrics | Where-Object { $_ -notin $metricNamesFinal }).Count -eq 0
    }
    if (@($finalChecks.Values | Where-Object { $_ -ne $true }).Count -ne 0) {
        throw "F306 final health did not pass"
    }

    [ordered]@{
        schema = "openmitrastar.f306-physical-campaign/v1"
        status = "PASS"
        firmware = $expectedVersion
        realtek = $realtekResultPath
        radio5 = $qtnResult.FullName
        final_health = $finalChecks
        final_diagnostics = $diagnosticsFinal
        flash = $false
        mtd_writes = $false
    } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $OutputDir "campaign.json") -Encoding ascii
    Write-Output "OMF306_PHYSICAL_CAMPAIGN_PASS=1 output=$OutputDir"
} finally {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\ensure_lyoko_speed_server.ps1") `
        -Action Stop -Port 8008 -AllowedClient $OracleHost | Out-Null
}

