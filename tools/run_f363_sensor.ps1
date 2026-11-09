[CmdletBinding(PositionalBinding=$false)]
param([Parameter(Mandatory=$true)][string]$PlanPath,[Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$PlanSha256,[switch]$Execute)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if((Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $PlanSha256){throw 'F363_SENSOR_PLAN_HASH'}
$p=Get-Content -LiteralPath $PlanPath -Raw|ConvertFrom-Json
if($p.schema -cne 'openmitrastar.f363-sensor-plan/v1' -or $p.status -cne 'PASS_OFFLINE_SENSOR_ACTIVATION' -or $p.flash_writes -isnot [bool] -or $p.flash_writes -or $p.autoboot_intercept -or $p.activation_attempts -ne 1 -or $p.sample_pairs -ne 3){throw 'F363_SENSOR_PLAN_SCOPE'}
foreach($pin in $p.sources.PSObject.Properties){if((Get-FileHash -LiteralPath $pin.Name -Algorithm SHA256).Hash.ToLowerInvariant() -cne $pin.Value){throw 'F363_SENSOR_SOURCE_DRIFT'}}
if(-not $Execute){[pscustomobject]@{status='OFFLINE_ONLY';hardware_actions=$false;ram_kernel_boot=$false;tftp_allowed=$false}|ConvertTo-Json;return}
if($PSVersionTable.PSEdition -cne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5){throw 'F363_SENSOR_REQUIRES_WINDOWS_POWERSHELL_51'}
if(([IO.DriveInfo]::new('C')).AvailableFreeSpace -le 500MB -or ([IO.DriveInfo]::new('D')).AvailableFreeSpace -le 500MB){throw 'F363_SENSOR_DISK_ADMISSION_FLOOR'}
if([IO.Path]::GetFullPath($p.evidence_root) -ine '/workspace/OpenMitraStar\f363-temperature-activation' -or -not (Test-Path -LiteralPath $p.evidence_root -PathType Container)){throw 'F363_SENSOR_EVIDENCE_ROOT'}
$check=[IO.DirectoryInfo]::new($p.evidence_root);while($null -ne $check){if($check.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'F363_SENSOR_EVIDENCE_REPARSE'};$check=$check.Parent}
. (Join-Path $PSScriptRoot 'f321_mtd4_runtime.ps1')
. (Join-Path $PSScriptRoot 'f336_host_network.ps1')
. (Join-Path $PSScriptRoot 'f363_sensor_context.ps1')
$dir=Join-Path $p.evidence_root ('f363-sensor-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8));[void](New-Item -ItemType Directory -Path $dir)
$claims=Join-Path $root 'outputs/claims/f363-sensor';[void](New-Item -ItemType Directory -Force -Path $claims)
$claim=[IO.File]::Open((Join-Path $claims ($PlanSha256+'.json')),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
try{$bytes=[Text.Encoding]::ASCII.GetBytes('{"plan_sha256":"'+$PlanSha256+'","consumed":true}');$claim.Write($bytes,0,$bytes.Length);$claim.Flush($true)}finally{$claim.Dispose()}
$guard=$null;$launched=$false;$old=$env:OM_F363_SENSOR_CONTEXT
function Get-F363_SENSORBootId {
 $argv=@('-i',(Join-Path $env:USERPROFILE '.ssh/id_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o',('UserKnownHostsFile='+$p.known_hosts),'-o','LogLevel=ERROR','root@192.168.1.90','sh','-s')
 $r=Invoke-F319SshScript -SshPath (Join-Path $env:WINDIR 'System32/OpenSSH/ssh.exe') -Arguments $argv -Script 'cat /proc/sys/kernel/random/boot_id' -TimeoutSeconds 15
 if($r.ExitCode -ne 0 -or $r.Stderr -or $r.Stdout.Trim() -cnotmatch '^[0-9a-f-]{36}$'){throw 'F363_SENSOR_BOOT_ID'};return $r.Stdout.Trim()
}
try{
 Assert-F336HostNetwork -Plan $p
 $guard=Enter-F319HardwareGuard -Port COM3 -ExpectedPnpDeviceId $p.uart_pnp_device_id -PhysicalLockDir $p.physical_lock_dir -Owner 'F363_SENSOR_LIVE_OBSERVE' -EvidenceDir $dir
 $boot=Get-F363_SENSORBootId;$binding=Assert-F319UartBinding -Port COM3 -ExpectedPnpDeviceId $p.uart_pnp_device_id -RouterHost '192.168.1.90' -KnownHosts $p.known_hosts -ExpectedVersion $p.images.f363.version -HardwareLease $guard
 if((Get-F363_SENSORBootId) -cne $boot){throw 'F363_SENSOR_BOOT_CHANGED_DURING_BINDING'}
 $now=[DateTimeOffset]::UtcNow;$context=@{schema='openmitrastar.f363-sensor-context/v1';purpose='f363-sensor-activation-once';baseline_sha256=$p.images.f363.sha256;sensor_sha256=$p.sensor_module.sha256;supervisor_sha256=$p.supervisor.sha256;flash_writes=$false;initial_boot_id=$boot;created_at_utc=$now.ToString('o');expires_at_utc=$now.AddMinutes(60).ToString('o');owner_pid=$guard.OwnerPid;owner_start_ticks=$guard.OwnerStartTicks;lease_token=$guard.LeaseToken;physical_lock_dir=$guard.PhysicalLockDir;uart_port=$guard.Port;uart_pnp_device_id=$guard.PnpDeviceId;binding=$binding;plan_path=[IO.Path]::GetFullPath($PlanPath);plan_sha256=$PlanSha256}
 $env:OM_F363_SENSOR_CONTEXT=$context|ConvertTo-Json -Depth 10 -Compress;[void](Assert-F363_SENSORContext);Write-Output ('F363_SENSOR_RUN_DIRECTORY='+$dir);$launched=$true
 [void](Invoke-F321Native -Program $p.network.python_executable -Arguments @((Join-Path $PSScriptRoot 'f363_sensor_executor.py'),'--execute','--plan',$PlanPath,'--plan-sha256',$PlanSha256,'--output-dir',$dir) -LogPrefix (Join-Path $dir 'worker') -TimeoutSeconds 1800)
}finally{
 $env:OM_F363_SENSOR_CONTEXT=$old
 if($guard){$safe=-not $launched;$resultPath=Join-Path $dir 'result.json';if(Test-Path -LiteralPath $resultPath){$r=Get-Content -LiteralPath $resultPath -Raw|ConvertFrom-Json;$safe=$r.containment_confirmed -is [bool] -and $r.containment_confirmed -and $r.retain_lease_required -is [bool] -and -not $r.retain_lease_required};if($script:F321ContainmentFailed){$safe=$false};if($safe){Exit-F319HardwareGuard -Guard $guard}else{Write-Warning 'F363_SENSOR lock retained: possible armed owner or unproven containment; no retry or unload.'}}
}
