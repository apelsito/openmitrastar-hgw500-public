[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
& python (Join-Path $root "tools\build_f187_session_ui.py")
if ($LASTEXITCODE -ne 0) { throw "F187 composition failed" }
& python -m pytest -q `
    (Join-Path $root "versions\lyoko-foundation-1.7-f187\tests") `
    (Join-Path $root "tools\test_lyoko_web_parity_deliverables.py") `
    (Join-Path $root "tools\test_f187_session_ui.py") `
    (Join-Path $root "tools\test_uart_ymodem_f165_pipeline.py")
if ($LASTEXITCODE -ne 0) { throw "F187 tests failed" }
Write-Output "OMF187_OFFLINE_BUILD_PASS=1"
Write-Output "OMF187_HARDWARE_ACTIONS=none"
