[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

& python (Join-Path $root "tools\build_f223_emac_rxring256.py")
if ($LASTEXITCODE -ne 0) { throw "F223 build failed" }

& python -m pytest -q `
    (Join-Path $root "tools\test_f223_emac_rxring256.py") `
    (Join-Path $root "tools\test_f222_signed_feed_fix.py") `
    (Join-Path $root "tools\test_uart_ymodem_f165_pipeline.py")
if ($LASTEXITCODE -ne 0) { throw "F223 tests failed" }

Write-Output "OMF223_OFFLINE_BUILD_PASS=1"
Write-Output "OMF223_HARDWARE_ACTIONS=none"
