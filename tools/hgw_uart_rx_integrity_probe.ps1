[CmdletBinding(PositionalBinding=$false)]
param([switch]$Execute, [switch]$QuietConsole, [string]$OutputDir='')
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$probeRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
. (Join-Path $PSScriptRoot 'f323_ssh_guard.ps1')

function Get-HgwRxHash {
    param([byte[]]$Bytes)
    $sha=[Security.Cryptography.SHA256]::Create()
    try { return -join ($sha.ComputeHash($Bytes) | ForEach-Object {$_.ToString('x2')}) }
    finally { $sha.Dispose() }
}

function Test-HgwRxFrame {
    param([byte[]]$Bytes,[string]$RunId,[int]$ExpectedBytes=32768)
    if($RunId -cnotmatch '^[A-Z0-9_]{16,80}$' -or $ExpectedBytes -le 0 -or $ExpectedBytes -gt 32768 -or $ExpectedBytes % 2){throw 'Invalid RX fixture bounds'}
    $encoding=[Text.Encoding]::GetEncoding(28591)
    $text=$encoding.GetString($Bytes)
    $begin=$RunId+'_BEGIN:'; $end=':'+$RunId+'_END'
    $begins=[regex]::Matches($text,[regex]::Escape($begin)); $ends=[regex]::Matches($text,[regex]::Escape($end))
    if($begins.Count -ne 1 -or $ends.Count -ne 1){throw 'Missing or duplicate RX frame markers'}
    $start=$begins[0].Index+$begin.Length; $finish=$ends[0].Index
    if($finish -lt $start){throw 'RX markers out of order'}
    $payload=$encoding.GetBytes($text.Substring($start,$finish-$start))
    $expected=[byte[]]::new($ExpectedBytes)
    for($i=0;$i -lt $ExpectedBytes;$i++){ $expected[$i]=if(($i % 2) -eq 0){6}else{67} }
    $unexpected=0; $first=-1
    for($i=0;$i -lt $payload.Length;$i++){
        if($i -ge $ExpectedBytes -or $payload[$i] -ne $expected[$i]){ $unexpected++;if($first -lt 0){$first=$i} }
    }
    $actualHash=Get-HgwRxHash -Bytes $payload; $expectedHash=Get-HgwRxHash -Bytes $expected
    $payloadText=$encoding.GetString($payload)
    $ackCount=0;$cCount=0;$otherCount=0;$printableOther=0
    foreach($value in $payload){
        if($value -eq 6){$ackCount++}elseif($value -eq 67){$cCount++}else{
            $otherCount++;if(($value -ge 32 -and $value -le 126) -or $value -in @(9,10,13)){$printableOther++}
        }
    }
    return [pscustomobject]@{frame_complete=$true;expected_bytes=$ExpectedBytes;received_bytes=$payload.Length;
        payload_matches=($payload.Length -eq $ExpectedBytes -and $actualHash -ceq $expectedHash);
        expected_sha256=$expectedHash;received_sha256=$actualHash;unexpected_bytes=$unexpected;first_mismatch_offset=$first;
        ignored_prefix_bytes=$begins[0].Index;ignored_suffix_bytes=($text.Length-$finish-$end.Length);
        ack_bytes=$ackCount;crc_request_bytes=$cCount;other_bytes=$otherCount;printable_other_bytes=$printableOther;
        emac_log_markers=([regex]::Matches($payloadText,'OMEMAC poll')).Count}
}

function Get-HgwRxProducerScript {
    param([string]$RunId,[string]$ExpectedVersion,[bool]$Quiet)
    if($RunId -cnotmatch '^[A-Z0-9_]{16,80}$' -or $ExpectedVersion -cne 'lyoko-foundation-6.8.5-f321-classic-ui-f314-device'){throw 'Unexpected RX producer identity'}
    $setup='';$restore=''
    if($Quiet){
        $setup=@'
rx_saved_printk=$(cat /proc/sys/kernel/printk)
set -- $rx_saved_printk
[ "$#" -eq 4 ] || exit 71
for rx_level in "$@"; do case "$rx_level" in ''|*[!0-9]*) exit 72 ;; esac; done
printf 'OMRX_PRINTK_BEFORE=%s %s %s %s\n' "$1" "$2" "$3" "$4"
rx_restore() { printf '%s\n' "$rx_saved_printk" > /proc/sys/kernel/printk; }
trap 'rx_restore' EXIT
trap 'exit 130' HUP INT TERM
if [ "$1" -gt 4 ]; then printf '4 %s %s %s\n' "$2" "$3" "$4" > /proc/sys/kernel/printk; fi
sleep 1
'@
        $restore=@'
rx_restore
rx_final_printk=$(cat /proc/sys/kernel/printk)
set -- $rx_final_printk
[ "$#" -eq 4 ] || exit 73
printf 'OMRX_PRINTK_AFTER=%s %s %s %s\n' "$1" "$2" "$3" "$4"
trap - EXIT HUP INT TERM
'@
    }
    $body=@'
set -eu
grep -qx 'OPENMITRASTAR_PRODUCT_VERSION=__VERSION__' /etc/openmitrastar/release
__SETUP__
printf '%s' '__RUN___BEGIN:' > /dev/console
awk 'BEGIN { for (i=0; i<16384; i++) printf "%cC", 6 }' > /dev/console
printf '%s' ':__RUN___END' > /dev/console
__RESTORE__
printf '%s\n' '__RUN___SENT'
'@
    return $body.Replace('__VERSION__',$ExpectedVersion).Replace('__RUN__',$RunId).Replace('__SETUP__',$setup).Replace('__RESTORE__',$restore)
}

$version='lyoko-foundation-6.8.5-f321-classic-ui-f314-device'
$pnp='FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000'
$knownHosts=Join-Path $env:USERPROFILE '.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f321-f314-device-bound/known_hosts.f321'
if(-not $Execute){
    [pscustomobject]@{mode='dry-run';host='192.168.1.90';expected_version=$version;port='COM3';payload_bytes=32768;
        uart_host_tx=$false;device_action='SSH emits a finite ACK/C pattern to /dev/console';reboot=$false;flash=$false;
        raw_capture_saved=$false;temporary_console_verbosity_reduction=[bool]$QuietConsole;requires='fresh exclusive lease and pinned SSH/UART nonce binding'} | ConvertTo-Json
    exit 0
}
if([string]::IsNullOrWhiteSpace($OutputDir)){throw 'A new output directory is required'}
$output=[IO.Path]::GetFullPath($OutputDir)
$allowedRoot=[IO.Path]::GetFullPath((Join-Path $probeRoot 'outputs'))+[IO.Path]::DirectorySeparatorChar
if(-not $output.StartsWith($allowedRoot,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $output)){throw 'Output must be a new directory under workspace outputs'}
[void][IO.Directory]::CreateDirectory($output)
$runId='OM_RX_'+[Guid]::NewGuid().ToString('N').ToUpperInvariant()
$guard=$null; $serial=$null; $process=$null; $started=$false; $buffer=[IO.MemoryStream]::new()
$stdoutTask=$null;$stderrTask=$null
$serialCloseFailed=$false; $eventRegistered=$false; $rxEventId=$runId+'_ERROR'
$probeSshPath=Join-Path $env:WINDIR 'System32/OpenSSH/ssh.exe'
$sshArgs=@('-i',(Join-Path $env:USERPROFILE '.ssh/id_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
    '-o','StrictHostKeyChecking=yes','-o',('UserKnownHostsFile='+$knownHosts),'-o','ConnectTimeout=6','-o','LogLevel=ERROR','root@192.168.1.90','sh','-s')
$result=[ordered]@{schema='openmitrastar.hgw-linux-uart-rx/v1';status='FAIL';run_id=$runId;host='192.168.1.90';
    expected_version=$version;uart_host_tx=$false;device_console_pattern=$true;reboot=$false;flash=$false;radio_mutation=$false;
    raw_capture_saved=$false;configuration_changed=[bool]$QuietConsole;temporary_console_verbosity_reduction=[bool]$QuietConsole;release_eligible=$false;
    scope='One fixed ACK/C receive window from Linux console to host; not host TX, Bootbase or YMODEM certification'}
$stage='binding'
try {
    $guard=Enter-F319HardwareGuard -Port COM3 -ExpectedPnpDeviceId $pnp -PhysicalLockDir (Join-Path $probeRoot 'outputs/locks/f301-physical-radio.lock') -Owner 'hgw-uart-rx-probe' -EvidenceDir $output
    [void](Assert-F319UartBinding -Port COM3 -ExpectedPnpDeviceId $pnp -RouterHost '192.168.1.90' -KnownHosts $knownHosts -ExpectedVersion $version -HardwareLease $guard)
    $serial=[IO.Ports.SerialPort]::new('COM3',115200,'None',8,'One')
    $serial.Handshake='None';$serial.DtrEnable=$false;$serial.RtsEnable=$false;$serial.ReadTimeout=100
    $serial.ReadBufferSize=65536
    [void](Register-ObjectEvent -InputObject $serial -EventName ErrorReceived -SourceIdentifier $rxEventId)
    $eventRegistered=$true
    $serial.Open(); $serial.DiscardInBuffer()
    if($serial.DtrEnable -or $serial.RtsEnable -or $serial.BreakState){throw 'Unexpected UART control-line state'}
    [void](Assert-F319HardwareLease -PhysicalLockDir $guard.PhysicalLockDir -OwnerPid $guard.OwnerPid -OwnerStartTicks $guard.OwnerStartTicks -LeaseToken $guard.LeaseToken -Port COM3 -ExpectedPnpDeviceId $pnp)
    $stage='receiver_ready'
    $remote=Get-HgwRxProducerScript -RunId $runId -ExpectedVersion $version -Quiet ([bool]$QuietConsole)
    $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$probeSshPath
    $start.Arguments=(($sshArgs | ForEach-Object {ConvertTo-F319NativeArgument $_}) -join ' ')
    $start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.RedirectStandardInput=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    $stage='sender_start'
    $process=[Diagnostics.Process]::new();$process.StartInfo=$start
    $oldEncoding=[Console]::InputEncoding
    try{[Console]::InputEncoding=[Text.UTF8Encoding]::new($false);if(-not $process.Start()){throw 'SSH sender failed to start'};$started=$true}
    finally{[Console]::InputEncoding=$oldEncoding}
    $stdoutTask=$process.StandardOutput.ReadToEndAsync();$stderrTask=$process.StandardError.ReadToEndAsync()
    $scriptBytes=[Text.UTF8Encoding]::new($false).GetBytes($remote.Replace("`r`n","`n")+"`n")
    $probeInputPipe=$process.StandardInput.BaseStream;$probeInputPipe.Write($scriptBytes,0,$scriptBytes.Length);$probeInputPipe.Flush();$probeInputPipe.Close()
    $stage='receive'
    $clock=[Diagnostics.Stopwatch]::StartNew();$chunk=[byte[]]::new(4096);$endMarker=':'+$runId+'_END';$ended=$false
    while($clock.Elapsed.TotalSeconds -lt 45){
        if($serial.BytesToRead -gt 0){
            $count=$serial.Read($chunk,0,[Math]::Min($chunk.Length,$serial.BytesToRead))
            $buffer.Write($chunk,0,$count)
            if($buffer.Length -gt 131072){throw 'RX capture exceeded its fixed memory limit'}
            if([Text.Encoding]::GetEncoding(28591).GetString($buffer.ToArray()).Contains($endMarker)){$ended=$true;break}
        } else {Start-Sleep -Milliseconds 10}
    }
    if(-not $ended){throw 'RX frame did not finish before deadline'}
    $stage='sender_completion'
    if(-not $process.WaitForExit(3000)){throw 'SSH sender completion not proved'}
    if(-not [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($stdoutTask,$stderrTask),3000)){throw 'SSH output completion not proved'}
    $senderOutput=$stdoutTask.GetAwaiter().GetResult().Trim()
    if($process.ExitCode -ne 0 -or $stderrTask.GetAwaiter().GetResult().Length -ne 0){throw 'SSH pattern sender failed its completion contract'}
    if($QuietConsole){
        $before=[regex]::Matches($senderOutput,'(?m)^OMRX_PRINTK_BEFORE=([0-9]+ [0-9]+ [0-9]+ [0-9]+)\r?$')
        $after=[regex]::Matches($senderOutput,'(?m)^OMRX_PRINTK_AFTER=([0-9]+ [0-9]+ [0-9]+ [0-9]+)\r?$')
        if($before.Count -ne 1 -or $after.Count -ne 1 -or $before[0].Groups[1].Value -cne $after[0].Groups[1].Value){throw 'Console verbosity restoration not proved'}
        $result.printk_before=$before[0].Groups[1].Value;$result.printk_after=$after[0].Groups[1].Value
        $result.console_verbosity_restored=$true
        if(($senderOutput -split '\r?\n')[-1] -cne ($runId+'_SENT')){throw 'Pattern completion marker missing'}
    }elseif($senderOutput -cne ($runId+'_SENT')){throw 'Pattern completion marker missing'}
    # The producer has finished, but bytes can still be queued by the driver.
    # Include a bounded quiet tail so a split duplicate END cannot be hidden.
    $stage='drain_tail';$drain=[Diagnostics.Stopwatch]::StartNew();$quiet=[Diagnostics.Stopwatch]::StartNew()
    while($drain.Elapsed.TotalSeconds -lt 3 -and $quiet.Elapsed.TotalMilliseconds -lt 500){
        if($serial.BytesToRead -gt 0){
            $count=$serial.Read($chunk,0,[Math]::Min($chunk.Length,$serial.BytesToRead));$buffer.Write($chunk,0,$count)
            if($buffer.Length -gt 131072){throw 'RX capture exceeded its fixed memory limit'}
            $quiet.Restart()
        }else{Start-Sleep -Milliseconds 10}
    }
    if($quiet.Elapsed.TotalMilliseconds -lt 500){throw 'RX did not become quiet after sender completion'}
    $result.serial_error_events=@(Get-Event -SourceIdentifier $rxEventId -ErrorAction SilentlyContinue).Count
    if($result.serial_error_events -ne 0){throw 'UART driver reported an error during the receive window'}
    $stage='frame_validation'
    $result.frame=Test-HgwRxFrame -Bytes $buffer.ToArray() -RunId $runId
    $result.elapsed_seconds=[Math]::Round($clock.Elapsed.TotalSeconds,3)
    if(-not $result.frame.payload_matches){throw 'RX pattern mismatch'}
    $result.status='PASS_LINUX_UART_RX_WINDOW'
} catch {
    $result.error_type=$_.Exception.GetType().Name
    $result.failed_stage=$stage
    # No exception arguments, SSH output or received bytes enter the record.
    $result.error='RX integrity window did not satisfy its bounded contract'
} finally {
    if($serial){
        try{if($serial.IsOpen){$serial.Close()}}catch{$serialCloseFailed=$true}
        try{$serial.Dispose()}catch{$serialCloseFailed=$true}
    }
    if($eventRegistered){
        Unregister-Event -SourceIdentifier $rxEventId -ErrorAction SilentlyContinue
        Remove-Event -SourceIdentifier $rxEventId -ErrorAction SilentlyContinue
    }
    if($process){
        try{Stop-F323SshProcess -Process $process -Started $started}
        catch{$result.status='FAIL';$result.failed_stage='sender_containment';$result.error='SSH sender exit is unproven; physical lease retained'}
        finally{$process.Dispose()}
    }
    $result.received_total_bytes=$buffer.Length
    $buffer.Dispose()
    $result.serial_close_verified=-not $serialCloseFailed
    if($serialCloseFailed){$result.status='FAIL';$result.failed_stage='serial_close';$result.error='UART closure unproven; physical lease retained'}
    $result.post_ssh_f321=$false
    if(-not $serialCloseFailed -and -not $script:F323SshContainmentFailed){
        try{
            $postScript="grep -qx 'OPENMITRASTAR_PRODUCT_VERSION=$version' /etc/openmitrastar/release && echo OMRX_F321_READY"
            if($QuietConsole){$postScript+="`nprintf 'OMRX_PRINTK_CURRENT='; cat /proc/sys/kernel/printk"}
            $post=Invoke-F319SshScript -SshPath $probeSshPath -Arguments $sshArgs -Script $postScript -TimeoutSeconds 15
            $postLines=@($post.Stdout.Trim() -split '\r?\n')
            $result.post_ssh_f321=($post.ExitCode -eq 0 -and $postLines[0] -ceq 'OMRX_F321_READY')
            if($QuietConsole){
                if(-not $result.Contains('printk_before') -and $stdoutTask -and $stdoutTask.IsCompleted){
                    $saved=[regex]::Match($stdoutTask.GetAwaiter().GetResult(),'(?m)^OMRX_PRINTK_BEFORE=([0-9]+ [0-9]+ [0-9]+ [0-9]+)\r?$')
                    if($saved.Success){$result.printk_before=$saved.Groups[1].Value}
                }
                $current=[regex]::Match($post.Stdout,'(?m)^OMRX_PRINTK_CURRENT=([0-9]+\s+[0-9]+\s+[0-9]+\s+[0-9]+)\r?$')
                $result.console_verbosity_restored=$false
                if($result.Contains('printk_before') -and $current.Success){
                    $normalizedPrintk=($current.Groups[1].Value.Trim() -split '\s+') -join ' '
                    $result.console_verbosity_restored=($normalizedPrintk -ceq $result.printk_before)
                }
                if(-not $result.console_verbosity_restored){$result.status='FAIL';$result.restoration_error='Original console verbosity was not proved restored'}
            }
        }catch{$result.post_ssh_f321=$false}
    }
    if(-not $result.post_ssh_f321){$result.status='FAIL';$result.postcheck_error='F321 SSH postcheck not proved'}
    $result.helper_containment_verified=-not ($script:F323SshContainmentFailed -or $serialCloseFailed)
    $result.lease_released=$false
    if($guard -and $result.helper_containment_verified){
        try{Exit-F319HardwareGuard -Guard $guard;$result.lease_released=$true}
        catch{$result.status='FAIL';$result.failed_stage='lease_release';$result.error='Physical lease release not proved'}
    }
    $result.finished_at_utc=[DateTime]::UtcNow.ToString('o')
    [IO.File]::WriteAllText((Join-Path $output 'result.json'),($result | ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
}
$result | ConvertTo-Json -Depth 8
if($result.status -cne 'PASS_LINUX_UART_RX_WINDOW'){exit 1}
