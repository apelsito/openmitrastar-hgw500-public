param(
    [Parameter(Mandatory=$true)][string]$ImageName,
    [Parameter(Mandatory=$true)][string]$ExpectedSha256,
    [Parameter(Mandatory=$true)][long]$ExpectedBytes,
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$Variant,
    [string]$HostAddress = "192.168.1.90",
    [int]$Seconds = 600,
    [int]$Interval = 2,
    [int]$PreSeconds = 10,
    [int]$PostSeconds = 20,
    [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$TftpRoot = [IO.Path]::GetFullPath((Join-Path $Root "work\tftp\omvl"))
$Image = [IO.Path]::GetFullPath((Join-Path $TftpRoot $ImageName))
$Monitor = Join-Path $PSScriptRoot "monitor_2g_live_traffic.py"
$Evaluator = Join-Path $PSScriptRoot "evaluate_w2_2g_live_traffic.py"

function Get-Sha256Hex {
    param([Parameter(Mandatory=$true)][string]$LiteralPath)

    $Cmd = Get-Command Get-FileHash -ErrorAction SilentlyContinue
    if ($Cmd) {
        return (Get-FileHash -LiteralPath $LiteralPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }

    $Stream = [System.IO.File]::OpenRead($LiteralPath)
    try {
        $Sha = [System.Security.Cryptography.SHA256]::Create()
        try {
            $Bytes = $Sha.ComputeHash($Stream)
            return (($Bytes | ForEach-Object { $_.ToString("x2") }) -join "")
        } finally {
            $Sha.Dispose()
        }
    } finally {
        $Stream.Dispose()
    }
}

if (-not $Image.StartsWith($TftpRoot + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase)) {
    throw "Image escapes TFTP root: $Image"
}
if ($ImageName -notmatch 'RAM-TEST-NO-FLASH\.bin$') {
    throw "Only explicit RAM-TEST-NO-FLASH images are accepted"
}
if (-not (Test-Path -LiteralPath $Monitor -PathType Leaf)) { throw "Missing monitor: $Monitor" }
if (-not (Test-Path -LiteralPath $Evaluator -PathType Leaf)) { throw "Missing evaluator: $Evaluator" }
if (-not (Test-Path -LiteralPath $Image -PathType Leaf)) { throw "Missing image: $Image" }

$ImageItem = Get-Item -LiteralPath $Image
$ImageSha256 = Get-Sha256Hex -LiteralPath $Image
$ExpectedSha256 = $ExpectedSha256.ToLowerInvariant()
if ($ImageItem.Length -ne $ExpectedBytes) { throw "Image size mismatch: $($ImageItem.Length)" }
if ($ImageSha256 -ne $ExpectedSha256) { throw "Image SHA-256 mismatch: $ImageSha256" }

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Evidence = Join-Path $Root "outputs\kernel-port\realtek-loop\w2-$($Variant.ToLowerInvariant())-live-gate-$Stamp-RAM-ONLY-NO-FLASH"
$RawLog = Join-Path $Evidence "monitor.log"
$Summary = "$RawLog.json"
$GateResult = Join-Path $Evidence "gate-result.json"
$Manifest = [ordered]@{
    schema = "openmitrastar.w2-candidate-live-gate-run/v1"
    classification = "RAM-ONLY-$Variant-NO-FLASH-READ-ONLY-SSH"
    host = $HostAddress
    image = [ordered]@{ path = $Image; bytes = $ImageItem.Length; sha256 = $ImageSha256 }
    capture = [ordered]@{
        seconds = $Seconds; interval = $Interval; pre_seconds = $PreSeconds
        post_seconds = $PostSeconds; raw_log = $RawLog; summary = $Summary
        evaluation = $GateResult
    }
    uart_opened = $false
    module_reload = $false
    reboot = $false
    flash = $false
}
$RenderedManifest = $Manifest | ConvertTo-Json -Depth 6
if ($PlanOnly) {
    $RenderedManifest
    Write-Output "OM2G_CANDIDATE_GATE_PLAN_PASS=1 variant=$Variant"
    exit 0
}

New-Item -ItemType Directory -Force -Path $Evidence | Out-Null
$RenderedManifest | Set-Content -LiteralPath (Join-Path $Evidence "run-manifest.json") -Encoding UTF8
Write-Output "OM2G_CANDIDATE_GATE_ARMED variant=$Variant evidence=$Evidence"
& python $Monitor --host $HostAddress --seconds $Seconds --interval $Interval `
    --pre-seconds $PreSeconds --post-seconds $PostSeconds --ctrl auto --output $RawLog
$MonitorExit = $LASTEXITCODE
$EvalExit = 1
if (Test-Path -LiteralPath $Summary -PathType Leaf) {
    & python $Evaluator $Summary --output $GateResult
    $EvalExit = $LASTEXITCODE
} else {
    Write-Output "OM2G_CANDIDATE_GATE_EVAL_SKIPPED missing_summary=$Summary"
}
Write-Output "OM2G_CANDIDATE_GATE_DONE variant=$Variant monitor_exit=$MonitorExit eval_exit=$EvalExit evidence=$Evidence"
if ($MonitorExit -ne 0) { exit $MonitorExit }
exit $EvalExit
