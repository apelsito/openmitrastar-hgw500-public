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
    [Parameter(Mandatory=$true)] [string]$RollbackCrc32,
    [Parameter(Mandatory=$true)] [string]$CurrentLiveCrc32,
    [Parameter(Mandatory=$true)] [string]$ExpectedCandidateCrc32,
    [Parameter(Mandatory=$true)] [string]$ExpectedFullSlotSha256,
    [Parameter(Mandatory=$true)] [string]$ExpectedFullSlotCrc32,
    [Parameter(Mandatory=$true)] [string]$OmspiroModule,
    [Parameter(Mandatory=$true)] [string]$ExpectedOmspiroSha256,
    [Parameter(Mandatory=$true)] [long]$ExpectedOmspiroBytes,
    [Parameter(Mandatory=$true)] [string]$ExpectedOmspiroKernelRelease,
    [Parameter(Mandatory=$true)] [string]$ExpectedOmspiroDeviceMode,
    [Parameter(Mandatory=$true)] [string]$AssociationEvidence,
    [Parameter(Mandatory=$true)] [string]$ExpectedAssociationEvidenceSha256,
    [Parameter(Mandatory=$true)] [string]$Q2RollbackArtifact,
    [ValidateRange(600,1800)] [int]$TimeoutSeconds = 900,
    [switch]$SkipReboot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$RequiredAck = "OPENMITRASTAR_Q3_V3_MTD4_FLASH_1F0C1BF5_PASS_ASSOCIATED"
$ExpectedCandidate = "1f0c1bf5b29c77c3670be9891db9da6bb3d186f0fb931b8de711a5b5d89c6296"
$ExpectedQ2Rollback = "cbe904ab7a807838fa12077fab924c79ce3c112a5ef40727cbaf9ec98f638cf1"
$TargetOffset = 0x007e0000
$TargetBytes = 0x007a0000
$RollbackOffset = 0x00040000
$RollbackBytes = 0x007a0000
$LoadAddress = [Convert]::ToUInt32('83000000', 16)
$ReadbackAddress = [Convert]::ToUInt32('86000000', 16)
$CrcResultAddress = [Convert]::ToUInt32('84000000', 16)
$OmspiroMtd0Skip64K = 0
$OmspiroMtd0Count64K = 2
$OmspiroMtd1Skip64K = 2
$OmspiroMtd1Count64K = 1
$OmspiroMtd2Skip64K = 3
$OmspiroMtd2Count64K = 1
$OmspiroMtd3Skip64K = 4
$OmspiroMtd3Count64K = 122
$OmspiroMtd4Skip64K = 126
$OmspiroMtd4Count64K = 122
$OmspiroMtd5Skip64K = 248
$OmspiroMtd5Count64K = 8
$OmspiroMtd4Skip4K = 2016
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Candidate = [IO.Path]::GetFullPath($Candidate)
$OmspiroModule = [IO.Path]::GetFullPath($OmspiroModule)
$Transcript = [IO.Path]::GetFullPath($Transcript)
$AssociationEvidence = [IO.Path]::GetFullPath($AssociationEvidence)
$Q2RollbackArtifact = [IO.Path]::GetFullPath($Q2RollbackArtifact)

if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { throw "candidate missing" }
$ObservedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Candidate).Hash.ToLowerInvariant()
$ObservedBytes = (Get-Item -LiteralPath $Candidate).Length
if ($ExpectedSha256 -ne $ExpectedCandidate -or $ObservedHash -ne $ExpectedCandidate) { throw "candidate SHA-256 mismatch" }
if ($ExpectedBytes -ne 4312048 -or $ObservedBytes -ne 4312048) { throw "candidate size mismatch" }
if (-not (Test-Path -LiteralPath $Q2RollbackArtifact -PathType Leaf)) { throw "Q2 rollback artifact missing" }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $Q2RollbackArtifact).Hash.ToLowerInvariant() -ne $ExpectedQ2Rollback -or
    (Get-Item -LiteralPath $Q2RollbackArtifact).Length -ne 4157772) { throw "Q2 rollback artifact mismatch" }
if (-not (Test-Path -LiteralPath $AssociationEvidence -PathType Leaf)) { throw "PASS_ASSOCIATED evidence missing" }
$ObservedAssociationHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $AssociationEvidence).Hash.ToLowerInvariant()
if ($ExpectedAssociationEvidenceSha256 -notmatch '^[0-9a-f]{64}$' -or
    $ObservedAssociationHash -ne $ExpectedAssociationEvidenceSha256) { throw "association evidence SHA-256 mismatch" }
$Association = Get-Content -LiteralPath $AssociationEvidence -Raw | ConvertFrom-Json
if ($Association.schema -ne 'openmitrastar.q3-client-association-evidence/v1' -or
    $Association.status -ne 'PASS_ASSOCIATED' -or
    $Association.candidate_sha256 -ne $ExpectedCandidate -or
    $Association.client_association.status -ne 'PASS' -or
    $Association.client_traffic.status -ne 'PASS' -or
    $Association.flash_actions -ne $false) { throw "PASS_ASSOCIATED evidence contract failed" }
if (-not (Test-Path -LiteralPath $OmspiroModule -PathType Leaf)) { throw "OMSPIRO module missing" }
$ObservedOmspiroHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $OmspiroModule).Hash.ToLowerInvariant()
$ObservedOmspiroBytes = (Get-Item -LiteralPath $OmspiroModule).Length
if ($ExpectedOmspiroSha256 -ne "7e00484816f37496f263e22e1bb286d8383681f1af4ad5629cd49ca97d659201" -or
    $ObservedOmspiroHash -ne $ExpectedOmspiroSha256) { throw "OMSPIRO module SHA-256 mismatch" }
if ($ExpectedOmspiroBytes -ne 4856 -or $ObservedOmspiroBytes -ne 4856) { throw "OMSPIRO module size mismatch" }
if ($ExpectedOmspiroKernelRelease -ne "5.10.260-openmitrastar-radiohw") { throw "OMSPIRO kernel release mismatch" }
if ($ExpectedOmspiroDeviceMode -ne "0400") { throw "OMSPIRO read-only device mode mismatch" }
if (-not $Execute) {
    Write-Output "OMQ3_V3_BOOTBASE_FLASH_DRY_RUN_PASS=1 association=PASS_ASSOCIATED target=mtd4 offset=0x007e0000 size=0x007a0000 rollback=mtd3+q2 flash=0"
    exit 0
}
if ($Ack -ne $RequiredAck) { throw "execute requires exact acknowledgement" }
if ($HostAddress -ne "192.168.1.90" -or $ClientIp -ne "192.168.1.90") { throw "management identity mismatch" }
if ($RollbackSha256 -ne "f1a40a5a87bf4262f8c0a3a39e6041d0f32d06794cf0302b470bfe98a50134b1") { throw "rollback SHA-256 mismatch" }
if ($ProtectedMtd0Sha256 -ne "a5fee18d095b1a7987ad71492bc6d1f86656d6b6a0877adeb40e5300e2eff7f1" -or
    $ProtectedMtd1Sha256 -ne "12aac941ac824b6249a20e6c7523e46cd484ac5e8a85cdea73659835fb352b1d" -or
    $ProtectedMtd2Sha256 -ne "8992410e131045fd6521fb5ebd7de87bb95b862d65ea7811ee4f12b4beb65483" -or
    $ProtectedMtd5Sha256 -ne "1ba0ec4124a4fb34701ac08079b7598ecf7ac25b96380b92182d0e67261dbba0") {
    throw "protected partition hash mismatch"
}
foreach ($protected in @($ProtectedMtd0Sha256,$ProtectedMtd1Sha256,$ProtectedMtd2Sha256,$ProtectedMtd5Sha256)) {
    if ($protected -notmatch '^[0-9a-f]{64}$') { throw "invalid protected-partition SHA-256" }
}
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
        if ($script:tail -match 'Hit any key to stop autoboot') {
            $serial.Write(" "); $script:tail = ""
            $promptDeadline = [DateTime]::UtcNow.AddSeconds(45)
            while ([DateTime]::UtcNow -lt $promptDeadline) {
                [void](Read-Uart)
                if ($script:tail -match 'topaz>\s*$') { return }
                if ($script:tail -match 'ZHAL>\s*$') { Exit-ZhalBootExtension; return }
                Start-Sleep -Milliseconds 10
            }
            throw 'UART timeout during autoboot interruption'
        }
        if ($script:tail -match 'ZHAL>\s*$') {
            Exit-ZhalBootExtension; return
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
    Parse-Crc (Prompt-Crc $LoadAddress $ExpectedBytes 'candidate CRC' 90) $ExpectedCandidateCrc32 'candidate RAM image'

    $rollbackRead = Prompt-Command ("spi_flash read 0x{0:x8} 0x{1:x8} 0x{2:x8}" -f $RollbackOffset,$ReadbackAddress,$RollbackBytes) 'fresh rollback read' 180
    if ($rollbackRead -notmatch ("ret_size={0}" -f $RollbackBytes)) { throw "rollback read size mismatch" }
    Parse-Crc (Prompt-Crc $ReadbackAddress $RollbackBytes 'fresh rollback CRC' 90) $RollbackCrc32 'fresh rollback'
    $liveRead = Prompt-Command ("spi_flash read 0x{0:x8} 0x{1:x8} 0x{2:x8}" -f $TargetOffset,$ReadbackAddress,$TargetBytes) 'fresh current-live read' 180
    if ($liveRead -notmatch ("ret_size={0}" -f $TargetBytes)) { throw "current live read size mismatch" }
    Parse-Crc (Prompt-Crc $ReadbackAddress $TargetBytes 'fresh current-live CRC' 90) $CurrentLiveCrc32 'fresh current live'
    Write-Output "OMQ2_MTD4_PREWRITE_PHYSICAL_RECHECK_PASS=1 rollback_crc=$RollbackCrc32 current_live_crc=$CurrentLiveCrc32"

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
    Write-Output "OMQ2_MTD4_BOOTBASE_READBACK_PASS=1 full_slot_crc=$ExpectedFullSlotCrc32 prefix=identical"

    $script:tail = ""; Send-Uart ("bootm 0x{0:x8}" -f $LoadAddress)
    [void](Wait-Uart 'OMPRODUCT_ENTROPY_LOCAL_OK source=jitterentropy_rng credited_bits=256 crng=ready' 'RAM readback autonomous entropy' 180)
    [void](Wait-Uart 'OMPRODUCT_READY state=(ready|degraded)' 'RAM readback boot ready' 120)
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose(); $writer.Dispose()
}

Start-Sleep -Seconds 3
$verify = & python (Join-Path $PSScriptRoot 'verify_ramssh.py') --host $HostAddress --timeout 60 2>&1
if ($LASTEXITCODE -ne 0) { throw "post-write key-only SSH verification failed: $verify" }
$remoteOmspiro = "/tmp/omspiro-q2-readback.ko"
$upload = & python (Join-Path $PSScriptRoot 'ramssh_upload.py') $OmspiroModule $remoteOmspiro --host $HostAddress --mode 0600 2>&1
if ($LASTEXITCODE -ne 0 -or ($upload -join "`n") -notmatch 'RAMSSH_UPLOAD_OK') {
    throw "OMSPIRO upload failed: $upload"
}
$blocks = [Math]::Floor($ExpectedBytes / 4096)
$remainder = $ExpectedBytes % 4096
$prefixTailBlock = $OmspiroMtd4Skip4K + $blocks
$remote = @"
set -e
module=$remoteOmspiro
loaded_by_gate=0
cleanup() {
    if [ "`$loaded_by_gate" = 1 ]; then rmmod omspiro >/dev/null 2>&1 || true; fi
    rm -f "`$module"
}
trap cleanup 0 1 2 15
test "`$(uname -r)" = '$ExpectedOmspiroKernelRelease'
test "`$(sha256sum "`$module" | awk '{print `$1}')" = '$ExpectedOmspiroSha256'
ls -l "`$module" | grep -q '^-rw-------'
if grep -q '^omspiro ' /proc/modules; then
    echo OMQ2_OMSPIRO_PRELOADED_REFUSED=1
    exit 1
fi
insmod "`$module"
loaded_by_gate=1
test -c /dev/omspiro
ls -l /dev/omspiro | grep -q '^cr--------'
dmesg | tail -n 64 | grep -q 'OMSPIRO ready phys=0x90000000 size=0x01000000 dev=/dev/omspiro read-only'
protected0=`$(/bin/busybox dd if=/dev/omspiro bs=65536 skip=$OmspiroMtd0Skip64K count=$OmspiroMtd0Count64K 2>/dev/null | sha256sum | awk '{print `$1}')
protected1=`$(/bin/busybox dd if=/dev/omspiro bs=65536 skip=$OmspiroMtd1Skip64K count=$OmspiroMtd1Count64K 2>/dev/null | sha256sum | awk '{print `$1}')
protected2=`$(/bin/busybox dd if=/dev/omspiro bs=65536 skip=$OmspiroMtd2Skip64K count=$OmspiroMtd2Count64K 2>/dev/null | sha256sum | awk '{print `$1}')
safety=`$(/bin/busybox dd if=/dev/omspiro bs=65536 skip=$OmspiroMtd3Skip64K count=$OmspiroMtd3Count64K 2>/dev/null | sha256sum | awk '{print `$1}')
full=`$(/bin/busybox dd if=/dev/omspiro bs=65536 skip=$OmspiroMtd4Skip64K count=$OmspiroMtd4Count64K 2>/dev/null | sha256sum | awk '{print `$1}')
protected5=`$(/bin/busybox dd if=/dev/omspiro bs=65536 skip=$OmspiroMtd5Skip64K count=$OmspiroMtd5Count64K 2>/dev/null | sha256sum | awk '{print `$1}')
prefix=`$({ /bin/busybox dd if=/dev/omspiro bs=4096 skip=$OmspiroMtd4Skip4K count=$blocks 2>/dev/null; /bin/busybox dd if=/dev/omspiro bs=4096 skip=$prefixTailBlock count=1 2>/dev/null | /bin/busybox dd bs=1 count=$remainder 2>/dev/null; } | sha256sum | awk '{print `$1}')
echo OMQ2_OMSPIRO_MODULE_SHA=$ExpectedOmspiroSha256
echo OMQ2_OMSPIRO_DEVICE_MODE=$ExpectedOmspiroDeviceMode
echo OMQ2_READBACK_SAFETY_SHA=`$safety
echo OMQ2_READBACK_FULL_SLOT_SHA=`$full
echo OMQ2_READBACK_PREFIX_SHA=`$prefix
echo OMQ2_READBACK_PROTECTED_MTD0_SHA=`$protected0
echo OMQ2_READBACK_PROTECTED_MTD1_SHA=`$protected1
echo OMQ2_READBACK_PROTECTED_MTD2_SHA=`$protected2
echo OMQ2_READBACK_PROTECTED_MTD5_SHA=`$protected5
test "`$safety" = '$RollbackSha256'
test "`$full" = '$ExpectedFullSlotSha256'
test "`$prefix" = '$ExpectedSha256'
test "`$protected0" = '$ProtectedMtd0Sha256'
test "`$protected1" = '$ProtectedMtd1Sha256'
test "`$protected2" = '$ProtectedMtd2Sha256'
test "`$protected5" = '$ProtectedMtd5Sha256'
echo OMQ2_PROTECTED_PARTITIONS_UNCHANGED_PASS=1
rmmod omspiro
loaded_by_gate=0
rm -f "`$module"
trap - 0 1 2 15
test ! -e /dev/omspiro
test ! -e "`$module"
echo OMQ2_OMSPIRO_CLEANUP_PASS=1
echo OMQ2_REMOTE_SHA256_READBACK_PASS=1
"@
$remoteOutput = & python (Join-Path $PSScriptRoot 'ramssh_exec.py') $remote --host $HostAddress --timeout 180 2>&1
if ($LASTEXITCODE -ne 0 -or ($remoteOutput -join "`n") -notmatch 'OMQ2_REMOTE_SHA256_READBACK_PASS=1') {
    throw "post-write SHA-256 readback failed: $remoteOutput"
}
$remoteOutput | Write-Output
Write-Output "OMQ3_V3_MTD4_FLASH_AND_READBACK_PASS=1 candidate=$ExpectedSha256 association=PASS_ASSOCIATED target=mtd4 rollback=mtd3+q2 bootselect=0-unchanged rollback_mode=manual-uart-ATGO-or-q2-reflash"
