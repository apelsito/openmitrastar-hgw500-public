[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
& python (Join-Path $root "tools\build_f184_integrated_capabilities.py")
if ($LASTEXITCODE -ne 0) { throw "F184 composition failed" }
& python -m pytest -q `
    (Join-Path $root "tools\test_f172_emac_napi128.py") `
    (Join-Path $root "tools\test_f177_lyoko_package_manager.py") `
    (Join-Path $root "tools\test_f183_capability_registry.py") `
    (Join-Path $root "tools\test_f184_integrated_capabilities.py") `
    (Join-Path $root "tools\test_uart_ymodem_f165_pipeline.py")
if ($LASTEXITCODE -ne 0) { throw "F184 tests failed" }
Write-Output "OMF184_OFFLINE_BUILD_PASS=1"
Write-Output "OMF184_HARDWARE_ACTIONS=none"
