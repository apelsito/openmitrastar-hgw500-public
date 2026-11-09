[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
& python (Join-Path $root "tools\build_f182_spi_probe_boot.py")
if ($LASTEXITCODE -ne 0) { throw "F182 image composition failed" }
& wsl.exe -d podman-mem9-tidb -u root -e sh -n /workspace/user-home/Desktop/MitraStar/versions/lyoko-spi-probe-1.0/overlay/etc/init.d/S31-spi-probe
if ($LASTEXITCODE -ne 0) { throw "F182 init script syntax failed" }
& python -m pytest -q `
    (Join-Path $root "tools\test_f180_storage_probe.py") `
    (Join-Path $root "tools\test_f181_spi_readonly_probe.py") `
    (Join-Path $root "tools\test_f182_spi_probe_boot.py")
if ($LASTEXITCODE -ne 0) { throw "F182 tests failed" }
Write-Output "OMF182_SPI_BOOT_PROBE_PASS=1"
Write-Output "OMF182_HARDWARE_ACTIONS=none"
