[CmdletBinding(PositionalBinding = $false)]
param([switch]$Execute, [Parameter(Mandatory=$true)][string]$AttemptDir)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $root 'tools/f319_uart_guard.ps1')
. (Join-Path $root 'tools/f321_ssh_guard.ps1')
$attempt = [IO.Path]::GetFullPath($AttemptDir)
$allowedRoot = [IO.Path]::GetFullPath((Join-Path $root 'outputs/flash-watch')) + [IO.Path]::DirectorySeparatorChar
if (-not $attempt.StartsWith($allowedRoot,[StringComparison]::OrdinalIgnoreCase)) { throw 'Attempt must be local F321 evidence' }
$previous = Get-Content -LiteralPath (Join-Path $attempt 'result.json') -Raw | ConvertFrom-Json
if ($previous.schema -cne 'openmitrastar.f321-physical-cycle/v1' -or $previous.status -cne 'STOP_NO_AUTOMATIC_RETRY' -or $previous.candidate_sha256 -cne 'eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18' -or $previous.error -notmatch 'UART/YMODEM candidate load failed') { throw 'Not the identified F321 RAM-load failure' }
if ((Test-Path -LiteralPath (Join-Path $attempt 'writer/bootbase-flash-uart.log')) -or (Test-Path -LiteralPath (Join-Path $attempt 'writer/uart-ymodem-status.json'))) { throw 'Write boundary or RAM-load result is ambiguous' }
if (-not $Execute) { Write-Output 'PREWRITE_RECOVERY_PLAN: cancel RAM reception; verify F314 slot CRC; boot existing slot; no flash or environment write'; exit 0 }
$runDir = Join-Path $root ('outputs/recovery/f321-prewrite-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
[void][IO.Directory]::CreateDirectory($runDir)
$guard = $null; $serial = $null; $log = $null; $script:tail = ''
$result = [ordered]@{schema='openmitrastar.f321-prewrite-boot-recovery/v1';started_at_utc=[DateTime]::UtcNow.ToString('o');status='FAIL';source_attempt=$attempt;flash_written=$false;boot_environment_written=$false;expected_f314_crc32='d6b13baa'}
function Receive([string]$Pattern,[int]$Seconds) {
    $until=[DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $until) {
        $chunk=$serial.ReadExisting()
        if ($chunk) { $log.Write($chunk); $script:tail += $chunk; if ($script:tail.Length -gt 32768) { $script:tail=$script:tail.Substring($script:tail.Length-32768) } }
        if ($script:tail -match $Pattern) { return $script:tail }
        Start-Sleep -Milliseconds 20
    }
    throw 'Recovery UART response timeout'
}
function Command([string]$Value,[int]$Seconds=90) {
    $script:tail=''; $serial.Write($Value+"`r")
    $text=Receive 'topaz>\s*$' $Seconds
    if ($text -match '(?im)(data abort|machine check|unknown command|command not found|\berror\b|ret_size=-)') { throw 'Bootbase rejected recovery read' }
    return $text
}
try {
    $guard=Enter-F319HardwareGuard -Port COM3 -ExpectedPnpDeviceId 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000' -PhysicalLockDir (Join-Path $root 'outputs/locks/f301-physical-radio.lock') -Owner 'f321-prewrite-recovery' -EvidenceDir $runDir
    $serial=[IO.Ports.SerialPort]::new('COM3',115200,'None',8,'One')
    $serial.Handshake='None'; $serial.DtrEnable=$false; $serial.RtsEnable=$false; $serial.ReadTimeout=100; $serial.WriteTimeout=1500
    $log=[IO.StreamWriter]::new((Join-Path $runDir 'uart.log'),$false,[Text.UTF8Encoding]::new($false)); $log.AutoFlush=$true
    $serial.Open()
    # Cancel an incomplete YMODEM receive in RAM, then clear the command line.
    [byte[]]$cancel=@(0x18,0x18,0x18,0x18,0x18)
    $serial.Write($cancel,0,$cancel.Length)
    Start-Sleep -Milliseconds 300
    $serial.Write([string][char]0x15 + "`r")
    [void](Receive 'topaz>\s*$' 30)
    $selector=Command 'printenv bootcmd; printenv bootselect' 30
    if ($selector -notmatch '(?m)^bootcmd=bootselect\r?$' -or $selector -notmatch '(?m)^bootselect=0\r?$') { throw 'Existing boot selector changed' }
    $read=Command 'spi_flash read 0x007e0000 0x86000000 0x007a0000' 180
    if ($read -notmatch 'ret_size=7995392') { throw 'Incomplete F314 slot read' }
    $crc=Command 'crc32 0x86000000 0x007a0000 0x84000000; md.l 0x84000000 1' 90
    if ($crc -notmatch '(?im)^84000000:\s*d6b13baa\b' -and $crc -notmatch '(?im)CRC32.*?(?:==>|=)\s*d6b13baa\b') { throw 'Existing slot is not exact F314' }
    $result.full_slot_crc32_observed='d6b13baa'
    Write-Output 'F321_PREWRITE_F314_SLOT_UNCHANGED=1'
    $script:tail=''; $serial.Write("bootselect`r")
    [void](Receive 'OMSSH_READY port=22' 180)
    $result.status='PASS_F314_SLOT_BOOTED_SSH_MARKER'
    Write-Output 'F314_EXISTING_SLOT_BOOTED=1'
} catch { $result.error=$_.Exception.Message; throw }
finally {
    if ($serial) { if ($serial.IsOpen) { $serial.Close() }; $serial.Dispose() }
    if ($log) { $log.Dispose() }
    $result.finished_at_utc=[DateTime]::UtcNow.ToString('o')
    $result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $runDir 'result.json') -Encoding UTF8
    if ($guard) { Exit-F319HardwareGuard -Guard $guard }
    Write-Output ('F321_RECOVERY_EVIDENCE=' + $runDir)
}
