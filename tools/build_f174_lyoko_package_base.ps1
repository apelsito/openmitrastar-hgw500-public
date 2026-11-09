[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

& python (Join-Path $root "tools\build_f174_lyoko_package_base.py")
if ($LASTEXITCODE -ne 0) { throw "F174 image composition failed" }

& python -m pytest -q `
    (Join-Path $root "tools\test_lyoko_ipk.py") `
    (Join-Path $root "tools\test_f171_lyoko_foundation_health_fix.py") `
    (Join-Path $root "tools\test_f173_lyoko_hardware_inventory.py") `
    (Join-Path $root "tools\test_f174_lyoko_package_base.py")
if ($LASTEXITCODE -ne 0) { throw "F174 tests failed" }

Write-Output "OMF174_OFFLINE_BUILD_PASS=1"
Write-Output "OMF174_HARDWARE_ACTIONS=none"
