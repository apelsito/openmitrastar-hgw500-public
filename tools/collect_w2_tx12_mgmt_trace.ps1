param(
    [string]$HostAddress = "192.168.1.90",
    [string]$Output = "",
    [int]$Seconds = 45,
    [int]$Timeout = 75,
    [switch]$ExecuteCollection,
    [string]$AckReadOnly = "",
    [string]$ImageName = "linux510-w2-2g-parity-tx12-mgmt-trace-v1-RAM-TEST-NO-FLASH.bin",
    [string]$ImageSha256 = "5feef36a0aa7c17384a0f1fec05a1940399fb3100978b9faaa526cb46fcb02c9",
    [long]$ImageBytes = 4333757,
    [string]$ImageVariant = "TX12_MGMT_TRACE",
    [string]$AckValue = "OPENMITRASTAR_COLLECT_TX12_MGMT_TRACE_READONLY",
    [string]$Label = "TX12",
    [string]$MarkerPrefix = "OMTX12",
    [string]$ReportSchema = "openmitrastar.w2-tx12-mgmt-trace/v1"
)

$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Collector = Join-Path $PSScriptRoot "collect_w2_tx12_mgmt_trace.py"

if (-not (Test-Path -LiteralPath $Collector -PathType Leaf)) { throw "Missing input: $Collector" }
if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $Root "outputs\uart-live\w2-tx12-mgmt-trace-latest.json"
}
$OutputPath = [IO.Path]::GetFullPath($Output)
$RawOutputPath = [IO.Path]::ChangeExtension($OutputPath, ".raw.txt")

$Plan = [ordered]@{
    schema = "openmitrastar.w2-$($Label.ToLowerInvariant())-mgmt-trace-collection-plan/v1"
    classification = "PLAN-ONLY-BY-DEFAULT-READONLY-SSH-NO-FLASH"
    host = $HostAddress
    output = $OutputPath
    raw_output = $RawOutputPath
    seconds = $Seconds
    image = [ordered]@{
        path = "work/tftp/omvl/$ImageName"
        bytes = $ImageBytes
        sha256 = $ImageSha256
        variant = $ImageVariant
    }
    execution_requested = [bool]$ExecuteCollection
    ack_required = $AckValue
    execution_requires = @(
        "exact acknowledgment $AckValue",
        "router already RAM-booted with exact $Label",
        "operator makes one client join attempt during the capture window",
        "no COM, reboot, module reload, bootenv, MTD or flash"
    )
    uart_opened = $false
    module_reload = $false
    reboot = $false
    bootenv = $false
    mtd = $false
    flash = $false
}
$Plan | ConvertTo-Json -Depth 6
if (-not $ExecuteCollection) {
    Write-Output "$MarkerPrefix`_MGMT_TRACE_COLLECTION_PLAN_PASS=1"
    Write-Output "$MarkerPrefix`_MGMT_TRACE_COLLECTION_LOCKED_UNTIL_ACK=1"
    return
}
if ($AckReadOnly -cne $AckValue) {
    throw "$Label mgmt trace collection requires exact -AckReadOnly $AckValue"
}

New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($OutputPath)) | Out-Null
& python $Collector --host $HostAddress --seconds $Seconds --timeout $Timeout --output $OutputPath --raw-output $RawOutputPath `
    --image-path "work/tftp/omvl/$ImageName" --image-sha256 $ImageSha256 --image-bytes $ImageBytes `
    --image-variant $ImageVariant --report-schema $ReportSchema
if ($LASTEXITCODE -ne 0) { throw "$Label mgmt trace collector failed: $LASTEXITCODE" }
Write-Output "$MarkerPrefix`_MGMT_TRACE_COLLECTED=1 path=$OutputPath"
