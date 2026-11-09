[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
& wsl.exe -d podman-mem9-tidb -u root -e sh /workspace/user-home/Desktop/MitraStar/tools/prepare_f175_network_config.sh
if ($LASTEXITCODE -ne 0) { throw "F175 network config resolution failed" }
& python -m pytest -q (Join-Path $root "tools/test_f175_network_config.py")
if ($LASTEXITCODE -ne 0) { throw "F175 network config tests failed" }
Write-Output "OMF175_CONFIG_ONLY_PASS=1"
