param([Parameter(Mandatory=$true)][string]$PlanPath,[Parameter(Mandatory=$true)][string]$PlanSha256,[switch]$Execute)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
if((Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $PlanSha256){throw 'F362_UART_PLAN_HASH'}
$p=Get-Content -LiteralPath $PlanPath -Raw|ConvertFrom-Json
if($p.schema -cne 'openmitrastar.f362-uart-plan/v1' -or $p.status -cne 'PASS_OFFLINE_UART_PROBE' -or $p.flash_writes -or $p.autoboot_intercept){throw 'F362_UART_PLAN_SCOPE'}
foreach($pin in $p.sources.PSObject.Properties){if((Get-FileHash -LiteralPath $pin.Name -Algorithm SHA256).Hash.ToLowerInvariant() -cne $pin.Value){throw 'F362_UART_SOURCE_DRIFT'}}
if(-not $Execute){'{"status":"OFFLINE_ONLY","hardware_actions":false}';return}
if($PSVersionTable.PSEdition -cne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5){throw 'WINDOWS_POWERSHELL_51_REQUIRED'}
. (Join-Path $PSScriptRoot 'f321_mtd4_runtime.ps1')
. (Join-Path $PSScriptRoot 'f336_host_network.ps1')
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$dir=Join-Path $p.evidence_root ('f362-uart-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8));[void](New-Item -ItemType Directory -Path $dir)
$claims=Join-Path $root 'outputs/claims/f362-uart';[void](New-Item -ItemType Directory -Force -Path $claims);$claim=[IO.File]::Open((Join-Path $claims ($PlanSha256+'.claim')),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read);$claim.Dispose()
$guard=$null;$started=$false;$old=$env:OM_F362_UART_CONTEXT
function Get-F362Boot {
 $argsList=@('-i',(Join-Path $env:USERPROFILE '.ssh/id_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o',('UserKnownHostsFile='+$p.known_hosts),'-o','LogLevel=ERROR','root@192.168.1.90','sh','-s')
 $r=Invoke-F319SshScript -SshPath (Join-Path $env:WINDIR 'System32/OpenSSH/ssh.exe') -Arguments $argsList -Script 'cat /proc/sys/kernel/random/boot_id' -TimeoutSeconds 15
 if($r.ExitCode -ne 0 -or $r.Stderr -or $r.Stdout.Trim() -cnotmatch '^[0-9a-f-]{36}$'){throw 'F362_BOOT_ID'};return $r.Stdout.Trim()
}
try{
 Assert-F336HostNetwork -Plan $p
 $guard=Enter-F319HardwareGuard -Port COM3 -ExpectedPnpDeviceId $p.uart_pnp_device_id -PhysicalLockDir $p.physical_lock_dir -Owner 'F362_UART_SYSRQ_PROBE' -EvidenceDir $dir
 $boot=Get-F362Boot;$binding=Assert-F319UartBinding -Port COM3 -ExpectedPnpDeviceId $p.uart_pnp_device_id -RouterHost '192.168.1.90' -KnownHosts $p.known_hosts -ExpectedVersion $p.version -HardwareLease $guard
 if((Get-F362Boot) -cne $boot){throw 'F362_NONCE_BOOT_CHANGED'}
 $now=[DateTimeOffset]::UtcNow;$context=@{schema='openmitrastar.f362-uart-context/v1';purpose='single-serial-sysrq-reboot';uart_port=$guard.Port;uart_pnp_device_id=$guard.PnpDeviceId;binding=$binding;initial_boot_id=$boot;owner_pid=$guard.OwnerPid;owner_start_ticks=$guard.OwnerStartTicks;lease_token=$guard.LeaseToken;physical_lock_dir=$guard.PhysicalLockDir;created_at_utc=$now.ToString('o');expires_at_utc=$now.AddMinutes(30).ToString('o');plan_path=[IO.Path]::GetFullPath($PlanPath);plan_sha256=$PlanSha256}
 $env:OM_F362_UART_CONTEXT=$context|ConvertTo-Json -Depth 10 -Compress
 Write-Output ('F362_UART_DIRECTORY='+$dir);$started=$true
 [void](Invoke-F321Native -Program $p.network.python_executable -Arguments @((Join-Path $PSScriptRoot 'f362_uart_reboot_probe.py'),'--execute','--plan',$PlanPath,'--plan-sha256',$PlanSha256,'--output-dir',$dir) -LogPrefix (Join-Path $dir 'worker') -TimeoutSeconds 600)
}finally{
 $env:OM_F362_UART_CONTEXT=$old
 if($guard){$safe=-not $started;$path=Join-Path $dir 'result.json';if(Test-Path -LiteralPath $path){$r=Get-Content -LiteralPath $path -Raw|ConvertFrom-Json;$safe=$r.containment_confirmed -is [bool] -and $r.containment_confirmed -and $r.retain_lease_required -is [bool] -and -not $r.retain_lease_required};if($script:F321ContainmentFailed){$safe=$false};if($safe){Exit-F319HardwareGuard -Guard $guard}else{Write-Warning 'F362 UART containment/break clear unproven; lock retained.'}}
}
