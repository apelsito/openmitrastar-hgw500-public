param(
    [string]$HostAddress = '192.168.1.90',
    [string]$Output = '',
    [int]$Seconds = 60,
    [int]$Timeout = 90,
    [switch]$ExecuteCollection,
    [string]$AckReadOnly = ''
)

$ErrorActionPreference = 'Stop'
$Base = Join-Path $PSScriptRoot 'collect_w2_tx12_mgmt_trace.ps1'
if ([string]::IsNullOrWhiteSpace($Output)) {
    $Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    $Output = Join-Path $Root 'outputs\uart-live\w2-tx16-mgmt-trace-latest.json'
}
$Params = @{
    HostAddress = $HostAddress
    Output = $Output
    Seconds = $Seconds
    Timeout = $Timeout
    ExecuteCollection = $ExecuteCollection
    AckReadOnly = $AckReadOnly
    ImageName = 'linux510-w2-2g-parity-tx16-mgmt-reply-split-v1-RAM-TEST-NO-FLASH.bin'
    ImageSha256 = '51d2616cb1a54f337fdefce8540ae4d019c9fdd4fc9c20a464377163a133fa5d'
    ImageBytes = 4333461
    ImageVariant = 'TX16_MGMT_REPLY_SPLIT'
    AckValue = 'OPENMITRASTAR_COLLECT_TX16_MGMT_TRACE_READONLY'
    Label = 'TX16'
    MarkerPrefix = 'OMTX16'
    ReportSchema = 'openmitrastar.w2-tx16-mgmt-trace/v1'
}
& $Base @Params
