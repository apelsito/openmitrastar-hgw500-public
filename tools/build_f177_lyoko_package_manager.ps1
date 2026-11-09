[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
& python (Join-Path $root "tools\build_f177_lyoko_package_manager.py")
if ($LASTEXITCODE -ne 0) { throw "F177 image composition failed" }
& wsl.exe -d podman-mem9-tidb -u root -e sh -n /workspace/user-home/Desktop/MitraStar/versions/lyoko-foundation-1.3-dev/overlay/usr/bin/lyoko-pkg
if ($LASTEXITCODE -ne 0) { throw "lyoko-pkg shell syntax failed" }
& python -m pytest -q `
    (Join-Path $root "versions\lyoko-foundation-1.3-dev\tests\test_foundation.py") `
    (Join-Path $root "versions\lyoko-foundation-1.3-dev\tests\test_router_api_v1.py") `
    (Join-Path $root "tools\test_lyoko_ipk.py") `
    (Join-Path $root "tools\test_lyoko_pkgbox.py") `
    (Join-Path $root "tools\test_f176_lyoko_package_ui.py") `
    (Join-Path $root "tools\test_f177_lyoko_package_manager.py")
if ($LASTEXITCODE -ne 0) { throw "F177 tests failed" }
Write-Output "OMF177_OFFLINE_BUILD_PASS=1"
Write-Output "OMF177_HARDWARE_ACTIONS=none"
