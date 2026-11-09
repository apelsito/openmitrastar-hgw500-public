[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
& python (Join-Path $root "tools\build_f181_spi_readonly_probe.py")
if ($LASTEXITCODE -ne 0) { throw "F181 SPI probe build failed" }
& python -m pytest -q (Join-Path $root "tools\test_f181_spi_readonly_probe.py")
if ($LASTEXITCODE -ne 0) { throw "F181 SPI probe tests failed" }
Write-Output "OMF181_SPI_READONLY_PROBE_PASS=1"
Write-Output "OMF181_HARDWARE_ACTIONS=none"
