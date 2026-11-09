param(
    [string]$HostAddress = '192.168.1.90',
    [string]$Output = '',
    [int]$Seconds = 45,
    [int]$Timeout = 75,
    [switch]$ExecuteCollection,
    [string]$AckReadOnly = ''
)

$ErrorActionPreference = 'Stop'
$Base = Join-Path $PSScriptRoot 'collect_w2_tx12_mgmt_trace.ps1'
if ([string]::IsNullOrWhiteSpace($Output)) {
    $Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    $Output = Join-Path $Root 'outputs\uart-live\w2-tx13-mgmt-trace-latest.json'
}
$Params = @{
    HostAddress = $HostAddress
    Output = $Output
    Seconds = $Seconds
    Timeout = $Timeout
    ExecuteCollection = $ExecuteCollection
    AckReadOnly = $AckReadOnly
    ImageName = 'linux510-w2-2g-parity-tx13-lossless-mgmt-trace-v1-RAM-TEST-NO-FLASH.bin'
    ImageSha256 = '66f9efe41c08c4fecac2b60521b6ec7d37b1390502862dd8cd6e493b6d8239c3'
    ImageBytes = 4334366
    ImageVariant = 'TX13_LOSSLESS_MGMT_TRACE'
    AckValue = 'OPENMITRASTAR_COLLECT_TX13_MGMT_TRACE_READONLY'
    Label = 'TX13'
    MarkerPrefix = 'OMTX13'
    ReportSchema = 'openmitrastar.w2-tx13-mgmt-trace/v1'
}
& $Base @Params
