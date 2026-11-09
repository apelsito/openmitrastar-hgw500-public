param([switch]$Execute)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
if(-not $Execute){'{"status":"OFFLINE_ONLY","client_changes":false}';return}
if($env:COMPUTERNAME -cne 'APELSITO' -or $env:USERNAME -ine 'aelita'){throw 'WRONG_TEST_CLIENT'}
$principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'CLIENT_ADMIN_REQUIRED'}
$eth=Get-NetAdapter -InterfaceIndex 6;$wifi=Get-NetAdapter -InterfaceIndex 17
if($eth.Name -cne 'Ethernet' -or $eth.Status -cne 'Up' -or $wifi.Name -cne 'Wi-Fi' -or $wifi.Status -cne 'Up'){throw 'ADAPTER_STATE_CHANGED'}
if(-not (Get-NetIPAddress -InterfaceIndex 17 -IPAddress 192.168.1.50 -ErrorAction SilentlyContinue)){throw 'WIFI_CONTROL_ADDRESS_CHANGED'}
$dup=Get-NetIPAddress -InterfaceIndex 6 -IPAddress 192.168.1.36 -ErrorAction SilentlyContinue
if(-not $dup -or [string]$dup.AddressState -cne 'Duplicate'){throw 'DUPLICATE_ADDRESS_NOT_PRESENT'}
$mgr=New-Object -ComObject HNetCfg.HNetShare;$ethConn=$null;$publicCount=0
foreach($conn in $mgr.EnumEveryConnection){$p=$mgr.NetConnectionProps($conn);$cfg=$mgr.INetSharingConfigurationForINetConnection($conn);if($cfg.SharingEnabled -and $cfg.SharingConnectionType -eq 0){$publicCount++};if($p.Name -ceq 'Ethernet'){$ethConn=$conn}}
if($publicCount -ne 0 -or $null -eq $ethConn){throw 'ACTIVE_SHARING_TOPOLOGY_CHANGED'}
$sharing=$mgr.INetSharingConfigurationForINetConnection($ethConn)
if(-not $sharing.SharingEnabled -or $sharing.SharingConnectionType -ne 1){throw 'ETHERNET_SHARING_STATE_CHANGED'}
$stage=Join-Path $env:TEMP ('openmitrastar-wired-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
if(Test-Path -LiteralPath $stage){throw 'NEW_STAGE_REQUIRED'}
[void](New-Item -ItemType Directory -Path $stage)
$taskName='OpenMitraStar-Wired-Rollback-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$ruleName='OpenMitraStar-AELITA-Wired-SSH'
$existingRule=Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if($existingRule){throw 'MANAGED_RULE_ALREADY_EXISTS_REVIEW_REQUIRED'}
$state=@{schema='openmitrastar.aelita-wired-repair/v1';interface_guid=[string]$eth.InterfaceGuid;interface_index=6;interface_name='Ethernet';dhcp=[string](Get-NetIPInterface -InterfaceIndex 6 -AddressFamily IPv4).Dhcp;ips=@(Get-NetIPAddress -InterfaceIndex 6 -AddressFamily IPv4|Select-Object IPAddress,PrefixLength,PrefixOrigin,SkipAsSource);sharing_type=1;task_name=$taskName;rule_name=$ruleName;stage=$stage;wifi_unchanged=$true}
$stateFile=Join-Path $stage 'before.json'
[IO.File]::WriteAllText($stateFile,($state|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
$rollback=@'
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
$stage=Split-Path -Parent $PSCommandPath
$s=Get-Content -LiteralPath (Join-Path $stage 'before.json') -Raw|ConvertFrom-Json
$result=@{status='ROLLBACK_NOT_STARTED'}
try{
 if(Test-Path -LiteralPath (Join-Path $stage 'keep')){$result.status='COMMITTED';return}
 $a=Get-NetAdapter -InterfaceIndex 6
 if([string]$a.InterfaceGuid -cne $s.interface_guid){throw 'ADAPTER_IDENTITY_CHANGED'}
 Set-NetIPInterface -InterfaceIndex 6 -AddressFamily IPv4 -Dhcp $s.dhcp
 Get-NetIPAddress -InterfaceIndex 6 -AddressFamily IPv4 -ErrorAction SilentlyContinue|Where-Object {[string]$_.PrefixOrigin -eq 'Dhcp'}|Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
 foreach($ip in $s.ips){if(-not (Get-NetIPAddress -InterfaceIndex 6 -IPAddress $ip.IPAddress -ErrorAction SilentlyContinue)){[void](New-NetIPAddress -InterfaceIndex 6 -IPAddress $ip.IPAddress -PrefixLength $ip.PrefixLength -SkipAsSource ([bool]$ip.SkipAsSource))}}
 $m=New-Object -ComObject HNetCfg.HNetShare
 foreach($c in $m.EnumEveryConnection){if($m.NetConnectionProps($c).Name -ceq 'Ethernet'){$m.INetSharingConfigurationForINetConnection($c).EnableSharing([int]$s.sharing_type)}}
 Remove-NetFirewallRule -Name $s.rule_name -ErrorAction SilentlyContinue
 $result.status='RESTORED_PREVIOUS_ETHERNET_CONFIGURATION'
}catch{$result.status='ROLLBACK_FAILED';$result.error=$_.Exception.Message}
finally{
 [IO.File]::WriteAllText((Join-Path $stage 'rollback-result.json'),($result|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
 Unregister-ScheduledTask -TaskName $s.task_name -Confirm:$false -ErrorAction SilentlyContinue
}
'@
$rollbackPath=Join-Path $stage 'rollback.ps1';[IO.File]::WriteAllText($rollbackPath,$rollback,[Text.UTF8Encoding]::new($false))
$action=New-ScheduledTaskAction -Execute "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+$rollbackPath+'"')
$trigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(3)
$owner=New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
[void](Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $owner -Settings $settings)
$result=@{status='FAILED';stage=$stage;rollback_task=$taskName;client_changes=$false;wifi_unchanged=$true}
try{
 [void](New-NetFirewallRule -Name $ruleName -DisplayName 'OpenMitraStar wired SSH control' -Direction Inbound -Action Allow -Enabled True -Profile Any -InterfaceAlias 'Ethernet' -Protocol TCP -LocalPort 22 -RemoteAddress 192.168.1.49)
 $result.client_changes=$true
 $sharing.DisableSharing()
 foreach($ip in @('192.168.1.36','192.168.137.1')){Get-NetIPAddress -InterfaceIndex 6 -IPAddress $ip -ErrorAction SilentlyContinue|Where-Object {[string]$_.PrefixOrigin -eq 'Manual'}|Remove-NetIPAddress -Confirm:$false -ErrorAction Stop}
 Set-NetIPInterface -InterfaceIndex 6 -AddressFamily IPv4 -Dhcp Enabled
 $deadline=[DateTime]::UtcNow.AddSeconds(35);$addresses=@()
 do{$addresses=@(Get-NetIPAddress -InterfaceIndex 6 -AddressFamily IPv4 -ErrorAction SilentlyContinue|Where-Object {[string]$_.AddressState -eq 'Preferred' -and [string]$_.PrefixOrigin -eq 'Dhcp'}|Select-Object IPAddress,PrefixLength);if($addresses.Count){break};Start-Sleep -Seconds 1}while([DateTime]::UtcNow -lt $deadline)
 $result.ethernet_addresses=$addresses
 $result.status=if($addresses.Count){'WAITING_WIRED_CONTROL_CONFIRMATION'}else{'DHCP_NOT_READY_ROLLBACK_ARMED'}
}catch{$result.error=$_.Exception.Message}
[IO.File]::WriteAllText((Join-Path $stage 'repair-result.json'),($result|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
$result|ConvertTo-Json -Depth 5 -Compress
