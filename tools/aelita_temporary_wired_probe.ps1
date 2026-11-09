param([switch]$Execute)
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';Set-StrictMode -Version Latest
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
if(-not $Execute){'{"status":"OFFLINE_ONLY","changes":false}';return}
if($env:COMPUTERNAME -cne 'APELSITO' -or $env:USERNAME -ine 'aelita'){throw 'WRONG_CLIENT'}
$adapter=Get-NetAdapter -InterfaceIndex 6
if($adapter.Name -cne 'Ethernet' -or $adapter.Status -cne 'Up'){throw 'ETHERNET_UNAVAILABLE'}
if([string](Get-NetIPInterface -InterfaceIndex 6 -AddressFamily IPv4).Dhcp -cne 'Disabled'){throw 'DHCP_STATE_CHANGED'}
if(Get-NetIPAddress -InterfaceIndex 6 -IPAddress 192.168.1.63 -ErrorAction SilentlyContinue){throw 'PROBE_ADDRESS_ALREADY_PRESENT'}
$stage=Join-Path $env:TEMP ('openmitrastar-wired-probe-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
[void](New-Item -ItemType Directory -Path $stage)
$task='OpenMitraStar-Wired-Probe-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$state=@{task=$task;guid=[string]$adapter.InterfaceGuid;address='192.168.1.63';interface=6}
[IO.File]::WriteAllText((Join-Path $stage 'state.json'),($state|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
$cleanup=@'
$ErrorActionPreference='Stop';$dir=Split-Path -Parent $PSCommandPath
$s=Get-Content (Join-Path $dir 'state.json') -Raw|ConvertFrom-Json
try{
 if(-not (Test-Path (Join-Path $dir 'keep')) -and [string](Get-NetAdapter -InterfaceIndex 6).InterfaceGuid -ceq $s.guid){
  Get-NetIPAddress -InterfaceIndex 6 -IPAddress $s.address -ErrorAction SilentlyContinue|Where-Object {[string]$_.PrefixOrigin -eq 'Manual'}|Remove-NetIPAddress -Confirm:$false
  [IO.File]::WriteAllText((Join-Path $dir 'removed'),'1')
 }
}finally{Unregister-ScheduledTask -TaskName $s.task -Confirm:$false -ErrorAction SilentlyContinue}
'@
$file=Join-Path $stage 'cleanup.ps1';[IO.File]::WriteAllText($file,$cleanup,[Text.UTF8Encoding]::new($false))
$action=New-ScheduledTaskAction -Execute "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+$file+'"')
$principal=New-ScheduledTaskPrincipal -UserId SYSTEM -LogonType ServiceAccount -RunLevel Highest
[void](Register-ScheduledTask -TaskName $task -Action $action -Principal $principal -Trigger (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2)) -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable))
if(-not (Get-NetFirewallRule -Name OpenMitraStar-AELITA-Wired-SSH -ErrorAction SilentlyContinue)){
 [void](New-NetFirewallRule -Name OpenMitraStar-AELITA-Wired-SSH -DisplayName 'OpenMitraStar wired SSH control' -Direction Inbound -Action Allow -Profile Any -InterfaceAlias Ethernet -Protocol TCP -LocalPort 22 -RemoteAddress 192.168.1.49)
}
[void](New-NetIPAddress -InterfaceIndex 6 -IPAddress 192.168.1.63 -PrefixLength 24 -PolicyStore ActiveStore)
Start-Sleep -Seconds 3
$ip=Get-NetIPAddress -InterfaceIndex 6 -IPAddress 192.168.1.63
[ordered]@{status='PROBE_STAGED';address=$ip.IPAddress;address_state=[string]$ip.AddressState;stage=$stage;cleanup_task=$task;wifi_changed=$false;other_addresses_removed=$false}|ConvertTo-Json -Compress
