[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
& python (Join-Path $root "tools\build_f185_web_provenance.py")
if ($LASTEXITCODE -ne 0) { throw "F185 composition failed" }
& python -m pytest -q `
    (Join-Path $root "versions\lyoko-foundation-1.5-f185\tests") `
    (Join-Path $root "tools\test_lyoko_web_parity_deliverables.py") `
    (Join-Path $root "tools\test_f185_web_provenance.py") `
    (Join-Path $root "tools\test_uart_ymodem_f165_pipeline.py")
if ($LASTEXITCODE -ne 0) { throw "F185 tests failed" }
Write-Output "OMF185_OFFLINE_BUILD_PASS=1"
Write-Output "OMF185_HARDWARE_ACTIONS=none"
