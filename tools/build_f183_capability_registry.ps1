[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
& python (Join-Path $root "tools\build_f183_capability_registry.py")
if ($LASTEXITCODE -ne 0) { throw "F183 image composition failed" }
& python -m pytest -q `
    (Join-Path $root "versions\lyoko-foundation-1.4-f183\tests\test_foundation.py") `
    (Join-Path $root "versions\lyoko-foundation-1.4-f183\tests\test_router_api_v1.py") `
    (Join-Path $root "tools\test_f177_lyoko_package_manager.py") `
    (Join-Path $root "tools\test_f183_capability_registry.py")
if ($LASTEXITCODE -ne 0) { throw "F183 tests failed" }
Write-Output "OMF183_CAPABILITY_REGISTRY_PASS=1"
Write-Output "OMF183_HARDWARE_ACTIONS=none"
