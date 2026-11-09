[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
& python (Join-Path $root "tools\build_f188_diagnostics_ui.py")
if ($LASTEXITCODE -ne 0) { throw "F188 composition failed" }
& python -m pytest -q `
    (Join-Path $root "versions\lyoko-foundation-1.8-f188\tests") `
    (Join-Path $root "tools\test_lyoko_web_parity_deliverables.py") `
    (Join-Path $root "tools\test_f188_diagnostics_ui.py") `
    (Join-Path $root "tools\test_uart_ymodem_f165_pipeline.py")
if ($LASTEXITCODE -ne 0) { throw "F188 tests failed" }
Write-Output "OMF188_OFFLINE_BUILD_PASS=1"
Write-Output "OMF188_HARDWARE_ACTIONS=none"
