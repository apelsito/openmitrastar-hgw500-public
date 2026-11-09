[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute, [string]$Ack = '',
    [string]$Port = 'COM3', [string]$ExpectedPnpDeviceId = 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000',
    [string]$RouterHost = '192.168.1.90',
    [string]$ExecutorReview = '', [string]$ExecutorReviewSha256 = '',
    [ValidateRange(600,1800)][int]$FlashTimeoutSeconds = 1800
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'f321_mtd4_runtime.ps1')
$plan = Get-F321Plan -Direction rollback -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256
$plan | ConvertTo-Json -Depth 12
if (-not $Execute) { exit 0 }
Assert-F321ExecutionRequest -Plan $plan -Ack $Ack -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId -RouterHost $RouterHost
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$runDir = Join-Path $script:F321Root ('outputs/recovery/f321-to-f314-' + $stamp)
[void][IO.Directory]::CreateDirectory($runDir)
($plan | ConvertTo-Json -Depth 12) | Set-Content -LiteralPath (Join-Path $runDir 'plan.json') -Encoding UTF8
Invoke-F321PhysicalCycle -Plan $plan -RunDir $runDir -FlashTimeoutSeconds $FlashTimeoutSeconds -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256 | ConvertTo-Json -Depth 12
