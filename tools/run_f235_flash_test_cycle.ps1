[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if ($Execute) {
    throw "F235 is superseded and must not be flashed; use the next hardened candidate after its gates pass"
}
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$requiredAck = "OPENMITRASTAR_F235_FLASH_TEST_E8984886"
$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$output = Join-Path $root "outputs\f3-certification\f235-dual-control-cycle-$stamp"

[ordered]@{
    schema = "openmitrastar.f235-flash-test-cycle-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    target = "mtd4/linux_live"
    candidate_sha256 = "e8984886b169b49d8459b66cafd1c2445a63498a28c95f62211ddd7f841f5b5e"
    sequence = @("flash", "platform-gate", "2g-control-apply-rollback", "5g-control-apply-rollback")
    protected = @("mtd0", "mtd1", "mtd2", "mtd3/linux_safety", "mtd5")
    client_traffic = "separate follow-up gate required"
} | ConvertTo-Json -Depth 5

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing full cycle: exact -Ack is required" }
New-Item -ItemType Directory -Force -Path $output | Out-Null

& pwsh.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\promote_f235_mtd4_direct.ps1") `
    -Execute -Ack OPENMITRASTAR_F235_DUAL_CONTROL_E8984886 -Port $Port -RouterHost $RouterHost
if ($LASTEXITCODE -ne 0) { throw "F235 flash/platform gate failed" }

& pwsh.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\run_f235_dual_radio_control_postflash_gate.ps1") `
    -Execute -Ack OPENMITRASTAR_F235_DUAL_RADIO_CONTROL_PHYSICAL -RouterHost $RouterHost `
    -OutputDir (Join-Path $output "radio-control")
if ($LASTEXITCODE -ne 0) { throw "F235 dual-radio control gate failed" }

[ordered]@{
    schema = "openmitrastar.f235-flash-test-cycle/v1"
    status = "PASS"
    target = "mtd4/linux_live"
    candidate_sha256 = "e8984886b169b49d8459b66cafd1c2445a63498a28c95f62211ddd7f841f5b5e"
    platform = "PASS"
    radio2_control = "PASS"
    radio5_control = "PASS"
    client_traffic = "NOT_RUN"
    integrated_candidate_after_pass = "F236 HOLD"
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output "result.json") -Encoding ascii

Write-Output "OMF235_FLASH_TEST_CYCLE_PASS=1 output=$output"
