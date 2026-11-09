[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute, [string]$Ack = '',
    [string]$ServerIp = '192.168.1.49', [int]$InterfaceIndex = 18,
    [string]$Port = 'COM3', [string]$ExpectedPnpDeviceId = 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000',
    [string]$RouterHost = '192.168.1.90', [string]$ExecutorReview = '', [string]$ExecutorReviewSha256 = '',
    [string]$NetworkAuthorization = '', [string]$NetworkAuthorizationSha256 = '',
    [ValidateSet('temporary-scoped-rule','existing-permission')][string]$FirewallMode='temporary-scoped-rule',
    [string]$ExistingPermission='', [string]$ExistingPermissionSha256='',
    [ValidateRange(600,1800)][int]$FlashTimeoutSeconds = 1800
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'f325_ethernet_runtime.ps1')
$plan=Get-F325EthernetPlan -Direction promote -ServerIp $ServerIp -InterfaceIndex $InterfaceIndex `
    -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256 `
    -NetworkAuthorization $NetworkAuthorization -NetworkAuthorizationSha256 $NetworkAuthorizationSha256 `
    -FirewallMode $FirewallMode -ExistingPermission $ExistingPermission -ExistingPermissionSha256 $ExistingPermissionSha256
$plan | ConvertTo-Json -Depth 16
if (-not $Execute) { exit 0 }
Assert-F325EthernetExecutionRequest -Plan $plan -Ack $Ack -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId -RouterHost $RouterHost
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8)
$runDir=Join-Path $script:F325EthernetRoot ('outputs/flash-watch/f325-ethernet-'+$stamp)
if (Test-Path -LiteralPath $runDir) { throw 'Fresh Ethernet evidence directory required' }
[void][IO.Directory]::CreateDirectory($runDir)
Write-F325EthernetJson -Path (Join-Path $runDir 'plan.json') -Value $plan
Invoke-F325EthernetPhysicalCycle -Plan $plan -RunDir $runDir -FlashTimeoutSeconds $FlashTimeoutSeconds `
    -ExecutorReview $ExecutorReview -ExecutorReviewSha256 $ExecutorReviewSha256 -CaptureAndRestore | ConvertTo-Json -Depth 16
