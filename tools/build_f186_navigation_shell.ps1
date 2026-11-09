[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
& python (Join-Path $root "tools\build_f186_navigation_shell.py")
if ($LASTEXITCODE -ne 0) { throw "F186 composition failed" }
& python -m pytest -q `
    (Join-Path $root "versions\lyoko-foundation-1.6-f186\tests") `
    (Join-Path $root "tools\test_lyoko_web_parity_deliverables.py") `
    (Join-Path $root "tools\test_f186_navigation_shell.py") `
    (Join-Path $root "tools\test_uart_ymodem_f165_pipeline.py")
if ($LASTEXITCODE -ne 0) { throw "F186 tests failed" }
Write-Output "OMF186_OFFLINE_BUILD_PASS=1"
Write-Output "OMF186_HARDWARE_ACTIONS=none"
