[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
& python (Join-Path $root "tools\build_f176_lyoko_package_ui.py")
if ($LASTEXITCODE -ne 0) { throw "F176 image composition failed" }
& python -m pytest -q `
    (Join-Path $root "versions\lyoko-foundation-1.2-f176\tests\test_foundation.py") `
    (Join-Path $root "versions\lyoko-foundation-1.2-f176\tests\test_router_api_v1.py") `
    (Join-Path $root "tools\test_f174_lyoko_package_base.py") `
    (Join-Path $root "tools\test_f176_lyoko_package_ui.py")
if ($LASTEXITCODE -ne 0) { throw "F176 tests failed" }
Write-Output "OMF176_OFFLINE_BUILD_PASS=1"
Write-Output "OMF176_HARDWARE_ACTIONS=none"
