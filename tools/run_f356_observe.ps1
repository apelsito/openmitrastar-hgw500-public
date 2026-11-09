[CmdletBinding(PositionalBinding=$false)]
param([Parameter(Mandatory=$true)][string]$PlanPath,[Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$PlanSha256,[switch]$Execute)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
$F356Root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if((Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $PlanSha256){throw 'F356_PLAN_HASH'}
$p=Get-Content -LiteralPath $PlanPath -Raw|ConvertFrom-Json
if($p.schema -cne 'openmitrastar.f356-observe-plan/v1' -or $p.status -cne 'PASS_OFFLINE_OBSERVE_GATE' -or $p.allow_program -isnot [bool] -or $p.allow_program -or ($p.observation_commands -join '|') -cne 'observe'){throw 'F356_PLAN_SCOPE'}
foreach($entry in $p.sources.PSObject.Properties){if((Get-FileHash -LiteralPath $entry.Name -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value){throw 'F356_SOURCE_DRIFT'}}
if(-not $Execute){[pscustomobject]@{status='OFFLINE_ONLY';hardware_actions=$false;observation_commands=@('observe');allow_program=$false}|ConvertTo-Json;return}
if(([IO.DriveInfo]::new('C')).AvailableFreeSpace -le 500MB -or ([IO.DriveInfo]::new('D')).AvailableFreeSpace -le 500MB){throw 'F356_EVIDENCE_DISK_FLOOR'}
$evidenceRoot=[IO.Path]::GetFullPath($p.evidence_root)
if($evidenceRoot -ine '/workspace/OpenMitraStar\f356-evidence' -or -not (Test-Path -LiteralPath $evidenceRoot -PathType Container)){throw 'F356_EVIDENCE_ROOT'}
$directoryCheck=[IO.DirectoryInfo]::new($evidenceRoot)
while($null -ne $directoryCheck){if($directoryCheck.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'F356_EVIDENCE_REPARSE'};$directoryCheck=$directoryCheck.Parent}
. (Join-Path $PSScriptRoot 'f321_mtd4_runtime.ps1')
. (Join-Path $PSScriptRoot 'f336_host_network.ps1')
. (Join-Path $PSScriptRoot 'f325_existing_firewall.ps1')
. (Join-Path $PSScriptRoot 'f356_hardware_context.ps1')
$dir=Join-Path $evidenceRoot ('f356-observe-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8))
[void](New-Item -ItemType Directory -Path $dir)
$claims=Join-Path $F356Root 'outputs/claims/f356';[void](New-Item -ItemType Directory -Force -Path $claims)
$claim=[IO.File]::Open((Join-Path $claims ($PlanSha256+'.json')),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
try{$bytes=[Text.Encoding]::ASCII.GetBytes('{"plan_sha256":"'+$PlanSha256+'","one_shot_consumed":true}');$claim.Write($bytes,0,$bytes.Length);$claim.Flush($true)}finally{$claim.Dispose()}
$guard=$null;$launched=$false;$old=$env:OM_F356_CONTEXT
function Get-F356BootId {
 $sshArguments=@('-i',(Join-Path $env:USERPROFILE '.ssh/id_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o',('UserKnownHostsFile='+$p.known_hosts),'-o','LogLevel=ERROR','root@192.168.1.90','sh','-s')
 $r=Invoke-F319SshScript -SshPath (Join-Path $env:WINDIR 'System32/OpenSSH/ssh.exe') -Arguments $sshArguments -Script 'cat /proc/sys/kernel/random/boot_id' -TimeoutSeconds 15
 if($r.ExitCode -ne 0 -or $r.Stderr -or $r.Stdout.Trim() -cnotmatch '^[0-9a-f-]{36}$'){throw 'F356_BOOT_ID'}
 return $r.Stdout.Trim()
}
try {
 [void](Assert-F325ExistingPermission -Plan $p);Assert-F336HostNetwork -Plan $p -RequireFreeUdp
 $guard=Enter-F319HardwareGuard -Port COM3 -ExpectedPnpDeviceId $p.uart_pnp_device_id -PhysicalLockDir $p.physical_lock_dir -Owner 'F356_RAM_OBSERVE' -EvidenceDir $dir
 $boot=Get-F356BootId
 $binding=Assert-F319UartBinding -Port COM3 -ExpectedPnpDeviceId $p.uart_pnp_device_id -RouterHost '192.168.1.90' -KnownHosts $p.known_hosts -ExpectedVersion $p.images.f340.version -HardwareLease $guard
 if((Get-F356BootId) -cne $boot){throw 'F356_BOOT_CHANGED_DURING_BINDING'}
 $now=[DateTimeOffset]::UtcNow
 $context=[ordered]@{schema='openmitrastar.f356-observe-context/v1';purpose='ram-readonly-identification';baseline_sha256=$p.images.f340.sha256;loader_sha256=$p.loader.sha256;loader_runtime_path=$p.loader.runtime_path;
  kernel_sha256=$p.kernel.sha256;provider_sha256=$p.provider.sha256;supervisor_ram_sha256=$p.supervisor_ram.sha256;cli_sha256=$p.cli.sha256;allow_program=$false;
  initial_boot_id=$boot;created_at_utc=$now.ToString('o');expires_at_utc=$now.AddMinutes(60).ToString('o');owner_pid=$guard.OwnerPid;owner_start_ticks=$guard.OwnerStartTicks;lease_token=$guard.LeaseToken;
  physical_lock_dir=$guard.PhysicalLockDir;uart_port=$guard.Port;uart_pnp_device_id=$guard.PnpDeviceId;binding=$binding;plan_path=[IO.Path]::GetFullPath($PlanPath);plan_sha256=$PlanSha256}
 $env:OM_F356_CONTEXT=$context|ConvertTo-Json -Depth 10 -Compress;[void](Assert-F356Context)
 Write-Output ('F356_RUN_DIRECTORY='+$dir);$launched=$true
 [void](Invoke-F321Native -Program $p.network.python_executable -Arguments @((Join-Path $PSScriptRoot 'f356_observe_executor.py'),'--execute','--plan',$PlanPath,'--plan-sha256',$PlanSha256,'--output-dir',$dir) -LogPrefix (Join-Path $dir 'worker') -TimeoutSeconds 1800)
}finally{
 $env:OM_F356_CONTEXT=$old
 if($guard){
  $safe=-not $launched;$resultPath=Join-Path $dir 'result.json'
  if(Test-Path -LiteralPath $resultPath){$r=Get-Content -LiteralPath $resultPath -Raw|ConvertFrom-Json;$safe=$r.containment_confirmed -is [bool] -and $r.containment_confirmed -and $r.retain_lease_required -is [bool] -and -not $r.retain_lease_required}
  if($script:F321ContainmentFailed){$safe=$false}
  if($safe){Exit-F319HardwareGuard -Guard $guard}else{Write-Warning 'F356 lock barrier retained: containment or inactive-watchdog proof missing. No retry or provider/owner kill.'}
 }
}
