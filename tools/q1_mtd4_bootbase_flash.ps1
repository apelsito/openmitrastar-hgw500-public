param(
    [switch]$Execute,
    [string]$Ack = "",
    [Parameter(Mandatory=$true)] [string]$Candidate,
    [Parameter(Mandatory=$true)] [string]$ExpectedSha256,
    [Parameter(Mandatory=$true)] [long]$ExpectedBytes,
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [Parameter(Mandatory=$true)] [string]$Transcript,
    [Parameter(Mandatory=$true)] [string]$RollbackSha256,
    [Parameter(Mandatory=$true)] [string]$RollbackCrc32,
    [Parameter(Mandatory=$true)] [string]$CurrentLiveCrc32,
    [Parameter(Mandatory=$true)] [string]$ExpectedCandidateCrc32,
    [Parameter(Mandatory=$true)] [string]$ExpectedFullSlotSha256,
    [Parameter(Mandatory=$true)] [string]$ExpectedFullSlotCrc32,
    [ValidateRange(600,1800)] [int]$TimeoutSeconds = 900,
    [switch]$SkipReboot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$RequiredAck = "OPENMITRASTAR_Q1_MTD4_FLASH_BD473EF7"
$ExpectedCandidate = "bd473ef7f7238a5f9488e4739308615355c7e86526c5c867e16d3a232908c306"
$TargetOffset = 0x007e0000
$TargetBytes = 0x007a0000
$RollbackOffset = 0x00040000
$RollbackBytes = 0x007a0000
$LoadAddress = 0x83000000
$ReadbackAddress = 0x86000000
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Candidate = [IO.Path]::GetFullPath($Candidate)
$Transcript = [IO.Path]::GetFullPath($Transcript)

if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { throw "candidate missing" }
$ObservedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Candidate).Hash.ToLowerInvariant()
$ObservedBytes = (Get-Item -LiteralPath $Candidate).Length
if ($ExpectedSha256 -ne $ExpectedCandidate -or $ObservedHash -ne $ExpectedCandidate) { throw "candidate SHA-256 mismatch" }
if ($ExpectedBytes -ne 3647602 -or $ObservedBytes -ne 3647602) { throw "candidate size mismatch" }
if (-not $Execute) {
    Write-Output "OMQ1_BOOTBASE_FLASH_DRY_RUN_PASS=1 target=mtd4 offset=0x007e0000 size=0x007a0000 rollback=mtd3 flash=0"
    exit 0
}
if ($Ack -ne $RequiredAck) { throw "execute requires exact acknowledgement" }
if ($HostAddress -ne "192.168.1.90" -or $ClientIp -ne "192.168.1.90") { throw "management identity mismatch" }
if ($RollbackSha256 -ne "f1a40a5a87bf4262f8c0a3a39e6041d0f32d06794cf0302b470bfe98a50134b1") { throw "rollback SHA-256 mismatch" }
foreach ($crc in @($RollbackCrc32,$CurrentLiveCrc32,$ExpectedCandidateCrc32,$ExpectedFullSlotCrc32)) {
    if ($crc -notmatch '^[0-9a-f]{8}$') { throw "invalid CRC32 input" }
}
if ($ExpectedFullSlotSha256 -notmatch '^[0-9a-f]{64}$') { throw "invalid full-slot SHA-256" }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Transcript) | Out-Null
$writer = [IO.StreamWriter]::new($Transcript, $false, [Text.UTF8Encoding]::new($false))
$writer.AutoFlush = $true
$serial = [IO.Ports.SerialPort]::new($Port, 115200, 'None', 8, 'One')
$serial.Handshake = 'None'; $serial.DtrEnable = $false; $serial.RtsEnable = $false
$serial.ReadTimeout = 100; $serial.WriteTimeout = 2000
$script:tail = ""

function Read-Uart {
    $chunk = $serial.ReadExisting()
    if ($chunk) {
        $writer.Write($chunk); Write-Host -NoNewline $chunk
        $script:tail += $chunk
        if ($script:tail.Length -gt 16384) { $script:tail = $script:tail.Substring($script:tail.Length - 16384) }
    }
    return $chunk
}
function Wait-Uart([string]$Pattern, [string]$Stage, [int]$Seconds) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        [void](Read-Uart)
        if ($script:tail -match $Pattern) { return $script:tail }
        if ($script:tail -match '(?im)(data abort|machine check|unknown command|usage:|spi_flash[^\r\n]*(fail|error))') {
            throw "Bootbase failure during $Stage"
        }
        Start-Sleep -Milliseconds 10
    }
    throw "UART timeout during $Stage"
}
function Wait-Prompt([string]$Stage, [int]$Seconds = 60) { return Wait-Uart 'topaz>\s*$' $Stage $Seconds }
function Send-Uart([string]$Text) { $serial.Write($Text + "`r") }
function Prompt-Command([string]$Text, [string]$Stage, [int]$Seconds = 120) {
    $script:tail = ""; Send-Uart $Text; return Wait-Prompt $Stage $Seconds
}
function Parse-Crc([string]$Text, [string]$Expected, [string]$Stage) {
    $matches = [regex]::Matches($Text, '(?im)CRC32.*?(?:==>|=)\s*([0-9a-f]{8})')
    if ($matches.Count -lt 1) { throw "CRC32 output missing during $Stage" }
    $actual = $matches[$matches.Count - 1].Groups[1].Value.ToLowerInvariant()
    if ($actual -ne $Expected) { throw "CRC32 mismatch during $Stage expected=$Expected actual=$actual" }
}
function Acquire-Bootbase {
    if ($SkipReboot) {
        $serial.DiscardInBuffer(); $script:tail = ""; $serial.Write("`r")
        [void](Wait-Prompt 'existing Bootbase prompt' 30); return
    }
    $execTool = Join-Path $PSScriptRoot 'ramssh_exec.py'
    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = 'python.exe'; $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
    foreach ($arg in @($execTool, 'sync; (sleep 1; reboot -f) >/dev/null 2>&1 &',
                       '--host', $HostAddress, '--timeout', '10')) { [void]$psi.ArgumentList.Add($arg) }
    $null = [Diagnostics.Process]::Start($psi)
    $deadline = [DateTime]::UtcNow.AddSeconds(120)
    while ([DateTime]::UtcNow -lt $deadline) {
        [void](Read-Uart)
        if ($script:tail -match 'topaz>\s*$') { return }
        if ($script:tail -match 'Hit any key to stop autoboot') { $serial.Write(" "); [void](Wait-Prompt 'autoboot interruption' 45); return }
        if ($script:tail -match 'ZHAL>\s*$') {
            $serial.Write([string][char]0x15); $serial.Write([string][char]0x08); Start-Sleep -Milliseconds 80
            Send-Uart 'ATGU'; [void](Wait-Uart 'Hit any key to exit' 'BootExtension ATGU' 15)
            $serial.Write(" "); $script:tail = ""; [void](Wait-Uart 'Hit any key to stop autoboot' 'post-BootExtension autoboot' 30)
            $serial.Write(" "); [void](Wait-Prompt 'post-BootExtension prompt' 45); return
        }
        Start-Sleep -Milliseconds 10
    }
    throw "unable to acquire Bootbase prompt"
}

try {
    $serial.Open(); Acquire-Bootbase
    [void](Prompt-Command "setenv ipaddr $ClientIp" 'volatile ipaddr')
    [void](Prompt-Command "setenv serverip $ServerIp" 'volatile serverip')
    $envBefore = Prompt-Command 'printenv bootcmd; printenv bootselect' 'prewrite boot selector' 30
    if ($envBefore -notmatch '(?m)^bootcmd=bootselect\r?$' -or $envBefore -notmatch '(?m)^bootselect=0\r?$') {
        throw "prewrite selector differs from documented current-unit bootselect=0"
    }
    $script:tail = ""; Send-Uart ("tftpboot 0x{0:x8} {1}" -f $LoadAddress, [IO.Path]::GetFileName($Candidate))
    [void](Wait-Uart ("Bytes transferred = {0}" -f $ExpectedBytes) 'candidate TFTP transfer' 240)
    [void](Wait-Prompt 'candidate TFTP prompt' 30)
    $iminfo = Prompt-Command ("iminfo 0x{0:x8}" -f $LoadAddress) 'candidate iminfo' 60
    if ($iminfo -notmatch 'Verifying Checksum \.\.\. OK') { throw "Bootbase iminfo rejected candidate" }
    Parse-Crc (Prompt-Command ("crc32 0x{0:x8} 0x{1:x8}" -f $LoadAddress,$ExpectedBytes) 'candidate CRC' 90) $ExpectedCandidateCrc32 'candidate RAM image'

    $rollbackRead = Prompt-Command ("spi_flash read 0x{0:x8} 0x{1:x8} 0x{2:x8}" -f $RollbackOffset,$ReadbackAddress,$RollbackBytes) 'fresh rollback read' 180
    if ($rollbackRead -notmatch ("ret_size={0}" -f $RollbackBytes)) { throw "rollback read size mismatch" }
    Parse-Crc (Prompt-Command ("crc32 0x{0:x8} 0x{1:x8}" -f $ReadbackAddress,$RollbackBytes) 'fresh rollback CRC' 90) $RollbackCrc32 'fresh rollback'
    $liveRead = Prompt-Command ("spi_flash read 0x{0:x8} 0x{1:x8} 0x{2:x8}" -f $TargetOffset,$ReadbackAddress,$TargetBytes) 'fresh current-live read' 180
    if ($liveRead -notmatch ("ret_size={0}" -f $TargetBytes)) { throw "current live read size mismatch" }
    Parse-Crc (Prompt-Command ("crc32 0x{0:x8} 0x{1:x8}" -f $ReadbackAddress,$TargetBytes) 'fresh current-live CRC' 90) $CurrentLiveCrc32 'fresh current live'
    Write-Output "OMQ1_MTD4_PREWRITE_PHYSICAL_RECHECK_PASS=1 rollback_crc=$RollbackCrc32 current_live_crc=$CurrentLiveCrc32"

    [void](Prompt-Command ("spi_flash erase 0x{0:x8} 0x{1:x8}" -f $TargetOffset,$TargetBytes) 'mtd4 erase' 300)
    $write = Prompt-Command ("spi_flash write 0x{0:x8} 0x{1:x8} 0x{2:x8}" -f $TargetOffset,$LoadAddress,$ExpectedBytes) 'mtd4 candidate write' 300
    if ($write -notmatch ("ret_size={0}" -f $ExpectedBytes)) { throw "mtd4 write size mismatch" }
    $readback = Prompt-Command ("spi_flash read 0x{0:x8} 0x{1:x8} 0x{2:x8}" -f $TargetOffset,$ReadbackAddress,$TargetBytes) 'mtd4 full readback' 240
    if ($readback -notmatch ("ret_size={0}" -f $TargetBytes)) { throw "mtd4 readback size mismatch" }
    Parse-Crc (Prompt-Command ("crc32 0x{0:x8} 0x{1:x8}" -f $ReadbackAddress,$TargetBytes) 'mtd4 full readback CRC' 120) $ExpectedFullSlotCrc32 'mtd4 full readback'
    $compare = Prompt-Command ("cmp.b 0x{0:x8} 0x{1:x8} 0x{2:x8}" -f $LoadAddress,$ReadbackAddress,$ExpectedBytes) 'mtd4 candidate-prefix compare' 180
    if ($compare -notmatch 'Total of [0-9]+ (byte|bytes|word|words) were the same') { throw "mtd4 candidate prefix compare failed" }
    $envAfter = Prompt-Command 'printenv bootcmd; printenv bootselect' 'postwrite boot selector' 30
    if ($envAfter -notmatch '(?m)^bootcmd=bootselect\r?$' -or $envAfter -notmatch '(?m)^bootselect=0\r?$') {
        throw "postwrite current-unit selector changed"
    }
    Write-Output "OMQ1_MTD4_BOOTBASE_READBACK_PASS=1 full_slot_crc=$ExpectedFullSlotCrc32 prefix=identical"

    $seed = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'new_ramssh_seed.ps1')
    if ($seed -notmatch '^seed_[0-9a-f]{64}$') { throw "invalid entropy seed" }
    $script:tail = ""; Send-Uart ("bootm 0x{0:x8}" -f $LoadAddress)
    [void](Wait-Uart '(?s)OMPRODUCT_ENTR.{0,4096}OPY_SEED_REQUIRED' 'RAM readback boot entropy prompt' 180)
    Send-Uart $seed
    [void](Wait-Uart 'OMPRODUCT_SERIAL_ENTROPY_OK bits=256' 'RAM readback boot entropy accepted' 30)
    [void](Wait-Uart 'OMPRODUCT_READY state=(ready|degraded)' 'RAM readback boot ready' 120)
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose(); $writer.Dispose()
}

Start-Sleep -Seconds 3
$verify = & python (Join-Path $PSScriptRoot 'verify_ramssh.py') --host $HostAddress --timeout 60 2>&1
if ($LASTEXITCODE -ne 0) { throw "post-write key-only SSH verification failed: $verify" }
$blocks = [Math]::Floor($ExpectedBytes / 4096)
$remainder = $ExpectedBytes % 4096
$remote = @"
set -e
grep -qx 'mtd3: 007a0000 00010000 "linux_safety"' /proc/mtd
grep -qx 'mtd4: 007a0000 00010000 "linux_live"' /proc/mtd
safety=`$(sha256sum /dev/mtdblock3 | awk '{print `$1}')
full=`$(sha256sum /dev/mtdblock4 | awk '{print `$1}')
prefix=`$({ dd if=/dev/mtdblock4 bs=4096 count=$blocks 2>/dev/null; dd if=/dev/mtdblock4 bs=4096 skip=$blocks count=1 2>/dev/null | dd bs=1 count=$remainder 2>/dev/null; } | sha256sum | awk '{print `$1}')
echo OMQ1_READBACK_SAFETY_SHA=`$safety
echo OMQ1_READBACK_FULL_SLOT_SHA=`$full
echo OMQ1_READBACK_PREFIX_SHA=`$prefix
test "`$safety" = '$RollbackSha256'
test "`$full" = '$ExpectedFullSlotSha256'
test "`$prefix" = '$ExpectedSha256'
echo OMQ1_REMOTE_SHA256_READBACK_PASS=1
"@
$remoteOutput = & python (Join-Path $PSScriptRoot 'ramssh_exec.py') $remote --host $HostAddress --timeout 180 2>&1
if ($LASTEXITCODE -ne 0 -or ($remoteOutput -join "`n") -notmatch 'OMQ1_REMOTE_SHA256_READBACK_PASS=1') {
    throw "post-write SHA-256 readback failed: $remoteOutput"
}
$remoteOutput | Write-Output
Write-Output "OMQ1_MTD4_FLASH_AND_READBACK_PASS=1 candidate=$ExpectedSha256 target=mtd4 rollback=mtd3 bootselect=0-unchanged rollback_mode=manual-uart-ATGO"
