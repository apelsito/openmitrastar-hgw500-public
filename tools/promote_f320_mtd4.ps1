[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = '',
    [ValidateSet('Promote', 'RestoreF314')][string]$Action = 'Promote',
    [switch]$ManualHgwPowerCycleReady,
    [string]$TftpHost = '',
    [string]$QualificationPath = '',
    [string]$RecoveryRehearsalResultPath = '',
    [string]$OutputDir = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f320_campaign.ps1')
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
# Invalid/missing authority is rejected without even creating a plan directory.
if ($Execute) { Assert-F320ExecutionRequest $Ack ([bool]$ManualHgwPowerCycleReady) $Action }
$contract = Get-F320Contract $QualificationPath
if (-not $OutputDir) { $OutputDir = Join-Path $root ('outputs\flash-watch\f320-campaign-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')) }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $OutputDir -ErrorAction Stop | Out-Null
$plan = [ordered]@{schema='openmitrastar.f320-campaign-plan/v1';action=$Action;execute=[bool]$Execute;target='HGW-500BNA-QCv2 A2 / 192.168.1.90';
    images=$contract.images;required_ack=$contract.required_ack;qualification=$contract.qualification;
    uart='COM3, pinned FTDI plus fresh authenticated console nonce';write_target='mtd4/linux_live';offset='0x7e0000';slot_bytes='0x7a0000';erase_bytes='0x5e0000';
    runtime='one map read and one SPI control read, no writes, no provider, clean unload';
    recovery='exact F314 under original live guard only if F320 responds; hard halt requires physical HGW-only power cycle';
    partial_or_ambiguous_write='STOP, no alternate transport or retry';hardware_actions=$false;release_pass=$false}
Write-F320Json (Join-Path $OutputDir 'plan.json') $plan
if (-not $Execute) { $plan | ConvertTo-Json -Depth 12; exit 0 }
$context = [pscustomobject]@{Action=$Action;Ack=$Ack;PowerCycleReady=[bool]$ManualHgwPowerCycleReady;TftpHost=$TftpHost;
    Contract=$contract;QualificationPath=$QualificationPath;RecoveryPath=$RecoveryRehearsalResultPath;Recovery=$null;
    OutputDir=$OutputDir;LockDir=(Join-Path $root 'outputs\locks\f301-physical-radio.lock');
    InitialTag=if ($Action -eq 'Promote') {'f319'} else {'f320'};Guard=$null;BindingProof=$null;
    HardwareActions=$false;FlashAttempted=$false;FlashCompleted=$false;ProbeAttempted=$false;RuntimeHardFault=$false}
$result = Invoke-F320Campaign $context
$result | ConvertTo-Json -Depth 12
if ($result.status -notin @('PASS_F320_SINGLE_CONTROL_READ_UNLOAD', 'PASS_EXACT_F314_RESTORED')) { exit 1 }
