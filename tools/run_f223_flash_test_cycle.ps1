[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [string]$OracleHost = "192.168.1.63",
    [string]$OracleUser = "AELITA",
    [string]$ControllerUrl = "http://192.168.1.43:8008/speed.bin"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$requiredAck = "OPENMITRASTAR_F223_FLASH_TEST_A63CCCE6"
$candidateSha = "a63ccce69776732269ac4c08f29062c74b93eda945c88778ab63efd9215be2bc"
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f223-device-bound"
$candidate = Join-Path $build "openmitrastar-linux510-f223-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin"
$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$output = Join-Path $root "outputs\f3-certification\f223-full-cycle-$stamp"

$manifest = Get-Content -Raw -LiteralPath (Join-Path $build "manifest.json") | ConvertFrom-Json
$actualSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant()
if ($actualSha -ne $candidateSha -or $manifest.artifacts.webformat.sha256 -ne $candidateSha) {
    throw "F223 candidate hash mismatch"
}
if ($manifest.binary_contract.result -ne "PASS" -or
    $manifest.binary_contract.rx_ring_descriptors -ne 256 -or
    $manifest.binary_contract.napi_weight -ne 128) {
    throw "F223 binary contract mismatch"
}

[ordered]@{
    mode = if ($Execute) { "execute" } else { "dry-run" }
    target = "mtd4/linux_live"
    candidate = $candidate
    bytes = [long]$manifest.artifacts.webformat.bytes
    sha256 = $candidateSha
    sequence = @("flash", "platform-gate", "package-regression", "2g-three-run", "5g-32m-120s")
    rollback_artifact = "F222"
    integrated_candidate_after_pass = "F228 HOLD"
} | ConvertTo-Json -Depth 5

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing full cycle: exact -Ack is required" }
New-Item -ItemType Directory -Force -Path $output | Out-Null

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\promote_f223_mtd4_direct.ps1") `
    -Execute -Ack OPENMITRASTAR_F223_RXRING256_A63CCCE6 -Port $Port -RouterHost $RouterHost
if ($LASTEXITCODE -ne 0) { throw "F223 flash/platform gate failed" }

& python (Join-Path $root "tools\post_flash_f219_package_gate.py") `
    --host $RouterHost --expected-version lyoko-foundation-3.7-f222-device `
    --known-hosts (Join-Path $build "known_hosts.f223") `
    --output-dir (Join-Path $output "package-regression")
if ($LASTEXITCODE -ne 0) { throw "F223 package regression failed" }

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\run_f223_physical_campaign.ps1") `
    -Execute -Ack OPENMITRASTAR_F223_RXRING256_PHYSICAL -RouterHost $RouterHost `
    -OracleHost $OracleHost -OracleUser $OracleUser -ControllerUrl $ControllerUrl `
    -OutputDir (Join-Path $output "radio2")
if ($LASTEXITCODE -ne 0) { throw "F223 2.4 GHz campaign failed" }

& python (Join-Path $root "tools\run_f151_5g_bridge_trial.py") `
    --execute --ack OPENMITRASTAR_F151_5G_BRIDGE_TRIAL --router-host $RouterHost `
    --seconds 120 --transfer-mib 32 --transfer-timeout-seconds 90 `
    --persistent-bridge `
    --expected-qdrv-sha 0ef6cac2fe68ba62dcba21c4878b9d4697d8e6560579bf74f3ed9a5ae09c0dff `
    --expected-wlan-sha f4f6099b43dd675dd44e7021374f1ea2f4380a4d9d9fd81b1d35ea411984897f `
    --output-dir (Join-Path $output "radio5")
if ($LASTEXITCODE -ne 0) { throw "F223 5 GHz regression failed" }

[ordered]@{
    schema = "openmitrastar.f223-full-cycle/v1"
    status = "PASS"
    candidate_sha256 = $candidateSha
    target = "mtd4/linux_live"
    platform = "PASS"
    packages = "PASS"
    radio2 = "PASS"
    radio5 = "PASS"
    next_candidate = "F228"
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $output "result.json") -Encoding ascii

Write-Output "OMF223_FULL_CYCLE_PASS=1 output=$output"
