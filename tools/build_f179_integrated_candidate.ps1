[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
& python (Join-Path $root "tools\build_f179_integrated_napi_package_manager.py")
if ($LASTEXITCODE -ne 0) { throw "F179 composition failed" }
& python -m pytest -q `
    (Join-Path $root "tools\test_f172_emac_napi128.py") `
    (Join-Path $root "tools\test_f176_lyoko_package_ui.py") `
    (Join-Path $root "tools\test_f177_lyoko_package_manager.py") `
    (Join-Path $root "tools\test_f179_integrated_candidate.py") `
    (Join-Path $root "tools\test_uart_ymodem_f165_pipeline.py")
if ($LASTEXITCODE -ne 0) { throw "F179 tests failed" }
Write-Output "OMF179_OFFLINE_BUILD_PASS=1"
Write-Output "OMF179_HARDWARE_ACTIONS=none"
