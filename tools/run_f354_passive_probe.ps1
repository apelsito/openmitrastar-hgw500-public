[CmdletBinding(PositionalBinding=$false)]
param([Parameter(Mandatory=$true)][string]$PlanPath,[Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$PlanSha256,[switch]$Execute)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
$F354Root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if((Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $PlanSha256){throw 'F354_PLAN_HASH'}
$p=Get-Content -LiteralPath $PlanPath -Raw|ConvertFrom-Json
if($p.schema -cne 'openmitrastar.f354-passive-plan/v1' -or $p.status -cne 'PASS_OFFLINE_PASSIVE_GATE' -or $p.flash_writes_allowed -isnot [bool] -or $p.flash_writes_allowed){throw 'F354_PLAN_SCOPE'}
foreach($entry in $p.sources.PSObject.Properties){if((Get-FileHash -LiteralPath $entry.Name -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value){throw 'F354_SOURCE_DRIFT'}}
if(-not $Execute){[pscustomobject]@{status='OFFLINE_ONLY';hardware_actions=$false;planned_probe_reads=2;spi_writes=0}|ConvertTo-Json;return}
if((Get-PSDrive C).Free -le 500MB){throw 'F354_EVIDENCE_DISK_FLOOR'}
. (Join-Path $PSScriptRoot 'f321_mtd4_runtime.ps1')
. (Join-Path $PSScriptRoot 'f336_host_network.ps1')
. (Join-Path $PSScriptRoot 'f354_hardware_context.ps1')
$dir=Join-Path $F354Root ('outputs\handoff-live\f354-passive-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8))
[void](New-Item -ItemType Directory -Path $dir)
$claims=Join-Path $F354Root 'outputs/claims/f354';[void](New-Item -ItemType Directory -Force -Path $claims)
$claim=[IO.File]::Open((Join-Path $claims ($PlanSha256+'.json')),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
try{$bytes=[Text.Encoding]::ASCII.GetBytes('{"plan_sha256":"'+$PlanSha256+'","one_shot_consumed":true}');$claim.Write($bytes,0,$bytes.Length);$claim.Flush($true)}finally{$claim.Dispose()}
$guard=$null;$launched=$false;$old=$env:OM_F354_CONTEXT
function Get-F354BootId {
    $sshArguments=@('-i',(Join-Path $env:USERPROFILE '.ssh/id_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o',('UserKnownHostsFile='+$p.known_hosts),'-o','LogLevel=ERROR','root@192.168.1.90','sh','-s')
    $r=Invoke-F319SshScript -SshPath (Join-Path $env:WINDIR 'System32/OpenSSH/ssh.exe') -Arguments $sshArguments -Script 'cat /proc/sys/kernel/random/boot_id' -TimeoutSeconds 15
    if($r.ExitCode -ne 0 -or $r.Stderr -or $r.Stdout.Trim() -cnotmatch '^[0-9a-f-]{36}$'){throw 'F354_BOOT_ID'}
    return $r.Stdout.Trim()
}
try {
    Assert-F336HostNetwork -Plan $p
    $guard=Enter-F319HardwareGuard -Port COM3 -ExpectedPnpDeviceId $p.uart_pnp_device_id -PhysicalLockDir $p.physical_lock_dir -Owner 'F354_PASSIVE_CONTROL' -EvidenceDir $dir
    $boot=Get-F354BootId
    $binding=Assert-F319UartBinding -Port COM3 -ExpectedPnpDeviceId $p.uart_pnp_device_id -RouterHost '192.168.1.90' -KnownHosts $p.known_hosts -ExpectedVersion $p.images.f340.version -HardwareLease $guard
    if((Get-F354BootId) -cne $boot){throw 'F354_BOOT_CHANGED_DURING_BINDING'}
    $now=[DateTimeOffset]::UtcNow
    $context=[ordered]@{schema='openmitrastar.f354-passive-context/v1';purpose='one-passive-spi-control-read';probe_sha256=$p.probe.sha256;baseline_sha256=$p.images.f340.sha256;loader_sha256=$p.loader.sha256;loader_runtime_path=$p.loader.runtime_path;
      initial_boot_id=$boot;created_at_utc=$now.ToString('o');expires_at_utc=$now.AddMinutes(30).ToString('o');owner_pid=$guard.OwnerPid;owner_start_ticks=$guard.OwnerStartTicks;lease_token=$guard.LeaseToken;
      physical_lock_dir=$guard.PhysicalLockDir;uart_port=$guard.Port;uart_pnp_device_id=$guard.PnpDeviceId;binding=$binding;plan_path=[IO.Path]::GetFullPath($PlanPath);plan_sha256=$PlanSha256}
    $env:OM_F354_CONTEXT=$context|ConvertTo-Json -Depth 10 -Compress;[void](Assert-F354Context)
    Write-Output ('F354_RUN_DIRECTORY='+$dir);$launched=$true
    [void](Invoke-F321Native -Program $p.network.python_executable -Arguments @((Join-Path $PSScriptRoot 'f354_probe_executor.py'),'--execute','--plan',$PlanPath,'--plan-sha256',$PlanSha256,'--output-dir',$dir) -LogPrefix (Join-Path $dir 'worker') -TimeoutSeconds 900)
} finally {
    $env:OM_F354_CONTEXT=$old
    if($guard){
        $safe=-not $launched;$resultPath=Join-Path $dir 'result.json'
        if(Test-Path -LiteralPath $resultPath){$r=Get-Content -LiteralPath $resultPath -Raw|ConvertFrom-Json;$safe=$r.containment_confirmed -is [bool] -and $r.containment_confirmed -and $r.retain_lease_required -is [bool] -and -not $r.retain_lease_required}
        if($script:F321ContainmentFailed){$safe=$false}
        if($safe){Exit-F319HardwareGuard -Guard $guard}else{Write-Warning 'F354 lock directory retained; guardian may still own an armed watchdog. No probe retry or owner kill.'}
    }
}
