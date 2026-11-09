[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

& python (Join-Path $root "tools\build_f173_lyoko_hardware_inventory.py")
if ($LASTEXITCODE -ne 0) { throw "F173 image composition failed" }

& python -m pytest -q `
    (Join-Path $root "versions\lyoko-foundation-1.1-dev\tests\test_foundation.py") `
    (Join-Path $root "versions\lyoko-foundation-1.1-dev\tests\test_router_api_v1.py") `
    (Join-Path $root "tools\test_f170_lyoko_foundation_runtime_fix.py") `
    (Join-Path $root "tools\test_f171_lyoko_foundation_health_fix.py") `
    (Join-Path $root "tools\test_f173_lyoko_hardware_inventory.py")
if ($LASTEXITCODE -ne 0) { throw "F173 tests failed" }

Write-Output "OMF173_OFFLINE_BUILD_PASS=1"
Write-Output "OMF173_HARDWARE_ACTIONS=none"
