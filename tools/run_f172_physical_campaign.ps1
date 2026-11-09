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
$requiredAck = "OPENMITRASTAR_F172_PHYSICAL_CAMPAIGN"
$baseline = Join-Path $root "outputs\f3-certification\realtek-2g-f167-32m-20260901\summary.json"

if (-not $OutputDir) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $OutputDir = Join-Path $root "outputs\f3-certification\f172-emac-napi128-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
$candidate = Join-Path $root "work\mission-state\q3-persistent-composite-f172-emac-napi128-from-f171\build\openmitrastar-linux510-q3-persistent-f172-emac-napi128-from-f171-LZMA-OFFLINE-NO-FLASH.webformat.bin"
$manifestPath = Join-Path (Split-Path $candidate) "manifest.json"
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json

[ordered]@{
    mode = if ($Execute) { "execute" } else { "dry-run" }
    router = $RouterHost
    oracle = $OracleHost
    runs = 3
    bytes_per_direction = 33554432
    expected_napi_weight = 128
    candidate = $candidate
    candidate_sha256 = $manifest.artifacts.webformat.sha256
    flash = $false
    router_mutation = $false
    client_wifi_temporary_mutation = $Execute.IsPresent
} | ConvertTo-Json -Depth 4

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing physical campaign: exact -Ack is required" }
if (-not (Test-Path -LiteralPath $baseline)) { throw "missing F167 baseline" }

$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$probe = & $ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 `
    -i "$env:USERPROFILE\.ssh\id_ed25519" "root@$RouterHost" `
    "cat /run/openmitrastar/boot-state; grep '^napi_weight=128$' /sys/bus/platform/devices/e8000000.ethernet/lyoko_emac_stats"
if ($LASTEXITCODE -ne 0 -or ($probe -notcontains "ready") -or ($probe -notcontains "napi_weight=128")) {
    throw "F172 runtime identity or ready state not proven"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$summaries = @()
for ($run = 1; $run -le 3; $run++) {
    $runDir = Join-Path $OutputDir ("run-{0}" -f $run)
    & python (Join-Path $root "tools\run_aelita_2g_wpa2_speed_router_probe.py") `
        --router-host $RouterHost `
        --oracle-host $OracleHost `
        --oracle-user $OracleUser `
        --controller-url $ControllerUrl `
        --traffic-direction both `
        --interval 3 `
        --wait-result 300 `
        --child-timeout 240 `
        --recovery-window 90 `
        --restore-watchdog-minutes 5 `
        --soak-seconds 10 `
        --output-dir $runDir
    if ($LASTEXITCODE -ne 0) { throw "F172 physical run $run failed" }
    $summary = Join-Path $runDir "summary.json"
    if (-not (Test-Path -LiteralPath $summary)) { throw "missing summary for F172 run $run" }
    $summaries += $summary
}

$evaluation = Join-Path $OutputDir "f172-evaluation.json"
$args = @((Join-Path $root "tools\evaluate_f172_emac_napi128_result.py"), "--baseline", $baseline)
foreach ($summary in $summaries) { $args += @("--candidate-summary", $summary) }
$args += @("--output", $evaluation)
& python @args
if ($LASTEXITCODE -ne 0) { throw "F172 physical campaign did not meet acceptance thresholds" }

[ordered]@{
    schema = "openmitrastar.f172-physical-campaign/v1"
    status = "PASS"
    candidate_sha256 = $manifest.artifacts.webformat.sha256
    runs = $summaries
    evaluation = $evaluation
    flash = $false
    router_mutation = $false
    oracle_restored_after_each_run = $true
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $OutputDir "campaign.json") -Encoding ascii

Write-Output "OMF172_PHYSICAL_CAMPAIGN_PASS=1 output=$OutputDir"
