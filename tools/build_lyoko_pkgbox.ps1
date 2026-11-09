[CmdletBinding(PositionalBinding = $false)]
param()

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$script = "/workspace/user-home/Desktop/MitraStar/tools/build_lyoko_pkgbox.sh"

& wsl.exe -d podman-mem9-tidb -u root -e sh $script
if ($LASTEXITCODE -ne 0) { throw "Lyoko pkgbox build failed" }

& python -m pytest -q `
    (Join-Path $root "tools/test_lyoko_ipk.py") `
    (Join-Path $root "tools/test_lyoko_pkgbox.py")
if ($LASTEXITCODE -ne 0) { throw "Lyoko IPK tests failed" }

Write-Output "LYOKO_PKGBOX_OFFLINE_PASS=1"
