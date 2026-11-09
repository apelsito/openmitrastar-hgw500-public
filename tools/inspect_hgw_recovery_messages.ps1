param([Parameter(Mandatory=$true)][string]$OutputDir,[switch]$Execute)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
if(-not $Execute){'{"status":"OFFLINE_ONLY","uart_opened":false}';return}
if($PSVersionTable.PSEdition -cne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5){throw 'WINDOWS_POWERSHELL_51_REQUIRED'}
. (Join-Path $PSScriptRoot 'f321_mtd4_runtime.ps1')
$workspace=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$evidence=[IO.Path]::GetFullPath($OutputDir)
if(Test-Path -LiteralPath $evidence){throw 'NEW_EVIDENCE_DIRECTORY_REQUIRED'}
[void](New-Item -ItemType Directory -Path $evidence)
$guard=$null;$port=$null;$closed=$true;$result=@{schema='openmitrastar.recovery-uart-messages/v1';status='FAILED';uart_tx_bytes=0;reboot_requested=$false;flash_writes=$false;raw_saved=$false}
$data=[IO.MemoryStream]::new();$digest=[Security.Cryptography.SHA256]::Create()
try {
 $guard=Enter-F319HardwareGuard -Port COM3 -ExpectedPnpDeviceId 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -PhysicalLockDir (Join-Path $workspace 'outputs/locks/f301-physical-radio.lock') -Owner 'HGW_ETHERNET_OUTAGE_RECOVERY_RX' -EvidenceDir $evidence
 $port=[IO.Ports.SerialPort]::new('COM3',115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
 $port.Handshake=[IO.Ports.Handshake]::None;$port.DtrEnable=$false;$port.RtsEnable=$false;$port.ReadTimeout=200
 $port.Open();$closed=$false;$timer=[Diagnostics.Stopwatch]::StartNew();$buffer=New-Object byte[] 4096
 while($timer.Elapsed.TotalSeconds -lt 20){
  $available=$port.BytesToRead
  if($available -gt 0){
   $count=$port.Read($buffer,0,[Math]::Min($buffer.Length,$available))
   if($count -gt 0){[void]$digest.TransformBlock($buffer,0,$count,$buffer,0);$data.Write($buffer,0,$count)}
   if($data.Length -gt 1048576){throw 'RX_OBSERVATION_LIMIT'}
  }else{Start-Sleep -Milliseconds 50}
 }
 [void]$digest.TransformFinalBlock((New-Object byte[] 0),0,0)
 $text=[Text.Encoding]::ASCII.GetString($data.ToArray())
 $result.rx_bytes=$data.Length;$result.sha256=([BitConverter]::ToString($digest.Hash)).Replace('-','').ToLowerInvariant()
 $result.linux_version_lines=[regex]::Matches($text,'Linux version 5\.10\.260-openmitrastar-radiohw').Count
 $result.kernel_timestamped_lines=[regex]::Matches($text,'(?m)^\[\s*\d+\.\d+\]').Count
 $result.bootloader_markers=[regex]::Matches($text,'Boot reached stage 13|U-Boot |Bootbase Version|topaz>').Count
 $result.fatal_markers=[regex]::Matches($text,'Kernel panic|Oops:|\bBUG:|MuC has halted|EV_TLB|EV_ProtV').Count
 $result.oom_markers=[regex]::Matches($text,'Out of memory|oom-kill|Killed process').Count
 $result.thermal_error_markers=[regex]::Matches($text,'(?i)temp[^\r\n]{0,90}(?:-19|-110|fail|error)').Count
 $lines=@()
 foreach($line in ($text -split "[\r\n]+")){
  if($line -notmatch '(?i)temp|error|qdrv|Linux|Kernel|panic|fatal|failed'){continue}
  if($line -match '(?i)password|passwd|psk|ssid|secret|calibr|mtd5|private.?key|wep.?key'){continue}
  $safe=$line -replace '(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}','[MAC-REDACTED]'
  $safe=$safe -replace '(?i)\b[0-9a-f]{12,}\b','[HEX-REDACTED]'
  $safe=$safe -replace '\x1b\[[0-9;]*[A-Za-z]',''
  if($safe.Length -gt 240){$safe=$safe.Substring(0,240)+'[TRUNCATED]'}
  if($safe -notin $lines){$lines+=$safe}
  if($lines.Count -ge 24){break}
 }
 $result.classified_lines=$lines
 $result.status='PASS_RX_OBSERVATION_ONLY'
} catch {$result.error_type=$_.Exception.GetType().Name}
finally {
 if($port){try{if($port.IsOpen){$port.Close()};$port.Dispose();$closed=$true}catch{$closed=$false}}
 $data.Dispose();$digest.Dispose();$result.port_closed=$closed
 if($guard -and $closed){Exit-F319HardwareGuard -Guard $guard}
 $result.retain_lease_required=($null -ne $guard -and -not $closed)
 [IO.File]::WriteAllText((Join-Path $evidence 'result.json'),($result|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
}
$result|ConvertTo-Json -Depth 5
if($result.status -cne 'PASS_RX_OBSERVATION_ONLY'){exit 1}
