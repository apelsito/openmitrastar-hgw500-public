[CmdletBinding()]
param(
    [string]$BundleDirectory = "outputs\aelita-testbench\lyoko-aelita-testbench-recovery-20260902",
    [string]$ZipPath = "outputs\aelita-testbench\lyoko-aelita-testbench-recovery-20260902.zip",
    [string]$GeneratedAt = "2026-09-02T00:00:00Z"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$bundle = [IO.Path]::GetFullPath((Join-Path $root $BundleDirectory))
$zip = [IO.Path]::GetFullPath((Join-Path $root $ZipPath))
$allowed = [IO.Path]::GetFullPath((Join-Path $root "outputs\aelita-testbench"))
if (-not $bundle.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase) -or
    -not $zip.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) {
    throw "bundle paths must remain under outputs/aelita-testbench"
}

$publicKeySource = Join-Path $root "outputs\kernel-port\realtek-loop\wifi-oracle-server\oracle_ed25519.pub"
if (-not (Test-Path -LiteralPath $publicKeySource)) { throw "missing AELITA controller public key" }
New-Item -ItemType Directory -Force -Path $bundle | Out-Null
Copy-Item -LiteralPath $publicKeySource -Destination (Join-Path $bundle "oracle_ed25519.pub") -Force

$payloadFiles = Get-ChildItem -LiteralPath $bundle -File | Where-Object { $_.Name -notin @("manifest.json", "SHA256SUMS") } | Sort-Object Name
$items = @($payloadFiles | ForEach-Object {
    [ordered]@{
        file = $_.Name
        bytes = $_.Length
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
    }
})
$manifest = [ordered]@{
    schema = "openmitrastar.aelita-testbench-recovery-bundle/v1"
    generated_at = $GeneratedAt
    target = "authorized Windows Wi-Fi testbench"
    controller_ip = "192.168.1.43"
    expected_wifi_mac = "CC-6B-1E-77-2D-5B"
    contains_private_keys = $false
    router_changes = $false
    firmware_changes = $false
    files = $items
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $bundle "manifest.json") -Encoding ascii
$sumFiles = Get-ChildItem -LiteralPath $bundle -File | Where-Object { $_.Name -ne "SHA256SUMS" } | Sort-Object Name
($sumFiles | ForEach-Object { "$((Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant())  $($_.Name)" }) -join "`n" | Set-Content -LiteralPath (Join-Path $bundle "SHA256SUMS") -Encoding ascii
$fixedTimestamp = [DateTimeOffset]::Parse($GeneratedAt).UtcDateTime
Get-ChildItem -LiteralPath $bundle -File | ForEach-Object { $_.LastWriteTimeUtc = $fixedTimestamp }

if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path (Join-Path $bundle "*") -DestinationPath $zip -CompressionLevel Optimal
[ordered]@{
    status = "PASS"
    zip = $zip
    bytes = (Get-Item -LiteralPath $zip).Length
    sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLowerInvariant()
    contains_private_keys = $false
} | ConvertTo-Json -Depth 4
