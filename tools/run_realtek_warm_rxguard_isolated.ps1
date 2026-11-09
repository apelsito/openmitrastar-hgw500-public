param(
    [switch]$ExecuteRam,
    [string]$AckRamOnly = "",
    [Parameter(Mandatory = $true)]
    [string]$PskFile,
    [string]$HostAddress = "192.168.1.200",
    [string]$Ssid = "OpenMitraStar-RXGuard",
    [switch]$AutoDiscoverClient,
    [string]$ClientMac = "",
    [string]$UartLog = "",
    [int]$AssociationTimeoutSeconds = 180,
    [int]$WatchdogSeconds = 300,
    [string]$RealtekBundle = "outputs\kernel-port\realtek-loop\rx-rate-tx-v4-RAM-ONLY-NO-FLASH"
)

$ErrorActionPreference = "Stop"
$AckValue = "OPENMITRASTAR_REALTEK_RXGUARD_RAM_ONLY"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$ExecTool = Join-Path $PSScriptRoot "ramssh_exec.py"
$UploadTool = Join-Path $PSScriptRoot "ramssh_upload.py"
$IsolatedGate = Join-Path $PSScriptRoot "run_openmitrastar_ap_isolated_gate.ps1"
$Bundle = if ([IO.Path]::IsPathRooted($RealtekBundle)) {
    [IO.Path]::GetFullPath($RealtekBundle)
} else {
    [IO.Path]::GetFullPath((Join-Path $Root $RealtekBundle))
}
$AllowedBundleRoot = [IO.Path]::GetFullPath((Join-Path $Root "outputs\kernel-port\realtek-loop"))
$ManifestPath = Join-Path $Bundle "manifest.json"
$Remote = "/tmp/omrtl-rxguard"

if (-not $Bundle.StartsWith($AllowedBundleRoot + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase)) {
    throw "Realtek bundle must remain below $AllowedBundleRoot"
}
foreach ($required in @($ExecTool, $UploadTool, $IsolatedGate, $ManifestPath, $PskFile)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing input: $required" }
}
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
if ($Manifest.classification -ne "RAM-ONLY-NO-FLASH" -or
    [bool]$Manifest.candidate_eligible -or
    [bool]$Manifest.safety.flash_supported -or
    [bool]$Manifest.safety.persistent_writes_supported) {
    throw "Realtek bundle is not RAM-only/fail-closed"
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

foreach ($artifact in $Manifest.artifacts) {
    $path = [IO.Path]::GetFullPath((Join-Path $Bundle ([string]$artifact.path)))
    if (-not $path.StartsWith($Bundle + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)) { throw "Artifact escapes bundle" }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing artifact: $path" }
    if ((Get-Item -LiteralPath $path).Length -ne [int64]$artifact.bytes -or
        (Get-Sha256 $path) -ne [string]$artifact.sha256) {
        throw "Artifact integrity failure: $($artifact.path)"
    }
}

$Plan = [ordered]@{
    schema = "openmitrastar.realtek-warm-rxguard-isolated/v1"
    mode = if ($ExecuteRam) { "EXECUTE_RAM" } else { "DRY_RUN" }
    classification = "RAM-ONLY-NO-FLASH"
    host = $HostAddress
    topology = "isolated"
    bridge_created = $false
    eth0_management_preserved = $true
    modules = @("warm MCU pre-clean", "intb-only RXFOVW recognition", "RX deferred 32x4 with HIMR masked")
    uart = "capture file must acknowledge a ttyS0 marker before module or traffic changes"
    flash_supported = $false
    persistent_writes_supported = $false
}
$Plan | ConvertTo-Json -Depth 5
if (-not $ExecuteRam) {
    Write-Output "OMRTL_RXGUARD_ISOLATED_DRY_RUN_PASS=1"
    exit 0
}
if ($AckRamOnly -cne $AckValue) { throw "Execution requires exact -AckRamOnly $AckValue" }
if (-not $UartLog -or -not (Test-Path -LiteralPath $UartLog -PathType Leaf)) {
    throw "Execution requires -UartLog pointing at the active COM3 capture"
}
$UartLog = [IO.Path]::GetFullPath($UartLog)

function Invoke-Remote([string]$Command, [string]$Label, [int]$Timeout = 40) {
    $saved = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & python $ExecTool $Command --host $HostAddress --timeout $Timeout 2>&1
        $rc = $LASTEXITCODE
    } finally { $ErrorActionPreference = $saved }
    if ($rc -ne 0) { throw "$Label failed (exit $rc): $($output -join ' ')" }
    return @($output)
}

function Upload-Quiet([string]$Source, [string]$Destination, [string]$Mode) {
    $saved = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & python $UploadTool $Source $Destination --host $HostAddress --mode $Mode *> $null
        $rc = $LASTEXITCODE
    } finally { $ErrorActionPreference = $saved }
    if ($rc -ne 0) { throw "Upload failed: $Destination" }
}

# Prove that UART capture is active before touching the loaded radio stack or
# generating traffic. The marker is harmless and contains no secret.
$CaptureToken = "OMRTL_RXDEFER_CAPTURE_ARMED_" + (Get-Date -Format "yyyyMMddHHmmssfff")
Invoke-Remote "printf '$CaptureToken\n' >/dev/ttyS0" "uart-capture-marker" 20 | Out-Null
$CaptureDeadline = (Get-Date).AddSeconds(12)
$CaptureSeen = $false
while ((Get-Date) -lt $CaptureDeadline) {
    if ((Get-Content -LiteralPath $UartLog -Raw -ErrorAction SilentlyContinue) -match [regex]::Escape($CaptureToken)) {
        $CaptureSeen = $true
        break
    }
    Start-Sleep -Milliseconds 300
}
if (-not $CaptureSeen) { throw "UART capture did not record the pre-traffic marker" }
Write-Output "OMRTL_UART_CAPTURE_GATE_PASS log=$UartLog"

# The diagnostic product image has no PSK and therefore reaches SSH with the
# radio modules loaded but without starting hostapd or creating br0. Remove that
# exact stack before loading the instrumented modules.
$unload = @'
/usr/sbin/om-radio-stop >/dev/null 2>&1 || true
ifconfig wlan0 down >/dev/null 2>&1 || true
for m in rtl8192ee rtl_pci btcoexist rtlwifi mac80211 libarc4 cfg80211 cmac ccm ctr; do
    rmmod "$m" >/dev/null 2>&1 || true
done
test ! -e /sys/class/net/br0
test ! -e /sys/class/ieee80211/phy0
echo OMRTL_OLD_STACK_UNLOADED=1
'@
Invoke-Remote $unload "unload-old-stack" 60 | Write-Output
Invoke-Remote "rm -rf $Remote; mkdir -p $Remote/modules $Remote/firmware/rtlwifi" "prepare-staging" | Out-Null

foreach ($artifact in $Manifest.artifacts) {
    $relative = ([string]$artifact.path).Replace('\', '/')
    $source = Join-Path $Bundle ([string]$artifact.path)
    $destination = "$Remote/$relative"
    $parent = $destination.Substring(0, $destination.LastIndexOf('/'))
    Invoke-Remote "mkdir -p $parent" "mkdir-$relative" | Out-Null
    $mode = if ($relative -eq "ram_insmod") { "0700" } else { "0600" }
    Upload-Quiet $source $destination $mode
}
Upload-Quiet (Join-Path $Bundle "UPLOAD_SHA256SUMS") "$Remote/UPLOAD_SHA256SUMS" "0600"

$load = @"
ln -sf $Remote/ram_insmod $Remote/busybox
cd $Remote && ./busybox sha256sum -c UPLOAD_SHA256SUMS
mkdir -p /lib/firmware/rtlwifi
cp $Remote/firmware/regulatory.db /lib/firmware/regulatory.db
cp $Remote/firmware/rtlwifi/rtl8192eefw.bin /lib/firmware/rtlwifi/rtl8192eefw.bin
for m in ctr.ko ccm.ko cmac.ko cfg80211.ko libarc4.ko mac80211.ko rtlwifi.ko btcoexist.ko rtl_pci.ko; do
    $Remote/busybox insmod $Remote/modules/`$m || exit 31
done
$Remote/busybox insmod $Remote/modules/rtl8192ee.ko msi=0 dma64=0 aspm=0 ips=0 fwlps=0 swenc=1 disable_watchdog=1 debug_level=5 || exit 32
test -e /sys/class/net/wlan0
echo OMRTL_RXGUARD_STACK_LOADED=1
"@
Invoke-Remote $load "load-rxguard-stack" 120 | Write-Output

$gateArgs = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $IsolatedGate,
    "-ExecuteRam", "-AckRamOnly", "OPENMITRASTAR_RAM_ONLY_AP_ISOLATED_GATE",
    "-HostAddress", $HostAddress, "-Ssid", $Ssid, "-PskFile", ([IO.Path]::GetFullPath($PskFile)),
    "-AssociationTimeoutSeconds", "$AssociationTimeoutSeconds",
    "-WatchdogSeconds", "$WatchdogSeconds"
)
if ($AutoDiscoverClient) { $gateArgs += "-AutoDiscoverClient" }
elseif ($ClientMac) { $gateArgs += @("-ClientMac", $ClientMac) }
else { throw "Pass -AutoDiscoverClient or -ClientMac" }

& powershell.exe @gateArgs
if ($LASTEXITCODE -ne 0) { throw "Isolated AP gate failed; inspect the external UART log for OMRTL rx-irq markers" }
Write-Output "OMRTL_RXGUARD_ISOLATED_PASS=1"
