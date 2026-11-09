param(
    [string]$HostAddress = "192.168.1.90",
    [int]$Seconds = 180,
    [int]$Interval = 2,
    [int]$PreSeconds = 10,
    [int]$PostSeconds = 10,
    [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Monitor = Join-Path $PSScriptRoot "monitor_2g_live_traffic.py"
$Image = Join-Path $Root "work\tftp\omvl\linux510-w2-2g-parity-tx3-v1-RAM-TEST-NO-FLASH.bin"
$ExpectedSha256 = "38930e350c2da27c00d5a3dff693dfab967c8cff1255904ebfc4897314bd203e"
$ExpectedBytes = 4330620

if (-not (Test-Path -LiteralPath $Monitor -PathType Leaf)) { throw "Missing monitor: $Monitor" }
if (-not (Test-Path -LiteralPath $Image -PathType Leaf)) { throw "Missing TX3 image: $Image" }
$ImageItem = Get-Item -LiteralPath $Image
$ImageSha256 = (Get-FileHash -LiteralPath $Image -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ImageItem.Length -ne $ExpectedBytes) { throw "TX3 image size mismatch: $($ImageItem.Length)" }
if ($ImageSha256 -ne $ExpectedSha256) { throw "TX3 image SHA-256 mismatch: $ImageSha256" }

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Evidence = Join-Path $Root "outputs\kernel-port\realtek-loop\w2-tx3-live-gate-$Stamp-RAM-ONLY-NO-FLASH"
$RawLog = Join-Path $Evidence "monitor.log"
$Manifest = [ordered]@{
    schema = "openmitrastar.w2-tx3-live-gate-run/v1"
    classification = "RAM-ONLY-NO-FLASH-READ-ONLY-SSH"
    host = $HostAddress
    image = [ordered]@{
        path = $Image
        bytes = $ImageItem.Length
        sha256 = $ImageSha256
    }
    capture = [ordered]@{
        seconds = $Seconds
        interval = $Interval
        pre_seconds = $PreSeconds
        post_seconds = $PostSeconds
        raw_log = $RawLog
        summary = "$RawLog.json"
    }
    uart_opened = $false
    module_reload = $false
    reboot = $false
    flash = $false
}
$RenderedManifest = $Manifest | ConvertTo-Json -Depth 6
if ($PlanOnly) {
    $RenderedManifest
    Write-Output "OM2G_TX3_GATE_PLAN_PASS=1"
    exit 0
}

New-Item -ItemType Directory -Force -Path $Evidence | Out-Null
$RenderedManifest | Set-Content -LiteralPath (Join-Path $Evidence "run-manifest.json") -Encoding UTF8

Write-Output "OM2G_TX3_GATE_ARMED evidence=$Evidence"
Write-Output "OM2G_TX3_GATE_PHASES before=$PreSeconds during=$($Seconds - $PreSeconds - $PostSeconds) after=$PostSeconds"
& python $Monitor `
    --host $HostAddress `
    --seconds $Seconds `
    --interval $Interval `
    --pre-seconds $PreSeconds `
    --post-seconds $PostSeconds `
    --ctrl auto `
    --output $RawLog
$ExitCode = $LASTEXITCODE
Write-Output "OM2G_TX3_GATE_DONE exit=$ExitCode evidence=$Evidence"
exit $ExitCode
