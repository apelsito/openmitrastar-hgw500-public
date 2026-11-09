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
    [Parameter(Mandatory=$true)] [string]$ProtectedMtd0Sha256,
    [Parameter(Mandatory=$true)] [string]$ProtectedMtd1Sha256,
    [Parameter(Mandatory=$true)] [string]$ProtectedMtd2Sha256,
    [Parameter(Mandatory=$true)] [string]$ProtectedMtd5Sha256,
    [Parameter(Mandatory=$true)] [string]$ProtectedMtd0Crc32,
    [Parameter(Mandatory=$true)] [string]$ProtectedMtd1Crc32,
    [Parameter(Mandatory=$true)] [string]$ProtectedMtd2Crc32,
    [Parameter(Mandatory=$true)] [string]$ProtectedMtd5Crc32,
    [Parameter(Mandatory=$true)] [string]$RollbackCrc32,
    [Parameter(Mandatory=$true)] [string]$CurrentLiveCrc32,
    [Parameter(Mandatory=$true)] [string]$ExpectedCandidateCrc32,
    [Parameter(Mandatory=$true)] [string]$ExpectedFullSlotSha256,
    [Parameter(Mandatory=$true)] [string]$ExpectedFullSlotCrc32,
    [ValidateRange(600,1800)] [int]$TimeoutSeconds = 900,
    [switch]$SkipReboot,
    [switch]$RequireProductReady
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$RequiredAck = "OPENMITRASTAR_Q3_F42_RADIO5_CONTRACT_FIX_OPENLAB_AUTOSTART_MTD4_FLASH_AB1F8009"
$ExpectedCandidate = "ab1f800967d51bd3e0119617d23e9d1a227a45591ea19880d8f1e27d0bc478c4"
$TargetOffset = 0x007e0000
$TargetBytes = 0x007a0000
$ProtectedMtd0Offset = 0x00000000
$ProtectedMtd0Bytes = 0x00020000
$ProtectedMtd1Offset = 0x00020000
$ProtectedMtd1Bytes = 0x00010000
$ProtectedMtd2Offset = 0x00030000
$ProtectedMtd2Bytes = 0x00010000
$RollbackOffset = 0x00040000
$RollbackBytes = 0x007a0000
$ProtectedMtd5Offset = 0x00f80000
$ProtectedMtd5Bytes = 0x00080000
$LoadAddress = [Convert]::ToUInt32('83000000', 16)
$ReadbackAddress = [Convert]::ToUInt32('86000000', 16)
$CrcResultAddress = [Convert]::ToUInt32('84000000', 16)
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Candidate = [IO.Path]::GetFullPath($Candidate)
$Transcript = [IO.Path]::GetFullPath($Transcript)

if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { throw "candidate missing" }
$ObservedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Candidate).Hash.ToLowerInvariant()
$ObservedBytes = (Get-Item -LiteralPath $Candidate).Length
if ($ExpectedSha256 -ne $ExpectedCandidate -or $ObservedHash -ne $ExpectedCandidate) { throw "candidate SHA-256 mismatch" }
if ($ExpectedBytes -ne 4336578 -or $ObservedBytes -ne 4336578) { throw "candidate size mismatch" }
if (-not $Execute) {
    Write-Output "OMQ3_F42_RADIO5_CONTRACT_FIX_OPENLAB_BOOTBASE_FLASH_DRY_RUN_PASS=1 target=mtd4 offset=0x007e0000 size=0x007a0000 rollback=mtd3 flash=0 linux_ram_writes=0"
    exit 0
}
if ($Ack -ne $RequiredAck) { throw "execute requires exact acknowledgement" }
if (-not $SkipReboot) { throw "execute requires -SkipReboot: Linux-side reboot/ramssh entry is disabled by no-more-RAM-writes policy" }
if ($HostAddress -ne "192.168.1.90" -or $ClientIp -ne "192.168.1.90") { throw "management identity mismatch" }
if ($RollbackSha256 -ne "f1a40a5a87bf4262f8c0a3a39e6041d0f32d06794cf0302b470bfe98a50134b1") { throw "rollback SHA-256 mismatch" }
foreach ($protected in @($ProtectedMtd0Sha256,$ProtectedMtd1Sha256,$ProtectedMtd2Sha256,$ProtectedMtd5Sha256)) {
    if ($protected -notmatch '^[0-9a-f]{64}$') { throw "invalid protected-partition SHA-256" }
}
foreach ($crc in @($ProtectedMtd0Crc32,$ProtectedMtd1Crc32,$ProtectedMtd2Crc32,$ProtectedMtd5Crc32,$RollbackCrc32,$CurrentLiveCrc32,$ExpectedCandidateCrc32,$ExpectedFullSlotCrc32)) {
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
function Exit-ZhalBootExtension {
    $escaped = $false
    for ($attempt = 1; $attempt -le 3 -and -not $escaped; $attempt++) {
        $script:tail = ""
        $serial.Write([string][char]0x15)
        $serial.Write([string][char]0x08)
        Start-Sleep -Milliseconds 80
        Send-Uart 'ATGU'
        $deadline = [DateTime]::UtcNow.AddSeconds(8)
        while ([DateTime]::UtcNow -lt $deadline) {
            [void](Read-Uart)
            if ($script:tail -match 'Hit any key to exit') { $escaped = $true; break }
            if ($script:tail -match 'command not found') { break }
            Start-Sleep -Milliseconds 10
        }
    }
    if (-not $escaped) { throw 'ZHAL rejected ATGU after three cleared-line attempts' }
    $serial.Write(' ')
    $script:tail = ""
    [void](Wait-Uart 'Hit any key to stop autoboot' 'post-BootExtension autoboot' 30)
    $serial.Write(' ')
    $script:tail = ""
    [void](Wait-Prompt 'post-BootExtension prompt' 45)
}
function Parse-Crc([string]$Text, [string]$Expected, [string]$Stage) {
    $matches = [regex]::Matches($Text, '(?im)CRC32.*?(?:==>|=)\s*([0-9a-f]{8})')
    if ($matches.Count -gt 0) {
        $actual = $matches[$matches.Count - 1].Groups[1].Value.ToLowerInvariant()
    } else {
        $address = '{0:x8}' -f $CrcResultAddress
        $memory = [regex]::Matches($Text, "(?im)^${address}:\s*([0-9a-f]{8})\b")
        if ($memory.Count -lt 1) { throw "CRC32 RAM readback missing during $Stage" }
        $actual = $memory[$memory.Count - 1].Groups[1].Value.ToLowerInvariant()
    }
    if ($actual -ne $Expected) { throw "CRC32 mismatch during $Stage expected=$Expected actual=$actual" }
}
function Prompt-Crc([uint32]$Address, [uint32]$Bytes, [string]$Stage, [int]$Seconds = 120) {
    $command = "crc32 0x{0:x8} 0x{1:x8} 0x{2:x8}; md.l 0x{2:x8} 1" -f $Address,$Bytes,$CrcResultAddress
    return Prompt-Command $command $Stage $Seconds
}
function Check-Flash-Crc([uint32]$Offset, [uint32]$Bytes, [string]$Expected, [string]$Stage, [int]$Seconds = 180) {
    $read = Prompt-Command ("spi_flash read 0x{0:x8} 0x{1:x8} 0x{2:x8}" -f $Offset,$ReadbackAddress,$Bytes) $Stage $Seconds
    if ($read -notmatch ("ret_size={0}" -f $Bytes)) { throw "$Stage read size mismatch" }
    Parse-Crc (Prompt-Crc $ReadbackAddress $Bytes "$Stage CRC" 90) $Expected $Stage
}
function Acquire-Bootbase {
    if ($SkipReboot) {
        $serial.DiscardInBuffer(); $script:tail = ""
        $serial.Write([string][char]0x15); $serial.Write("`r")
        $deadline = [DateTime]::UtcNow.AddSeconds(5)
        while ([DateTime]::UtcNow -lt $deadline) {
            [void](Read-Uart)
            if ($script:tail -match 'topaz>\s*$') { return }
            if ($script:tail -match 'ZHAL>\s*$') { Exit-ZhalBootExtension; return }
            Start-Sleep -Milliseconds 10
        }
        throw 'existing Bootbase/ZHAL prompt not found'
    }
    throw "Linux-side reboot/ramssh entry is disabled by no-more-RAM-writes policy"
}

try {
    $serial.Open(); Acquire-Bootbase
    [void](Prompt-Command "setenv ipaddr $ClientIp" 'volatile ipaddr')
    [void](Prompt-Command "setenv serverip $ServerIp" 'volatile serverip')
    $envBefore = Prompt-Command 'printenv bootcmd; printenv bootselect' 'prewrite boot selector' 30
    if ($envBefore -notmatch '(?m)^bootcmd=bootselect\r?$' -or $envBefore -notmatch '(?m)^bootselect=0\r?$') {
        throw "prewrite selector differs from documented current-unit bootselect=0"
    }
    Check-Flash-Crc $ProtectedMtd0Offset $ProtectedMtd0Bytes $ProtectedMtd0Crc32 'prewrite protected mtd0'
    Check-Flash-Crc $ProtectedMtd1Offset $ProtectedMtd1Bytes $ProtectedMtd1Crc32 'prewrite protected mtd1'
    Check-Flash-Crc $ProtectedMtd2Offset $ProtectedMtd2Bytes $ProtectedMtd2Crc32 'prewrite protected mtd2'
    Check-Flash-Crc $ProtectedMtd5Offset $ProtectedMtd5Bytes $ProtectedMtd5Crc32 'prewrite protected mtd5'
    $script:tail = ""; Send-Uart ("tftpboot 0x{0:x8} {1}" -f $LoadAddress, [IO.Path]::GetFileName($Candidate))
    [void](Wait-Uart ("Bytes transferred = {0}" -f $ExpectedBytes) 'candidate TFTP transfer' 240)
    [void](Wait-Prompt 'candidate TFTP prompt' 30)
    $iminfo = Prompt-Command ("iminfo 0x{0:x8}" -f $LoadAddress) 'candidate iminfo' 60
    if ($iminfo -notmatch 'Verifying Checksum \.\.\. OK') { throw "Bootbase iminfo rejected candidate" }
    Parse-Crc (Prompt-Crc $LoadAddress $ExpectedBytes 'candidate CRC' 90) $ExpectedCandidateCrc32 'candidate RAM image'

    $rollbackRead = Prompt-Command ("spi_flash read 0x{0:x8} 0x{1:x8} 0x{2:x8}" -f $RollbackOffset,$ReadbackAddress,$RollbackBytes) 'fresh rollback read' 180
    if ($rollbackRead -notmatch ("ret_size={0}" -f $RollbackBytes)) { throw "rollback read size mismatch" }
    Parse-Crc (Prompt-Crc $ReadbackAddress $RollbackBytes 'fresh rollback CRC' 90) $RollbackCrc32 'fresh rollback'
    $liveRead = Prompt-Command ("spi_flash read 0x{0:x8} 0x{1:x8} 0x{2:x8}" -f $TargetOffset,$ReadbackAddress,$TargetBytes) 'fresh current-live read' 180
    if ($liveRead -notmatch ("ret_size={0}" -f $TargetBytes)) { throw "current live read size mismatch" }
    Parse-Crc (Prompt-Crc $ReadbackAddress $TargetBytes 'fresh current-live CRC' 90) $CurrentLiveCrc32 'fresh current live'
    Write-Output "OMQ3_F42_RADIO5_CONTRACT_FIX_OPENLAB_MTD4_PREWRITE_PHYSICAL_RECHECK_PASS=1 rollback_crc=$RollbackCrc32 current_live_crc=$CurrentLiveCrc32"

    [void](Prompt-Command ("spi_flash erase 0x{0:x8} 0x{1:x8}" -f $TargetOffset,$TargetBytes) 'mtd4 erase' 300)
    $write = Prompt-Command ("spi_flash write 0x{0:x8} 0x{1:x8} 0x{2:x8}" -f $TargetOffset,$LoadAddress,$ExpectedBytes) 'mtd4 candidate write' 300
    if ($write -notmatch ("ret_size={0}" -f $ExpectedBytes)) { throw "mtd4 write size mismatch" }
    $readback = Prompt-Command ("spi_flash read 0x{0:x8} 0x{1:x8} 0x{2:x8}" -f $TargetOffset,$ReadbackAddress,$TargetBytes) 'mtd4 full readback' 240
    if ($readback -notmatch ("ret_size={0}" -f $TargetBytes)) { throw "mtd4 readback size mismatch" }
    Parse-Crc (Prompt-Crc $ReadbackAddress $TargetBytes 'mtd4 full readback CRC' 120) $ExpectedFullSlotCrc32 'mtd4 full readback'
    $compare = Prompt-Command ("cmp.b 0x{0:x8} 0x{1:x8} 0x{2:x8}" -f $LoadAddress,$ReadbackAddress,$ExpectedBytes) 'mtd4 candidate-prefix compare' 180
    if ($compare -notmatch 'Total of [0-9]+ (byte|bytes|word|words) were the same') { throw "mtd4 candidate prefix compare failed" }
    $envAfter = Prompt-Command 'printenv bootcmd; printenv bootselect' 'postwrite boot selector' 30
    if ($envAfter -notmatch '(?m)^bootcmd=bootselect\r?$' -or $envAfter -notmatch '(?m)^bootselect=0\r?$') {
        throw "postwrite current-unit selector changed"
    }
    Check-Flash-Crc $ProtectedMtd0Offset $ProtectedMtd0Bytes $ProtectedMtd0Crc32 'postwrite protected mtd0'
    Check-Flash-Crc $ProtectedMtd1Offset $ProtectedMtd1Bytes $ProtectedMtd1Crc32 'postwrite protected mtd1'
    Check-Flash-Crc $ProtectedMtd2Offset $ProtectedMtd2Bytes $ProtectedMtd2Crc32 'postwrite protected mtd2'
    Check-Flash-Crc $ProtectedMtd5Offset $ProtectedMtd5Bytes $ProtectedMtd5Crc32 'postwrite protected mtd5'
    Write-Output "OMQ3_F42_RADIO5_CONTRACT_FIX_OPENLAB_PROTECTED_PARTITION_CRC_PASS=1 mtd0=$ProtectedMtd0Crc32 mtd1=$ProtectedMtd1Crc32 mtd2=$ProtectedMtd2Crc32 mtd3=$RollbackCrc32 mtd5=$ProtectedMtd5Crc32"
    Write-Output "OMQ3_F42_RADIO5_CONTRACT_FIX_OPENLAB_MTD4_BOOTBASE_READBACK_PASS=1 full_slot_crc=$ExpectedFullSlotCrc32 prefix=identical"

    $script:tail = ""; Send-Uart 'bootselect'
    [void](Wait-Uart 'Linux version 5\.10\.260-openmitrastar-radiohw' 'flash boot Linux 5.10' 180)
    [void](Wait-Uart 'OMNETWORK_READY profile=oem-videobridge interface=eth0 ipv4=192\.168\.1\.90' 'flash boot network ready' 120)
    [void](Wait-Uart 'OMSSH_READY port=22 auth=ed25519-key-only forwarding=disabled' 'flash boot ssh ready' 120)
    if ($RequireProductReady) {
        [void](Wait-Uart 'OMPRODUCT_READY state=(ready|degraded)' 'flash boot product ready' 120)
    } else {
        try {
            [void](Wait-Uart 'OMPRODUCT_READY state=(ready|degraded)' 'flash boot product ready optional' 20)
        } catch {
            Write-Output "OMQ3_F42_RADIO5_CONTRACT_FIX_OPENLAB_PRODUCT_READY_OPTIONAL_TIMEOUT=1 ssh_ready=1 network_ready=1"
        }
    }
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose(); $writer.Dispose()
}

Start-Sleep -Seconds 3
$sshReady = $false
$deadline = [DateTime]::UtcNow.AddSeconds(60)
while ([DateTime]::UtcNow -lt $deadline) {
    $tcp = Test-NetConnection -ComputerName $HostAddress -Port 22 -InformationLevel Quiet -WarningAction SilentlyContinue
    if ($tcp) { $sshReady = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $sshReady) { throw "post-write SSH port check failed" }
Write-Output "OMQ3_F42_RADIO5_CONTRACT_FIX_OPENLAB_FLASH_BOOT_SSH_PASS=1 host=$HostAddress kernel=5.10.260-openmitrastar-radiohw"
Write-Output "OMQ3_F42_RADIO5_CONTRACT_FIX_OPENLAB_MTD4_FLASH_AND_READBACK_PASS=1 candidate=$ExpectedSha256 target=mtd4 rollback=mtd3 bootselect=0-unchanged boot=flash-bootselect rollback_mode=manual-uart-ATGO linux_ram_writes=0 bootbase_readback=1"

