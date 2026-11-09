param([Parameter(Mandatory=$true)][string]$OutputDir,[Parameter(Mandatory=$true)][string]$CommandFile,[switch]$Execute)
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
if(-not $Execute){'{"status":"OFFLINE_ONLY","uart_opened":false,"parent_lease_preserved":true}';return}
if($PSVersionTable.PSEdition -cne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5){throw 'WINDOWS_POWERSHELL_51_REQUIRED'}
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$guardScript=Join-Path $PSScriptRoot 'f319_uart_guard.ps1'
if((Get-FileHash -LiteralPath $guardScript -Algorithm SHA256).Hash.ToLowerInvariant() -cne 'c7522ad8787061d82805397a9521a6672a3cfbe497d026462dfb91eb954a3478'){throw 'GUARD_SOURCE_CHANGED'}
. $guardScript
$failedRun='/workspace/OpenMitraStar\f367-campaign\f367r9-campaign-20260922T224919Z-91a7595c'
$failedResult=Join-Path $failedRun 'result.json'
if((Get-FileHash -LiteralPath $failedResult -Algorithm SHA256).Hash.ToLowerInvariant() -cne '2ed7d2c75142a9ca3176302d4cb14c11d52d76dec056d6295a8ce7fd131b38d3'){throw 'R9_RESULT_CHANGED'}
$previous=Get-Content -LiteralPath $failedResult -Raw|ConvertFrom-Json
if($previous.status -cne 'FAILED_RECOVERY_UNPROVEN_NO_RETRY' -or $previous.recovery_error -cne 'uart_window_overflow' -or
   $previous.flash_command_in_flight -isnot [bool] -or $previous.flash_command_in_flight -or
   $previous.containment_confirmed -isnot [bool] -or -not $previous.containment_confirmed -or
   -not $previous.uart.port_closed -or -not $previous.uart.reader_stopped -or -not $previous.children_contained -or
   -not $previous.final_domain_guard -or -not $previous.break_cleanup_verified -or
   $previous.writer.image -cne '6bf5a08edd5b18adf1597efbd5367d5ad439363c7f7a13a035efc615b4cee440' -or
   -not $previous.writer.byte_compare -or @($previous.serial_recovery.PSObject.Properties).Count -ne 0){throw 'R9_OBSERVER_ADMISSION'}
$parentLease=[IO.Path]::GetFullPath((Join-Path $taskRoot 'outputs/locks/f301-physical-radio.lock'))
$ownerPath=Join-Path $parentLease 'owner.json'
if((Get-Item -LiteralPath $parentLease).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'PARENT_LEASE_REPARSE'}
if((Get-Item -LiteralPath $ownerPath).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'OWNER_REPARSE'}
$evidence=[IO.Path]::GetFullPath($OutputDir)
if(-not $evidence.StartsWith('/workspace/OpenMitraStar\f367-recovery\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $evidence)){throw 'NEW_SCOPED_EVIDENCE_REQUIRED'}
[void](New-Item -ItemType Directory -Path $evidence)
$guard=$null; $serial=$null; $parentStream=$null; $closed=$true; $childReleased=$false
$data=[IO.MemoryStream]::new(); $digest=[Security.Cryptography.SHA256]::Create()
$result=@{schema='openmitrastar.f367r9-retained-console-observation/v1';status='FAILED';uart_tx_bytes=0;break_attempted=$false;reboot_requested=$false;flash_writes=$false;bootenv_writes=$false;raw_saved=$false;old_result_sha256='2ed7d2c75142a9ca3176302d4cb14c11d52d76dec056d6295a8ce7fd131b38d3'}
function Assert-OldOwnerStopped($owner){
 if($owner.schema -cne 'openmitrastar.physical-lock/v3' -or $owner.owner -cne 'F367_ACQUISITION_F365_RETURN' -or
    $owner.pid -ne 38908 -or $owner.process_start_ticks -ne 639257141569704476 -or
    $owner.uart_port -cne 'COM3' -or $owner.uart_pnp_device_id -ine 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -or
    [IO.Path]::GetFullPath($owner.evidence_dir) -ine $failedRun){throw 'RETAINED_OWNER_MISMATCH'}
 $oldProcess=Get-Process -Id ([int]$owner.pid) -ErrorAction SilentlyContinue
 if($oldProcess){try{if(-not $oldProcess.HasExited -and $oldProcess.StartTime.ToUniversalTime().Ticks -eq $owner.process_start_ticks){throw 'ORIGINAL_OWNER_STILL_RUNNING'}}finally{$oldProcess.Dispose()}}
}
try {
 # Keep the quarantine file intact and locked against replacement. The child
 # lease uses the same two device mutexes; normal firmware entry remains blocked.
 $parentStream=[IO.File]::Open($ownerPath,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
 $owner=Get-Content -LiteralPath $ownerPath -Raw|ConvertFrom-Json
 Assert-OldOwnerStopped $owner
 $ownerHash=(Get-FileHash -LiteralPath $ownerPath -Algorithm SHA256).Hash.ToLowerInvariant()
 $guard=Enter-F319HardwareGuard -Port COM4 -ExpectedPnpDeviceId 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -PhysicalLockDir (Join-Path $parentLease 'r9-console-observer.lock') -Owner 'R9_RETAINED_CONSOLE_OBSERVER_NO_RESET_NO_FLASH' -EvidenceDir $evidence
 Assert-OldOwnerStopped $owner
 $serial=[IO.Ports.SerialPort]::new('COM4',115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
 $serial.Handshake=[IO.Ports.Handshake]::None; $serial.DtrEnable=$false; $serial.RtsEnable=$false
 $serial.ReadTimeout=200; $serial.WriteTimeout=1000
 $command=[IO.File]::ReadAllText($CommandFile).Trim(); if($command -match '[\r\n]'){throw 'ONE_COMMAND_LINE_REQUIRED'}; $commandSent=$false; $serial.Open(); $closed=$false; $timer=[Diagnostics.Stopwatch]::StartNew(); $buffer=New-Object byte[] 4096; $probed=$false
 while($timer.Elapsed.TotalSeconds -lt 15){
  if(-not $probed -and $timer.Elapsed.TotalSeconds -ge 3){
   $live=[Text.Encoding]::ASCII.GetString($data.ToArray())
   if($live -notmatch 'qtn-topaz-emac-f352' -or $live -match 'Quantenna U-Boot|Bootbase Version|topaz>|ZHAL>'){throw 'CURRENT_LINUX_CONSOLE_REQUIRED'}
   $result.break_attempted=$true; $result.break_cleared=$false
   try{$serial.BreakState=$true;Start-Sleep -Milliseconds 600}finally{$serial.BreakState=$false;$result.break_cleared=$true}
   Start-Sleep -Milliseconds 150
   $serial.Write('t');$result.uart_tx_bytes=1;$result.sysrq_command='t';$probed=$true
  }
  $available=$serial.BytesToRead
  if($available -gt 0){$count=$serial.Read($buffer,0,[Math]::Min(4096,$available));if($count -gt 0){[void]$digest.TransformBlock($buffer,0,$count,$buffer,0);$data.Write($buffer,0,$count)}}else{Start-Sleep -Milliseconds 50}
  if($data.Length -gt 1048576){throw 'RX_OBSERVATION_LIMIT'}
 }
 [void]$digest.TransformFinalBlock((New-Object byte[] 0),0,0)
 $text=[Text.Encoding]::ASCII.GetString($data.ToArray())
 $safeLines=@($text -split '[\r\n]+' | Where-Object {$_ -and $_ -notmatch '(?i)password|passwd|psk|secret|token|calibration|eapol|key_info|OMEMAC'} | Select-Object -Last 180 | ForEach-Object { [regex]::Replace($_,'(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}','[MAC-REDACTED]') })
 $result.console_tail_redacted=$safeLines; $result.command_sent=$commandSent; $result.command_file_sha256=(Get-FileHash -LiteralPath $CommandFile -Algorithm SHA256).Hash.ToLowerInvariant()
 $result.actual_uart_port='COM4'
 $result.rx_bytes=$data.Length; $result.rx_sha256=([BitConverter]::ToString($digest.Hash)).Replace('-','').ToLowerInvariant()
 $result.linux_version_seen=[regex]::IsMatch($text,'Linux version 5\.10\.260-openmitrastar-radiohw')
 $result.linux_diagnostic_seen=[regex]::IsMatch($text,'(?m)(?:^|[\r\n])(?:OMQDRV|OMEMAC|OMF367)')
 $result.bootloader_marker_seen=[regex]::IsMatch($text,'Boot reached stage 13|Quantenna U-Boot|Bootbase Version|topaz>|ZHAL>')
 $result.bootloader_prompt=[regex]::IsMatch($text,'(?:topaz>|ZHAL>)\s*$')
 $result.shell_prompt_candidate=[regex]::IsMatch($text,'(?m)(?:^|[\r\n])[^\r\n]{0,80}# ?$')
 $result.login_prompt=[regex]::IsMatch($text,'(?im)(?:login|password):\s*$')
 $result.tx_drained=($serial.BytesToWrite -eq 0)
 $result.parent_owner_unchanged=((Get-FileHash -LiteralPath $ownerPath -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $ownerHash)
 $result.status=if($data.Length -eq 0){'NO_UART_RESPONSE_TO_BOUNDED_PROBE'}else{'CONSOLE_OBSERVATION_CAPTURED_NOT_RECOVERY_PROOF'}
} catch {$result.error_type=$_.Exception.GetType().Name; $result.error=$_.Exception.Message}
finally {
 if($serial){try{if($serial.IsOpen){$serial.Close()};$serial.Dispose();$closed=$true}catch{$closed=$false}}
 if($guard -and $closed){try{Exit-F319HardwareGuard -Guard $guard;$childReleased=$true}catch{$result.child_cleanup_failed=$true}}
 if($parentStream){$parentStream.Dispose()}
 $data.Dispose();$digest.Dispose();$result.port_closed=$closed
 $result.child_lease_retained=($null -ne $guard -and -not $childReleased)
 $result.parent_lease_preserved=(Test-Path -LiteralPath $ownerPath)
 $result.recovery_unproven=$true
 [IO.File]::WriteAllText((Join-Path $evidence 'result.json'),($result|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
}
$result|ConvertTo-Json -Depth 5
if($result.status -ceq 'FAILED'){exit 1}
