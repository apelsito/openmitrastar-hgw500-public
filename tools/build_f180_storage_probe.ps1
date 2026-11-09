[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
& python (Join-Path $root "tools\build_f180_storage_probe.py")
if ($LASTEXITCODE -ne 0) { throw "F180 storage probe build failed" }
& python -m pytest -q `
    (Join-Path $root "tools\test_f172_emac_napi128.py") `
    (Join-Path $root "tools\test_f179_integrated_candidate.py") `
    (Join-Path $root "tools\test_f180_storage_probe.py") `
    (Join-Path $root "tools\test_simulate_f178_preserving_flash.py")
if ($LASTEXITCODE -ne 0) { throw "F180 tests failed" }
Write-Output "OMF180_STORAGE_PROBE_OFFLINE_PASS=1"
Write-Output "OMF180_HARDWARE_ACTIONS=none"
