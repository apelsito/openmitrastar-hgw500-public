[CmdletBinding()]
param(
    [string]$Distro = "podman-mem9-tidb",
    [string]$WslUser = "root",
    [string]$KernelSource = "/home/user/mitrastar-linux-5.10.260",
    [string]$BuildRoot = "/home/user/openmitrastar-build"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function ConvertTo-WslPath {
    param([Parameter(Mandatory)][string]$WindowsPath)

    $fullPath = [System.IO.Path]::GetFullPath($WindowsPath)
    if ($fullPath -notmatch '^(?<drive>[A-Za-z]):\\(?<path>.*)$') {
        throw "Only drive-letter Windows paths are supported: $fullPath"
    }

    $drive = $Matches.drive.ToLowerInvariant()
    $path = $Matches.path.Replace('\', '/')
    return "/mnt/$drive/$path"
}

function Invoke-TimedNative {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$ArgumentList
    )

    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $output = & $FilePath @ArgumentList 2>&1
    $exitCode = $LASTEXITCODE
    $timer.Stop()

    [pscustomobject]@{
        ExitCode = $exitCode
        ElapsedMs = $timer.ElapsedMilliseconds
        Output = @($output)
    }
}

$wslCommand = Get-Command wsl.exe -ErrorAction Stop
$projectRootWindows = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$projectRootWsl = ConvertTo-WslPath -WindowsPath $projectRootWindows
$toolchainPrefix = "$projectRootWsl/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"

$listTimer = [System.Diagnostics.Stopwatch]::StartNew()
$rawList = (& $wslCommand.Source --list --verbose 2>&1) -join "`n"
$listExitCode = $LASTEXITCODE
$listTimer.Stop()
if ($listExitCode -ne 0) {
    throw "Unable to list WSL distributions (exit $listExitCode): $rawList"
}

$cleanList = $rawList -replace "`0", ""
$escapedDistro = [regex]::Escape($Distro)
if ($cleanList -notmatch "(?m)^\s*\*?\s*$escapedDistro\s+") {
    throw "Required WSL distribution '$Distro' is not installed."
}
$wasRunning = $cleanList -match "(?mi)^\s*\*?\s*$escapedDistro\s+Running\s+2\s*$"

# One WSL process both starts a stopped distro and validates the complete build
# environment. Building directly in WSL avoids the Podman remote-client round trip.
$probe = @'
set -eu

fail() {
    printf 'CHECK_FAIL=%s\n' "$1" >&2
    exit 20
}

test -d "$OM_PROJECT" || fail "project:$OM_PROJECT"
test -f "$OM_PROJECT/tools/build_topaz_linux_510.sh" || fail "build-script"
test -f "$OM_SOURCE/Makefile" || fail "kernel-source:$OM_SOURCE"
test -x "${OM_TOOLCHAIN}gcc" || fail "toolchain:${OM_TOOLCHAIN}gcc"
test -d "$OM_OUTPUT" || fail "build-root:$OM_OUTPUT"
test -w "$OM_OUTPUT" || fail "build-root-not-writable:$OM_OUTPUT"

printf 'CHECK_OK=distro:%s\n' "${WSL_DISTRO_NAME:-unknown}"
printf 'CHECK_OK=user:%s\n' "$(id -un)"
printf 'CHECK_OK=project:%s\n' "$OM_PROJECT"
printf 'CHECK_OK=source:%s\n' "$OM_SOURCE"
printf 'CHECK_OK=output:%s\n' "$OM_OUTPUT"
printf 'CHECK_OK=toolchain:%s\n' "$("${OM_TOOLCHAIN}gcc" --version | sed -n '1p')"

image="$OM_OUTPUT/ramssh/arch/arc/boot/uImage.bin"
if test -f "$image"; then
    printf 'CHECK_OK=last-ramssh:%s bytes sha256=%s\n' \
        "$(wc -c < "$image" | tr -d ' ')" \
        "$(sha256sum "$image" | cut -d ' ' -f 1)"
else
    printf 'CHECK_INFO=last-ramssh:none\n'
fi

command -v podman >/dev/null 2>&1 && \
    printf 'CHECK_INFO=podman:available-not-invoked\n' || \
    printf 'CHECK_INFO=podman:not-required\n'
'@
$probeEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($probe))
$probeBootstrap = "printf '%s' '$probeEncoded' | base64 -d | sh"

$arguments = @(
    "-d", $Distro,
    "-u", $WslUser,
    "--",
    "env",
    "OM_PROJECT=$projectRootWsl",
    "OM_SOURCE=$KernelSource",
    "OM_OUTPUT=$BuildRoot",
    "OM_TOOLCHAIN=$toolchainPrefix",
    "sh", "-c", $probeBootstrap
)
$probeResult = Invoke-TimedNative -FilePath $wslCommand.Source -ArgumentList $arguments

foreach ($line in $probeResult.Output) {
    Write-Host $line
}
if ($probeResult.ExitCode -ne 0) {
    throw "OpenMitraStar environment validation failed (exit $($probeResult.ExitCode))."
}

$env:OPENMITRASTAR_WSL_DISTRO = $Distro
$env:OPENMITRASTAR_WSL_USER = $WslUser
$env:TOPAZ_KERNEL_SRC = $KernelSource
$env:TOPAZ_BUILD_ROOT = $BuildRoot

$mode = if ($wasRunning) { "reused-running" } else { "started" }
Write-Host "OPENMITRASTAR_ENV_READY distro=$Distro mode=$mode list_ms=$($listTimer.ElapsedMilliseconds) probe_ms=$($probeResult.ElapsedMs)"
Write-Host "OPENMITRASTAR_BUILD_HINT wsl.exe -d $Distro -u $WslUser -- env TOPAZ_INCREMENTAL=1 sh '$projectRootWsl/tools/build_topaz_linux_510.sh' ramssh"

[pscustomobject]@{
    Ready = $true
    Distro = $Distro
    User = $WslUser
    Mode = $mode
    ProjectRoot = $projectRootWsl
    KernelSource = $KernelSource
    BuildRoot = $BuildRoot
    ListMilliseconds = $listTimer.ElapsedMilliseconds
    ProbeMilliseconds = $probeResult.ElapsedMs
}
