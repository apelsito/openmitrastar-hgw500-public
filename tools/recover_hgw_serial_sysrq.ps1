param([Parameter(Mandatory=$true)][string]$OutputDir,[switch]$Execute)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
if(-not $Execute){'{"status":"OFFLINE_ONLY","hardware_actions":false}';return}
if($PSVersionTable.PSEdition -cne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5){throw 'WINDOWS_POWERSHELL_51_REQUIRED'}
. (Join-Path $PSScriptRoot 'f321_mtd4_runtime.ps1')
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$out=[IO.Path]::GetFullPath($OutputDir);if(Test-Path -LiteralPath $out){throw 'NEW_EVIDENCE_REQUIRED'}
[void](New-Item -ItemType Directory -Path $out)
$known=Join-Path $env:USERPROFILE '.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f363r2-f363-temperature-owner-device-bound/known_hosts.f363'
$expected='lyoko-foundation-6.9.11-f363r2-temperature-owner-device'
$guard=$null;$serial=$null;$closed=$true;$cleared=$true;$capture=[IO.MemoryStream]::new()
$result=@{schema='openmitrastar.serial-sysrq-recovery/v1';status='FAILED';flash_writes=$false;bootbase_commands=$false;autoboot_intercept=$false;raw_saved=$false;break_attempted=$false;b_written=$false}
function Read-RecoveryBytes {
 if($serial.BytesToRead -gt 0){$buffer=New-Object byte[] 4096;$n=$serial.Read($buffer,0,[Math]::Min(4096,$serial.BytesToRead));if($n -gt 0){$capture.Write($buffer,0,$n)}}
 if($capture.Length -gt 4194304){throw 'RECOVERY_RX_LIMIT'}
}
function RecoveryText { return [Text.Encoding]::ASCII.GetString($capture.ToArray()) }
try {
 $guard=Enter-F319HardwareGuard -Port COM3 -ExpectedPnpDeviceId 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -PhysicalLockDir (Join-Path $root 'outputs/locks/f301-physical-radio.lock') -Owner 'HGW_ETHERNET_SERIAL_RECOVERY' -EvidenceDir $out
 $serial=[IO.Ports.SerialPort]::new('COM3',115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
 $serial.Handshake=[IO.Ports.Handshake]::None;$serial.DtrEnable=$false;$serial.RtsEnable=$false;$serial.ReadTimeout=200;$serial.WriteTimeout=1000
 $serial.Open();$closed=$false;$deadline=[DateTime]::UtcNow.AddSeconds(20);$linux=$false
 while([DateTime]::UtcNow -lt $deadline){Read-RecoveryBytes;$text=RecoveryText
  if(($text -match 'qtn-topaz-emac-f352 e8000000\.ethernet eth0: OMEMAC poll') -and ($text -match 'qtn-topaz-emac-f352 e8000000\.ethernet eth1: OMEMAC poll')){$linux=$true;$result.fresh_linux_signature='F352 live eth0 and eth1 driver polls';break}
  if($text -match 'Topaz internal temperature unavailable: -19'){$linux=$true;$result.fresh_linux_signature='Topaz internal temperature unavailable: -19';break}
  if($text -match 'Boot reached stage 13|U-Boot |Bootbase Version|topaz>|ZHAL>'){throw 'BOOT_EPOCH_NOT_RUNNING_LINUX'}
  Start-Sleep -Milliseconds 30
 }
 if(-not $linux){throw 'FRESH_KNOWN_LINUX_SIGNATURE_MISSING'}
 if($serial.BytesToWrite -ne 0){throw 'UART_TX_NOT_IDLE'}
 $start=$capture.Length;$clock=[Diagnostics.Stopwatch]::StartNew();$result.break_attempted=$true;$cleared=$false
 try{$serial.BreakState=$true;Start-Sleep -Milliseconds 600}finally{$serial.BreakState=$false;$cleared=$true}
 Start-Sleep -Milliseconds 150;Read-RecoveryBytes
 $recent=(RecoveryText).Substring([int]$start)
 if($clock.Elapsed.TotalSeconds -ge 4 -or $recent -match 'Boot reached stage 13|U-Boot |Bootbase Version|topaz>|ZHAL>'){throw 'SYSRQ_EPOCH_OR_WINDOW_CHANGED'}
 $serial.Write('b');$result.b_written=$true;$result.break_to_b_ms=$clock.ElapsedMilliseconds
 $deadline=[DateTime]::UtcNow.AddSeconds(240);$nextProbe=[DateTime]::UtcNow
 while([DateTime]::UtcNow -lt $deadline){
  Read-RecoveryBytes;$recent=(RecoveryText).Substring([int]$start)
  $result.sysrq_dispatch_seen=($recent -match 'sysrq\s*:\s*Resetting')
  $result.reset_seen=($recent -match 'Boot reached stage 13|Quantenna U-Boot')
  $result.new_kernel_seen=($recent -match 'Linux version 5\.10\.260-openmitrastar-radiohw')
  if($result.new_kernel_seen -and [DateTime]::UtcNow -ge $nextProbe){
   $nextProbe=[DateTime]::UtcNow.AddSeconds(8)
   try {
    $argsList=@('-F','NUL','-T','-b','192.168.1.49','-i',(Join-Path $env:USERPROFILE '.ssh/id_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=4','-o','StrictHostKeyChecking=yes','-o',('UserKnownHostsFile='+$known),'-o','LogLevel=ERROR','root@192.168.1.90','sh','-s')
    $scriptText="printf 'boot_id='; cat /proc/sys/kernel/random/boot_id; printf 'version='; sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release; printf 'ready='; cat /run/openmitrastar/boot-state; printf 'watchdog_control='; cat /sys/class/watchdog/watchdog0/f340_control"
    $r=Invoke-F319SshScript -SshPath (Join-Path $env:WINDIR 'System32/OpenSSH/ssh.exe') -Arguments $argsList -Script $scriptText -TimeoutSeconds 6
    if($r.ExitCode -eq 0 -and -not $r.Stderr){
     $rows=@{};foreach($line in ($r.Stdout -split "`n")){if($line -match '^([^=]+)=(.*)$'){$rows[$Matches[1]]=$Matches[2].Trim()}}
     $result.observed_identity=$rows
     if($rows.version -ceq $expected -and $rows.ready -ceq 'ready' -and $rows.watchdog_control -ceq '00000000' -and $rows.boot_id -cmatch '^[0-9a-f-]{36}$' -and $result.sysrq_dispatch_seen -and $result.reset_seen){$result.identity=$rows;$result.status='PASS_F363R2_RECOVERED_WITH_SERIAL_SYSRQ';break}
    }
   }catch{$result.last_ssh_error_type=$_.Exception.GetType().Name}
  }
  Start-Sleep -Milliseconds 30
 }
 if($result.status -cne 'PASS_F363R2_RECOVERED_WITH_SERIAL_SYSRQ'){throw 'RECOVERY_RETURN_NOT_CONFIRMED'}
}catch{$result.error=$_.Exception.Message}
finally {
 if($serial){
  if(-not $cleared -and $serial.IsOpen){try{$serial.BreakState=$false;$cleared=$true}catch{}}
  try{if($serial.IsOpen){$serial.Close()};$serial.Dispose();$closed=$true}catch{$closed=$false}
 }
 $result.break_cleared=$cleared;$result.port_closed=$closed;$result.rx_bytes=$capture.Length
 $sha=[Security.Cryptography.SHA256]::Create();try{$result.rx_sha256=([BitConverter]::ToString($sha.ComputeHash($capture.ToArray()))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
 $capture.Dispose();$result.retain_lease_required=(-not $closed -or -not $cleared)
 if($guard -and -not $result.retain_lease_required){Exit-F319HardwareGuard -Guard $guard}
 [IO.File]::WriteAllText((Join-Path $out 'result.json'),($result|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
}
$result|ConvertTo-Json -Depth 5
if($result.status -cne 'PASS_F363R2_RECOVERED_WITH_SERIAL_SYSRQ'){exit 1}
