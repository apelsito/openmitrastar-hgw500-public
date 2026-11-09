[CmdletBinding()]
param(
 [ValidateSet('Describe','Capture','Probe','Connect','Traffic','Restore')][string]$Action='Describe',
 [string]$ConfigPath=(Join-Path $PSScriptRoot 'config.json'),
 [switch]$Execute
)
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';Set-StrictMode -Version Latest
if(-not $Execute){'{"status":"OFFLINE_F367_CLIENT_PAYLOAD","hardware_actions":false}';return}
$config=Get-Content -LiteralPath $ConfigPath -Raw|ConvertFrom-Json
if($env:COMPUTERNAME -cne 'APELSITO' -or $config.run_id -notmatch '^[0-9a-f]{32}$'){throw 'F367_CLIENT_IDENTITY'}
$stage=Join-Path 'C:\ProgramData\OpenMitraStar\f367-aelita' $config.run_id
$task='OpenMitraStar-F367-Restore-'+$config.run_id
$netsh=Join-Path $env:WINDIR 'System32\netsh.exe'
$curlExe=Join-Path $env:WINDIR 'System32\curl.exe'
. (Join-Path $PSScriptRoot 'reused-wlan-functions.ps1')

function Hash-Text([string]$Text){
 $sha=[Security.Cryptography.SHA256]::Create()
 try{return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
}
function Save-Public([string]$Name,$Value){
 $path=Join-Path $stage $Name;$tmp=$path+'.tmp'
 [IO.File]::WriteAllText($tmp,($Value|ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false));Move-Item -LiteralPath $tmp -Destination $path -Force
}
function Write-Private([string]$Name,$Value){
 Add-Type -AssemblyName System.Security
 $bytes=[Text.Encoding]::UTF8.GetBytes(($Value|ConvertTo-Json -Depth 12 -Compress))
 try{$blob=[Security.Cryptography.ProtectedData]::Protect($bytes,$null,[Security.Cryptography.DataProtectionScope]::LocalMachine);[IO.File]::WriteAllBytes((Join-Path $stage $Name),$blob)}finally{[Array]::Clear($bytes,0,$bytes.Length)}
}
function Read-Private([string]$Name){return (Read-RuntimePsk -LiteralPath (Join-Path $stage $Name))|ConvertFrom-Json}
function Assert-Control([bool]$RequireSsh=$false){
 if($RequireSsh){
  if($env:USERNAME -ine 'aelita'){throw 'F367_CLIENT_ACCOUNT'}
  $parts=@($env:SSH_CONNECTION -split ' ')
  if($parts.Count -ne 4 -or $parts[0] -cne '192.168.1.49' -or $parts[2] -cne '192.168.1.63'){throw 'F367_WIRED_SSH_REQUIRED'}
 }
 $eth=Get-NetAdapter -InterfaceIndex 6;$wifi=Get-NetAdapter -InterfaceIndex 17
 if($eth.Name -cne 'Ethernet' -or $eth.Status -cne 'Up' -or $wifi.Name -cne 'Wi-Fi'){throw 'F367_INTERFACE_BINDING'}
 $address=Get-NetIPAddress -InterfaceIndex 6 -IPAddress '192.168.1.63' -AddressFamily IPv4
 if([string]$address.AddressState -cne 'Preferred' -or [string](Get-NetIPInterface -InterfaceIndex 6 -AddressFamily IPv4).Dhcp -cne 'Disabled'){throw 'F367_CONTROL_ADDRESS'}
 foreach($index in @(6,17)){
  $ipif=Get-NetIPInterface -InterfaceIndex $index -AddressFamily IPv4
  if([string]$ipif.WeakHostSend -cne 'Disabled' -or [string]$ipif.WeakHostReceive -cne 'Disabled'){throw 'F367_STRONG_HOST_REQUIRED'}
 }
}
function Control-Hash {
 $state=[ordered]@{
  adapter=@(Get-NetAdapter -InterfaceIndex 6|Select-Object ifIndex,Name,InterfaceGuid,Status)
  addresses=@(Get-NetIPAddress -InterfaceIndex 6 -AddressFamily IPv4|Sort-Object IPAddress|Select-Object IPAddress,PrefixLength,PrefixOrigin,PolicyStore)
  routes=@(Get-NetRoute -InterfaceIndex 6 -AddressFamily IPv4|Sort-Object DestinationPrefix,NextHop|Select-Object DestinationPrefix,NextHop,RouteMetric,Protocol)
  interface=@(Get-NetIPInterface -InterfaceIndex 6 -AddressFamily IPv4|Select-Object Dhcp,InterfaceMetric,WeakHostSend,WeakHostReceive)
 }
 return Hash-Text ($state|ConvertTo-Json -Depth 8 -Compress)
}
function Wifi-State {
 $raw=(& $netsh wlan show interfaces 'interface=Wi-Fi' 2>$null|Out-String)
 if($LASTEXITCODE -ne 0){throw 'F367_WLAN_QUERY'}
 $profile=[regex]::Match($raw,'(?mi)^\s*(?:Profile|Perfil)\s*:\s*(.+?)\s*$')
 $channel=[regex]::Match($raw,'(?mi)^\s*(?:Channel|Canal)\s*:\s*(\d+)\s*$')
 $ssid=Get-CurrentSsid -InterfaceName 'Wi-Fi';$bssid=Get-CurrentBssid -InterfaceName 'Wi-Fi'
 if(-not $profile.Success -or -not $ssid -or -not $bssid -or -not $channel.Success){throw 'F367_WLAN_INCOMPLETE'}
 return @{profile=$profile.Groups[1].Value.Trim();ssid=$ssid;bssid=$bssid;channel=[int]$channel.Groups[1].Value}
}
function Export-Profile([string]$Profile){
 $dir=Join-Path $stage ('export-'+[Guid]::NewGuid().ToString('N'));[void](New-Item -ItemType Directory -Path $dir)
 try{
  & $netsh wlan export profile "name=$Profile" 'interface=Wi-Fi' "folder=$dir" 1>$null 2>$null
  if($LASTEXITCODE -ne 0){throw 'F367_PROFILE_EXPORT'}
  $files=@(Get-ChildItem -LiteralPath $dir -Filter '*.xml');if($files.Count -ne 1){throw 'F367_PROFILE_EXPORT_COUNT'}
  return [IO.File]::ReadAllText($files[0].FullName)
 }finally{
  foreach($file in @(Get-ChildItem -LiteralPath $dir -File)){Remove-Item -LiteralPath $file.FullName -Force}
  Remove-Item -LiteralPath $dir -Force
 }
}
function Restore-Profile {
 $saved=Read-Private 'state.dpapi';$restore=[ordered]@{profile_restored=$false;profile_unchanged=$false;test_profile_removed=$false;control_unchanged=$false}
 # Restoration must still reconnect Wi-Fi if the independent wire disappears.
 & $netsh wlan show profile "name=$($saved.profile)" 'interface=Wi-Fi' 1>$null 2>$null
 if($LASTEXITCODE -ne 0){
  $xmlPath=Join-Path $stage 'restore.xml'
  try{[IO.File]::WriteAllText($xmlPath,$saved.xml,[Text.UTF8Encoding]::new($false));& $netsh wlan add profile "filename=$xmlPath" 'interface=Wi-Fi' 'user=all' 1>$null 2>$null;if($LASTEXITCODE -ne 0){throw 'F367_PROFILE_REIMPORT'}}finally{Remove-Item -LiteralPath $xmlPath -Force -ErrorAction SilentlyContinue}
 }
 & $netsh wlan connect "name=$($saved.profile)" "ssid=$($saved.ssid)" 'interface=Wi-Fi' 1>$null 2>$null
 if($LASTEXITCODE -ne 0 -or -not (Wait-Ssid -InterfaceName 'Wi-Fi' -Ssid $saved.ssid -Seconds 40)){throw 'F367_PROFILE_RECONNECT'}
 $observed=Wifi-State;$restore.profile_restored=$observed.profile -ceq $saved.profile -and $observed.ssid -ceq $saved.ssid
 $restore.profile_unchanged=(Hash-Text (Export-Profile $saved.profile)) -ceq $saved.profile_hash
 & $netsh wlan delete profile "name=OpenMitraStar-F367-$($config.run_id)" 'interface=Wi-Fi' 1>$null 2>$null
 & $netsh wlan show profile "name=OpenMitraStar-F367-$($config.run_id)" 'interface=Wi-Fi' 1>$null 2>$null
 $restore.test_profile_removed=$LASTEXITCODE -ne 0
 try{$restore.control_unchanged=(Control-Hash) -ceq $saved.control_hash}catch{$restore.control_unchanged=$false}
 Save-Public 'restore.json' $restore
 if(@($restore.Values|Where-Object {$_ -ne $true}).Count){throw 'F367_RESTORE_INCOMPLETE'}
 Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
 foreach($file in @('inputs.dpapi','test.xml','upload.bin')){Remove-Item -LiteralPath (Join-Path $stage $file) -Force -ErrorAction SilentlyContinue}
 return $restore
}
function Bound-Curl([string]$Method,[string]$Url,[string]$Source){
 Assert-Control
 $curlArgs=@('-4','--interface',$Source,'--noproxy','*','--silent','--show-error','--connect-timeout','8','--max-time',[string]$config.traffic.timeout_seconds,'--output','NUL')
 $bytesField='size_download'
 if($Method -ceq 'HEAD'){$curlArgs+='--head'}
 if($Method -ceq 'PUT'){
  $bytesField='size_upload';$path=Join-Path $stage 'upload.bin';$stream=[IO.File]::Open($path,[IO.FileMode]::Create,[IO.FileAccess]::Write,[IO.FileShare]::None)
  try{$stream.SetLength([long]$config.traffic.bytes_each_direction)}finally{$stream.Dispose()}
  $curlArgs+=@('--request','PUT','--upload-file',$path)
 }
 $curlArgs+=@('--write-out',('http=%{http_code};local=%{local_ip};remote=%{remote_ip};bytes=%{'+$bytesField+'}'),$Url)
 $raw=(& $curlExe @curlArgs 2>(Join-Path $stage ('curl-'+$Method+'.stderr'))|Out-String).Trim();$exit=$LASTEXITCODE
 $m=[regex]::Match($raw,'^http=(\d{3});local=([0-9.]+);remote=([0-9.]+);bytes=(\d+)$')
 if(-not $m.Success){throw 'F367_CURL_FORMAT'}
 $row=@{exit_code=$exit;http_code=[int]$m.Groups[1].Value;local_ip=$m.Groups[2].Value;remote_ip=$m.Groups[3].Value;bytes=[long]$m.Groups[4].Value}
 if($exit -ne 0 -or $row.http_code -ne 200 -or $row.local_ip -cne $Source){throw 'F367_CURL_SOURCE_OR_STATUS'}
 return $row
}

if($Action -notin @('Restore','Probe')){
 if(-not $config.image_bound -or -not $config.execution_allowed){throw 'F367_FUTURE_IMAGE_OR_ROOT_DISPATCH_REQUIRED'}
 Assert-Control $true
}
try{
 if($Action -ceq 'Capture'){
  $path=[IO.DirectoryInfo]$stage
  for($parent=$path;$null -ne $parent;$parent=$parent.Parent){if($parent.Exists -and ($parent.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'F367_STAGE_REPARSE'}}
  if(Test-Path -LiteralPath $stage){throw 'F367_STAGE_ALREADY_EXISTS'}
  [void](New-Item -ItemType Directory -Path $stage)
  & icacls.exe $stage '/inheritance:r' '/grant:r' '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' 1>$null 2>$null
  if($LASTEXITCODE -ne 0){throw 'F367_STAGE_ACL'}
  foreach($pair in @(@($PSCommandPath,'f367_aelita_client.ps1'),@($ConfigPath,'config.json'),@((Join-Path $PSScriptRoot 'reused-wlan-functions.ps1'),'reused-wlan-functions.ps1'))){
   $destination=Join-Path $stage $pair[1];Copy-Item -LiteralPath $pair[0] -Destination $destination
   if((Get-FileHash -LiteralPath $pair[0]).Hash -cne (Get-FileHash -LiteralPath $destination).Hash){throw 'F367_STAGED_HASH'}
  }
  $wifi=Wifi-State;$xml=Export-Profile $wifi.profile
  Write-Private 'state.dpapi' @{profile=$wifi.profile;ssid=$wifi.ssid;xml=$xml;profile_hash=(Hash-Text $xml);control_hash=(Control-Hash);run_id=$config.run_id;deadline=[DateTime]::UtcNow.AddSeconds(240).ToString('o')}
  $command="& '"+(Join-Path $stage 'f367_aelita_client.ps1').Replace("'","''")+"' -Execute -Action Probe -ConfigPath '"+(Join-Path $stage 'config.json').Replace("'","''")+"'"
  $encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command));$exe=Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $probe=New-ScheduledTaskAction -Execute $exe -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -EncodedCommand '+$encoded)
  $principal=New-ScheduledTaskPrincipal -UserId SYSTEM -LogonType ServiceAccount -RunLevel Highest
  $trigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(240) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Minutes 10)
  [void](Register-ScheduledTask -TaskName $task -Action $probe -Principal $principal -Trigger $trigger -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable))
  Start-ScheduledTask -TaskName $task
  for($i=0;$i -lt 20 -and -not (Test-Path (Join-Path $stage 'probe.json'));$i++){Start-Sleep -Seconds 1}
  $probeResult=Get-Content -LiteralPath (Join-Path $stage 'probe.json') -Raw|ConvertFrom-Json
  if(-not $probeResult.pass){throw 'F367_SYSTEM_RESTORE_PROBE'}
  $command=$command.Replace('-Action Probe','-Action Restore');$encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
  $restoreAction=New-ScheduledTaskAction -Execute $exe -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -EncodedCommand '+$encoded)
  [void](Set-ScheduledTask -TaskName $task -Action $restoreAction)
  Save-Public 'capture.json' @{run_id=$config.run_id;profile_captured=$true;restore_armed=$true;system_probe=$true;control_verified=$true}
 }elseif($Action -ceq 'Probe'){
  Assert-Control;$saved=Read-Private 'state.dpapi'
  & $netsh wlan show profile "name=$($saved.profile)" 'interface=Wi-Fi' 1>$null 2>$null
  if($LASTEXITCODE -ne 0 -or $saved.run_id -cne $config.run_id){throw 'F367_SYSTEM_PROFILE_UNAVAILABLE'}
  Save-Public 'probe.json' @{pass=$true;run_id=$config.run_id}
 }elseif($Action -ceq 'Connect'){
  $saved=Read-Private 'state.dpapi';if(([DateTime]::Parse($saved.deadline).ToUniversalTime()-[DateTime]::UtcNow).TotalSeconds -lt 150){throw 'F367_RESTORE_DEADLINE'}
  $capture=Get-Content -LiteralPath (Join-Path $stage 'capture.json') -Raw|ConvertFrom-Json
  if(-not $capture.restore_armed -or -not (Get-ScheduledTask -TaskName $task)){throw 'F367_RESTORE_UNARMED'}
  $targetInput=Read-Private 'inputs.dpapi'
  if($targetInput.run_id -cne $config.run_id -or $targetInput.target_bssid_tag -notmatch '^[0-9a-f]{64}$' -or $targetInput.test_ssid -ceq $saved.ssid){throw 'F367_PRIVATE_INPUTS'}
  $profile='OpenMitraStar-F367-'+$config.run_id;$xmlPath=Join-Path $stage 'test.xml'
  try{
   [IO.File]::WriteAllText($xmlPath,(New-Wpa2ProfileXml -Ssid $targetInput.test_ssid -Name $profile -Psk $targetInput.psk),[Text.UTF8Encoding]::new($false))
   & $netsh wlan add profile "filename=$xmlPath" 'interface=Wi-Fi' 'user=all' 1>$null 2>$null
   if($LASTEXITCODE -ne 0){throw 'F367_TEST_PROFILE_ADD'}
  }finally{Remove-Item -LiteralPath $xmlPath -Force -ErrorAction SilentlyContinue;$targetInput.psk=$null}
  Write-Private 'target.dpapi' @{ssid=$targetInput.test_ssid;bssid_tag=$targetInput.target_bssid_tag}
  Remove-Item -LiteralPath (Join-Path $stage 'inputs.dpapi') -Force
  & $netsh wlan connect "name=$profile" "ssid=$($targetInput.test_ssid)" 'interface=Wi-Fi' 1>$null 2>$null
  if($LASTEXITCODE -ne 0 -or -not (Wait-Ssid -InterfaceName 'Wi-Fi' -Ssid $targetInput.test_ssid -Seconds 30)){throw 'F367_TEST_ASSOCIATION'}
  $wifi=Wifi-State;$bssidTag=Hash-Text ($config.run_id+$wifi.bssid.ToLowerInvariant())
  if($bssidTag -cne $targetInput.target_bssid_tag -or $wifi.channel -ne 52){throw 'F367_WRONG_AP'}
  $ips=@(Get-NetIPAddress -InterfaceIndex 17 -AddressFamily IPv4|Where-Object {[string]$_.AddressState -eq 'Preferred' -and $_.IPAddress -like '192.168.1.*'})
  if($ips.Count -ne 1){throw 'F367_WIFI_IPV4'}
  $tag=Hash-Text ($config.run_id+([string](Get-NetAdapter -InterfaceIndex 17).MacAddress).Replace('-',':').ToLowerInvariant())
  Save-Public 'client.json' @{run_id=$config.run_id;associated=$true;bssid_match=$true;channel=52;client_tag=$tag;wifi_ipv4=$ips[0].IPAddress;control_verified=$true;control_interface_index=6;wifi_interface_index=17;strong_host=$true;control_unchanged=((Control-Hash) -ceq $saved.control_hash)}
 }elseif($Action -ceq 'Traffic'){
  $saved=Read-Private 'state.dpapi';$target=Read-Private 'target.dpapi';$wifi=Wifi-State
  if($wifi.ssid -cne $target.ssid -or (Hash-Text ($config.run_id+$wifi.bssid.ToLowerInvariant())) -cne $target.bssid_tag){throw 'F367_TARGET_CHANGED'}
  $client=Get-Content -LiteralPath (Join-Path $stage 'client.json') -Raw|ConvertFrom-Json
  $ip=Get-NetIPAddress -InterfaceIndex 17 -IPAddress $client.wifi_ipv4 -AddressFamily IPv4
  if([string]$ip.AddressState -cne 'Preferred'){throw 'F367_WIFI_SOURCE_CHANGED'}
  foreach($row in @(@('download','GET',$config.traffic.download_url),@('upload','PUT',$config.traffic.upload_url),@('internet','HEAD',$config.traffic.internet_url))){
   $value=Bound-Curl $row[1] $row[2] $client.wifi_ipv4;$client|Add-Member -NotePropertyName $row[0] -NotePropertyValue $value -Force;Save-Public 'client.json' $client
  }
  $client.control_unchanged=(Control-Hash) -ceq $saved.control_hash;Save-Public 'client.json' $client
 }elseif($Action -ceq 'Restore'){
  $restore=Restore-Profile
  if(Test-Path (Join-Path $stage 'client.json')){$client=Get-Content -LiteralPath (Join-Path $stage 'client.json') -Raw|ConvertFrom-Json;$client|Add-Member -NotePropertyName restore -NotePropertyValue $restore -Force;Save-Public 'client.json' $client}
 }
 [ordered]@{phase=$Action;status='PASS';run_id=$config.run_id;secrets_logged=$false;client_macs_logged=$false}|ConvertTo-Json -Compress
}catch{
 $code=if($_.Exception.Message -match '^F367_[A-Z_]+$'){$_.Exception.Message}else{'F367_PHASE_EXCEPTION'}
 if($Action -notin @('Probe','Restore') -and (Test-Path (Join-Path $stage 'state.dpapi'))){try{$null=Restore-Profile}catch{}}
 [ordered]@{phase=$Action;status='FAIL';error=$code;run_id=$config.run_id;secrets_logged=$false;client_macs_logged=$false}|ConvertTo-Json -Compress
 exit 1
}
