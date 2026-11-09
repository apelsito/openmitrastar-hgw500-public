[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Scope)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'f320_campaign.ps1')
$cases = [Collections.Generic.List[string]]::new()
function Check([bool]$Condition, [string]$Label) {
    if (-not $Condition) { throw "Offline behavior failed: $Label" }
    $cases.Add($Label)
}
function Must-Fail([scriptblock]$Operation, [string]$Label) {
    $failed = $false
    try { & $Operation } catch { $failed = $true }
    Check $failed $Label
}
# Syntax check without invoking any entrypoint. Dot-sourcing above only defines
# functions. All device, SSH and mutation dependencies below are explicit stubs.
foreach ($name in @('f320_campaign.ps1','promote_f320_mtd4.ps1')) {
    $tokens = $null; $parseErrors = $null
    [void][Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $name), [ref]$tokens, [ref]$parseErrors)
    Check ($parseErrors.Count -eq 0) "parse-$name"
}
$fake = 'OFFLINE_F320_' + [Guid]::NewGuid().ToString('N')
function Get-F319SerialDevice {
    param([string]$Port, [string]$ExpectedPnpDeviceId)
    if ($ExpectedPnpDeviceId -cne $fake) { throw 'Real hardware forbidden by test' }
    return [pscustomobject]@{DeviceID=$Port;PNPDeviceID=$fake}
}
$images = [pscustomobject]@{f319=[pscustomobject]@{version='f319-synthetic'};f320=[pscustomobject]@{version='f320-synthetic'}}
$context = [pscustomobject]@{InitialTag='f319';LockDir=(Join-Path $Scope 'synthetic-lock');
    Contract=[pscustomobject]@{pnp=$fake;images=$images};Guard=$null;BindingProof=$null}
# Real Windows mutex, process start identity and open file lease, synthetic PnP.
$guard = Enter-F319HardwareGuard -Port COM3 -ExpectedPnpDeviceId $fake -PhysicalLockDir $context.LockDir -Owner offline-f320 -EvidenceDir $Scope
$context.Guard = $guard
$context.BindingProof = [pscustomobject]@{OwnerPid=$guard.OwnerPid;OwnerStartTicks=$guard.OwnerStartTicks;LeaseToken=$guard.LeaseToken;
    Binding=[pscustomobject]@{NonceObserved=$true;ExpectedVersion='f319-synthetic';RouterHost='192.168.1.90';Port='COM3';PnpDeviceId=$fake}}
try {
    Assert-F320BoundGuard $context; Check $true 'actual-live-lease-accepted'
    $context.BindingProof.Binding.NonceObserved = $false
    Must-Fail { Assert-F320BoundGuard $context } 'missing-board-nonce-rejected'
    $context.BindingProof.Binding.NonceObserved = $true
    $context.BindingProof.Binding.ExpectedVersion = 'lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device'
    Must-Fail { Assert-F320BoundGuard $context } 'old-F314-binding-rejected'
    $context.BindingProof.Binding.ExpectedVersion = 'f319-synthetic'
    $context.BindingProof.OwnerStartTicks++
    Must-Fail { Assert-F320BoundGuard $context } 'reused-PID-rejected'
    $context.BindingProof.OwnerStartTicks--
    $context.BindingProof.LeaseToken = 'f' * 32
    Must-Fail { Assert-F320BoundGuard $context } 'copied-binding-token-rejected'
    $context.BindingProof.LeaseToken = $guard.LeaseToken
    $guard.LeaseStream.Dispose()
    Must-Fail { Assert-F320BoundGuard $context } 'closed-lease-rejected'
} finally { Exit-F319HardwareGuard $guard }

# Exercise the real campaign and real Restore-F320ExactF314 sequencing with
# narrow leaf stubs. They never enumerate a real device or spawn a process.
$script:events = [Collections.Generic.List[string]]::new()
$script:scenario = ''
function Event([string]$Name) { $script:events.Add($Name) }
function Assert-F320Qualified([object]$Context) { Event qualified; if ($script:scenario -eq 'qualification') { throw 'fixture qualification failure' } }
function Assert-F320LocalTftp([object]$Context) { Event local_ip }
function Assert-F320ReadOnlyIdentity([object]$Context, [string]$Tag) {
    Event "ssh-$Tag"
    if ($script:scenario -eq 'identity' -or ($script:scenario -eq 'unresponsive' -and $Tag -eq 'f320')) { throw 'fixture identity failure' }
}
function Enter-F320Guard([object]$Context) {
    Event guard
    if ($script:scenario -eq 'busy') { throw 'fixture busy adapter' }
    return [pscustomobject]@{OwnerPid=$PID;OwnerStartTicks=123L;LeaseToken=('a' * 32)}
}
function Get-F320Binding([object]$Context, [string]$Tag) {
    Event "nonce-$Tag"
    if ($script:scenario -eq 'wrong_board') { throw 'fixture no nonce' }
    return [pscustomobject]@{NonceObserved=$true;ExpectedVersion=$Tag}
}
function Assert-F320BoundGuard([object]$Context) {
    Event bound_guard
    if ($script:scenario -eq 'lost_guard') { throw 'fixture lost lease' }
}
function Invoke-F320Bootbase([object]$Context, [string]$Label) { Assert-F320BoundGuard $Context; Event "reboot-$Label" }
function Invoke-F320Writer([object]$Context, [string]$Target, [string]$Current, [string]$Label) {
    Assert-F320BoundGuard $Context; Event "write-$Current-to-$Target"
    if (($script:scenario -eq 'partial' -and $Target -eq 'f320') -or ($script:scenario -eq 'rollback_partial' -and $Target -eq 'f314')) { throw 'fixture partial write' }
}
function Invoke-F320Platform([object]$Context, [string]$Tag, [string]$Label) {
    Event $Label
    if (($script:scenario -in @('platform','rollback_partial') -and $Label -eq 'postflash-f320') -or
        ($script:scenario -eq 'postprobe' -and $Label -eq 'postprobe-f320')) { throw 'fixture platform failure' }
}
function Invoke-F320Probe([object]$Context) {
    Event probe
    $Context.ProbeAttempted = $true
    if ($script:scenario -eq 'hard_halt') { $Context.RuntimeHardFault = $true; throw 'fixture Machine Check' }
    if ($script:scenario -in @('probe_fail','unresponsive')) { throw 'fixture probe failure' }
}
function Exit-F319HardwareGuard([object]$Guard) { Event release }

function Run-Case([string]$Name, [string]$ExpectedStatus, [string[]]$Forbidden = @(), [string]$Action = 'Promote') {
    $script:scenario = $Name; $script:events.Clear()
    $directory = Join-Path $Scope $Name
    New-Item -ItemType Directory -Path $directory | Out-Null
    $ctx = [pscustomobject]@{Action=$Action;Ack='OPENMITRASTAR_F320_MTD4_66FF3E8F';PowerCycleReady=$true;TftpHost='192.168.1.249';
        Contract=$null;QualificationPath='fixture';RecoveryPath='fixture';Recovery=$null;OutputDir=$directory;LockDir='fixture';
        InitialTag=if ($Action -eq 'Promote') {'f319'} else {'f320'};Guard=$null;BindingProof=$null;
        HardwareActions=$false;FlashAttempted=$false;FlashCompleted=$false;ProbeAttempted=$false;RuntimeHardFault=$false}
    if ($Name -eq 'old_ack') { $ctx.Ack = 'OPENMITRASTAR_F319_MTD4_E33D8511' }
    if ($Name -eq 'no_power') { $ctx.PowerCycleReady = $false }
    $result = Invoke-F320Campaign $ctx
    Check ($result.status -ceq $ExpectedStatus) "$Name-status"
    foreach ($item in $Forbidden) { Check (-not ($script:events -contains $item)) "$Name-forbids-$item" }
    if ($Name -eq 'success') {
        $expected = 'qualified,local_ip,ssh-f319,guard,nonce-f319,bound_guard,bound_guard,reboot-promotion,bound_guard,write-f319-to-f320,postflash-f320,probe,postprobe-f320,release'
        Check (($script:events -join ',') -ceq $expected) 'complete-order-identity-before-UART-and-write'
    }
    if ($Name -in @('platform','probe_fail','postprobe')) {
        Check (@($script:events | Where-Object { $_ -eq 'write-f320-to-f314' }).Count -eq 1) "$Name-exactly-one-rollback"
        Check ($script:events.IndexOf('ssh-f320') -lt $script:events.IndexOf('reboot-rollback')) "$Name-recovery-identity-before-TX"
    }
    Check ($script:events[$script:events.Count - 1] -eq 'release') "$Name-release-last"
}
Run-Case success PASS_F320_SINGLE_CONTROL_READ_UNLOAD
Run-Case old_ack NO_GO @('qualified','guard','probe','reboot-promotion')
Run-Case no_power NO_GO @('qualified','guard','probe','reboot-promotion')
Run-Case qualification NO_GO @('ssh-f319','guard','probe')
Run-Case identity NO_GO @('guard','nonce-f319','reboot-promotion')
Run-Case busy NO_GO @('nonce-f319','reboot-promotion')
Run-Case wrong_board NO_GO @('reboot-promotion','write-f319-to-f320')
Run-Case lost_guard NO_GO @('reboot-promotion','write-f319-to-f320')
Run-Case partial UNPROVEN_WRITE_OR_RECOVERY_NO_RETRY @('reboot-rollback','write-f320-to-f314','probe')
Run-Case platform FAIL_F320_EXACT_F314_RESTORED @('probe')
Run-Case probe_fail FAIL_F320_EXACT_F314_RESTORED
Run-Case postprobe FAIL_F320_EXACT_F314_RESTORED
Run-Case hard_halt MANUAL_HGW_POWER_CYCLE_REQUIRED @('ssh-f320','reboot-rollback','write-f320-to-f314')
Run-Case unresponsive MANUAL_RECOVERY_REQUIRED_NO_RETRY @('reboot-rollback','write-f320-to-f314')
Run-Case rollback_partial MANUAL_RECOVERY_REQUIRED_NO_RETRY @('postrestore-f314')
Run-Case restore_only PASS_EXACT_F314_RESTORED @('probe','write-f319-to-f320') RestoreF314
@{status='PASS';hardware_actions=$false;synthetic_identity=$true;cases=@($cases)} | ConvertTo-Json -Depth 5 -Compress
