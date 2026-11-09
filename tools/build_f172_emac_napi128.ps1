[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

& python (Join-Path $root "tools\prepare_f172_emac_napi128_assets.py")
if ($LASTEXITCODE -ne 0) { throw "F172 kernel asset build failed" }

& python (Join-Path $root "tools\compose_f172_emac_napi128.py")
if ($LASTEXITCODE -ne 0) { throw "F172 image composition failed" }

& python -m pytest -q `
    (Join-Path $root "tools\test_f164_squashfs_product.py") `
    (Join-Path $root "tools\test_f165_squashfs_exact_mtd.py") `
    (Join-Path $root "tools\test_f166_emac_telemetry.py") `
    (Join-Path $root "tools\test_f167_emac_ownership_fix.py") `
    (Join-Path $root "tools\test_f170_lyoko_foundation_runtime_fix.py") `
    (Join-Path $root "tools\test_f171_lyoko_foundation_health_fix.py") `
    (Join-Path $root "tools\test_f172_emac_napi128.py") `
    (Join-Path $root "tools\test_uart_ymodem_f165_pipeline.py")
if ($LASTEXITCODE -ne 0) { throw "F172 tests failed" }

& python (Join-Path $root "tools\analyze_f172_emac_starvation.py") `
    --output (Join-Path $root "outputs\f3-certification\realtek-2g-f167-32m-20260901\f172-emac-starvation-analysis.json")
if ($LASTEXITCODE -ne 0) { throw "F172 evidence analysis failed" }

Write-Output "OMF172_OFFLINE_BUILD_PASS=1"
Write-Output "OMF172_HARDWARE_ACTIONS=none"
