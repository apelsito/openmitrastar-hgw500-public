[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [ValidateRange(5, 60)][int]$PollSeconds = 12,
    [ValidateRange(180, 900)][int]$PhaseTimeoutSeconds = 360,
    [string]$VectorPath = "",
    [string]$OutputDir = "",
    [string]$CampaignStateRoot = "",
    [string]$SharedLockDir = "",
    [switch]$SkipProcessInventory
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$device = "hgw500bna-qcv2-a2-primary"
$deviceRoot = Join-Path $env:USERPROFILE ".openmitrastar\devices\$device"
$f301Root = Join-Path $deviceRoot "firmware\f301-device-bound"
$f301ManifestPath = Join-Path $f301Root "manifest.json"
$f301KnownHosts = Join-Path $f301Root "known_hosts.f301"
$oemFirmware = Join-Path $root "Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin"
$oemRadarModule = Join-Path $root "work\hgw500-rootfs-live\squashfs-root\lib\modules\2.6.35.12\extra\radar\radar.ko"
$atgoEvidence = Join-Path $root "outputs\uart-live\zhal-atgo-oem.log"
$evidenceTool = Join-Path $root "tools\f303_radar_oracle_evidence.py"
$defaultVector = Join-Path $root "outputs\kernel-port\f303-oem-radar-re-20260904\test-vectors\synthetic-normalization.json"
$requiredAck = "OPENMITRASTAR_F303_RADAR_ORACLE_MTD3_TEMPORARY"
$expectedF301Version = "lyoko-foundation-6.6.1-f301-f300-capability-truth-device"
$expectedF301Sha256 = "4c280e84b4593008b900cec70041b801d204bdde748b09064410708253b87262"
$expectedMtd3Sha256 = "f1a40a5a87bf4262f8c0a3a39e6041d0f32d06794cf0302b470bfe98a50134b1"
$expectedOemSha256 = "f39ed40cc66010287574bdc41c9fc18a6ba7d674f7c0acd7d7d47f8ab633a42f"
$expectedRadarSha256 = "3550945b4affe54ddc5dcc6a3d13bb4caed6f38e1a6d0fb7b295028381e58332"
$expectedAtgoEvidenceSha256 = "ef928a82ffe27f9a8b982d8a361dc490b13c3639267cc941ba9571ecd1cb88c8"
$defaultCampaignStateRoot = Join-Path $root "outputs"
$defaultSharedLockDir = Join-Path $root "outputs\locks\f301-physical-radio.lock"

if (-not $VectorPath) { $VectorPath = $defaultVector }
if (-not $CampaignStateRoot) { $CampaignStateRoot = $defaultCampaignStateRoot }
if (-not $SharedLockDir) { $SharedLockDir = $defaultSharedLockDir }
$VectorPath = if ([IO.Path]::IsPathRooted($VectorPath)) {
    [IO.Path]::GetFullPath($VectorPath)
} else {
    [IO.Path]::GetFullPath((Join-Path $root $VectorPath))
}
$CampaignStateRoot = [IO.Path]::GetFullPath($CampaignStateRoot)
$SharedLockDir = [IO.Path]::GetFullPath($SharedLockDir)

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "").ToLowerInvariant() }
    finally { $sha.Dispose(); $stream.Dispose() }
}

function Write-AtomicJson([string]$Path, [object]$Value) {
    $directory = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $temporary = Join-Path $directory (".{0}.{1}.tmp" -f ([IO.Path]::GetFileName($Path)), [Guid]::NewGuid().ToString("N"))
    try {
        $Value | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $temporary -Encoding ascii
        if (Test-Path -LiteralPath $Path) {
            $backup = $Path + "." + [Guid]::NewGuid().ToString("N") + ".bak"
            [IO.File]::Replace($temporary, $Path, $backup)
            Remove-Item -LiteralPath $backup -Force
        } else {
            [IO.File]::Move($temporary, $Path)
        }
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Test-Tcp([string]$HostName, [int]$TcpPort, [int]$TimeoutMs = 1200) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $pending = $client.BeginConnect($HostName, $TcpPort, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne($TimeoutMs)) { return $false }
        $client.EndConnect($pending)
        return $true
    } catch { return $false } finally { $client.Dispose() }
}

function Get-CampaignState([switch]$IgnoreSharedLock) {
    $processes = @()
    $checkpoints = @()
    $errors = @()
    if (-not $SkipProcessInventory) {
        try {
            $processes = @(Get-CimInstance Win32_Process -ErrorAction Stop |
                Where-Object {
                    $_.ProcessId -ne $PID -and $_.CommandLine -and
                    $_.CommandLine -match 'f30[01]_(?:sequential|multicast|vlan|store|radar)|run_f301_sequential_dual_radio_soak|run_f301_multicast_igmp_physical'
                } |
                ForEach-Object { [ordered]@{ pid = [int]$_.ProcessId; name = [string]$_.Name } })
        } catch { $errors += "process_inventory: $($_.Exception.Message)" }
    }
    $soakRoot = Join-Path $CampaignStateRoot "soak"
    if (Test-Path -LiteralPath $soakRoot) {
        foreach ($path in @(Get-ChildItem -LiteralPath $soakRoot -Recurse -Filter checkpoint.json -File -ErrorAction SilentlyContinue)) {
            try {
                $payload = Get-Content -Raw -LiteralPath $path.FullName | ConvertFrom-Json
                if ($payload.status -eq "IN_PROGRESS") {
                    $checkpoints += [ordered]@{ path = $path.FullName; status = "IN_PROGRESS"; updated_at = [string]$payload.updated_at }
                }
            } catch { $errors += "checkpoint:$($path.FullName): $($_.Exception.Message)" }
        }
    }
    $lockPresent = $false
    $lockOwner = $null
    if (-not $IgnoreSharedLock -and (Test-Path -LiteralPath $SharedLockDir)) {
        $lockPresent = $true
        try { $lockOwner = Get-Content -Raw -LiteralPath (Join-Path $SharedLockDir "owner.json") | ConvertFrom-Json }
        catch { $errors += "shared_lock_owner: $($_.Exception.Message)" }
    }
    return [ordered]@{
        active = [bool]($processes.Count -gt 0 -or $checkpoints.Count -gt 0 -or $lockPresent -or $errors.Count -gt 0)
        processes = $processes
        in_progress_checkpoints = $checkpoints
        shared_lock_present = $lockPresent
        shared_lock_owner = $lockOwner
        detection_errors = $errors
        fail_closed = $true
    }
}

function Acquire-SharedLock([string]$EvidenceDir) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $SharedLockDir) | Out-Null
    try { New-Item -ItemType Directory -Path $SharedLockDir -ErrorAction Stop | Out-Null }
    catch { throw "F301 physical campaign lock is already held" }
    [ordered]@{
        schema = "openmitrastar.f301-physical-radio-lock/v1"
        owner = "f303-radar-oracle"
        pid = $PID
        started_at = [DateTime]::UtcNow.ToString("o")
        evidence_dir = $EvidenceDir
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $SharedLockDir "owner.json") -Encoding ascii
}

function Release-SharedLock {
    if (Test-Path -LiteralPath $SharedLockDir) { Remove-Item -LiteralPath $SharedLockDir -Recurse -Force }
}

function Invoke-F301Ssh([string]$Command, [int]$Attempts = 4) {
    $ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
    $last = ""
    foreach ($attempt in 1..$Attempts) {
        $output = & $ssh -i "$env:USERPROFILE\.ssh\id_ed25519" -o IdentitiesOnly=yes -o BatchMode=yes `
            -o ConnectTimeout=8 -o ServerAliveInterval=4 -o ServerAliveCountMax=2 `
            -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$f301KnownHosts" -o LogLevel=ERROR `
            "root@$RouterHost" $Command 2>&1
        $last = ($output | Out-String).Trim()
        if ($LASTEXITCODE -eq 0) { return $last }
        if ($attempt -lt $Attempts) { Start-Sleep -Seconds 3 }
    }
    throw "F301 SSH command failed: $last"
}

foreach ($path in @($f301ManifestPath, $f301KnownHosts, $oemFirmware, $oemRadarModule, $atgoEvidence, $evidenceTool, $VectorPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing local contract input: $path" }
}

$f301Manifest = Get-Content -Raw -LiteralPath $f301ManifestPath | ConvertFrom-Json
$f301Candidate = Join-Path $f301Root ([string]$f301Manifest.artifacts.webformat.file)
if (-not (Test-Path -LiteralPath $f301Candidate -PathType Leaf)) { throw "Missing F301 candidate" }
$localHashes = [ordered]@{
    f301 = Get-Sha256 $f301Candidate
    oem_firmware = Get-Sha256 $oemFirmware
    oem_radar_module = Get-Sha256 $oemRadarModule
    proven_atgo_log = Get-Sha256 $atgoEvidence
}
$localContractPass = (
    $localHashes.f301 -eq $expectedF301Sha256 -and
    $localHashes.oem_firmware -eq $expectedOemSha256 -and
    $localHashes.oem_radar_module -eq $expectedRadarSha256 -and
    $localHashes.proven_atgo_log -eq $expectedAtgoEvidenceSha256 -and
    $f301Manifest.artifacts.webformat.sha256 -eq $expectedF301Sha256 -and
    $f301Manifest.artifacts.full_slot.sha256 -eq "c9c98d000fa9ea1c2fd53738e97decf83ef9a21132b382a23df03121fac1577b" -and
    $f301Manifest.contracts.bootbase -eq "PASS"
)

if (-not $OutputDir) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $OutputDir = Join-Path $root "outputs\preflight\f303-radar-oracle-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $OutputDir) {
    if (@(Get-ChildItem -LiteralPath $OutputDir -Force).Count -gt 0) { throw "Refusing to overwrite evidence directory: $OutputDir" }
} else { New-Item -ItemType Directory -Path $OutputDir | Out-Null }

$oracleCommandsPath = Join-Path $OutputDir "oracle-commands.json"
& python $evidenceTool vector --input $VectorPath --output $oracleCommandsPath | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Synthetic oracle vector contract failed" }
$oracleCommands = Get-Content -Raw -LiteralPath $oracleCommandsPath | ConvertFrom-Json
$campaign = Get-CampaignState
$plan = [ordered]@{
    schema = "openmitrastar.f303-radar-oracle-plan/v1"
    generated_at = [DateTime]::UtcNow.ToString("o")
    mode = if ($Execute) { "execute" } else { "dry-run" }
    target = $device
    router = $RouterHost
    uart = $Port
    installed_baseline = $expectedF301Version
    installed_candidate_sha256 = $expectedF301Sha256
    preserved_oem_slot = [ordered]@{
        partition = "mtd3/linux_safety"
        offset = "0x00040000"
        bytes = 7995392
        expected_sha256 = $expectedMtd3Sha256
        access = "Bootbase spi_flash read to RAM only"
    }
    return_slot = [ordered]@{
        partition = "mtd4/linux_live"
        offset = "0x007e0000"
        bytes = 7995392
        candidate_sha256 = $expectedF301Sha256
    }
    oem_reference = [ordered]@{
        firmware_sha256 = $localHashes.oem_firmware
        radar_module_sha256 = $localHashes.oem_radar_module
        atgo_evidence_sha256 = $localHashes.proven_atgo_log
    }
    oracle_vector = [ordered]@{
        path = $VectorPath
        name = $oracleCommands.vector_name
        source = $oracleCommands.source
        region = $oracleCommands.region
        channel = $oracleCommands.channel
        bandwidth_mhz = $oracleCommands.bandwidth_mhz
        pulse_count = $oracleCommands.pulse_count
    }
    sequence = @("F301 read-only identity", "temporary Bootbase mtd3 read", "OEM init=/bin/sh", "start", "bandwidth", "channel", "enable", "poll/detection", "disable", "all-MTD hash comparison", "reboot to persistent F301")
    timeouts = [ordered]@{ phase_seconds = $PhaseTimeoutSeconds; poll_seconds = $PollSeconds; recovery_seconds = 420 }
    persistence_guards = [ordered]@{
        environment_persist = $false
        boot_environment_write = $false
        flash_erase = $false
        flash_write = $false
        mtd_write = $false
        oem_init = "init=/bin/sh"
        writable_overlay_mount = $false
        mtd5_mount = $false
    }
    evidence_policy = [ordered]@{
        raw_uart_retained = $false
        sanitized_uart_allowlist_only = $true
        calibration_retained = $false
        credentials_retained = $false
        client_mac_retained = $false
        hashes_generated = $true
    }
    campaign_guard = $campaign
    local_contract_pass = $localContractPass
    execute_eligible_offline = [bool]($localContractPass -and -not $campaign.active)
    execute_allowed_now = $false
    hardware_preflight = "DEFERRED_UNTIL_EXECUTE"
    hardware_actions_performed = $false
}
Write-AtomicJson (Join-Path $OutputDir "plan.json") $plan
& python $evidenceTool manifest --directory $OutputDir --output (Join-Path $OutputDir "evidence-sha256.json") | Out-Null
$plan | ConvertTo-Json -Depth 12

if (-not $Execute) { exit $(if ($localContractPass) { 0 } else { 1 }) }
if ([IO.Path]::GetFullPath($CampaignStateRoot) -ne [IO.Path]::GetFullPath($defaultCampaignStateRoot) -or
    [IO.Path]::GetFullPath($SharedLockDir) -ne [IO.Path]::GetFullPath($defaultSharedLockDir) -or
    $SkipProcessInventory) {
    throw "Execute mode refuses campaign-state, lock-path or process-inventory overrides"
}
if ($Ack -ne $requiredAck) { throw "Refusing OEM oracle capture: exact -Ack is required" }
if (-not $localContractPass) { throw "Local F301/OEM artifact contract mismatch" }
if ($campaign.active) { throw "Another physical campaign is active" }

$eventPath = Join-Path $OutputDir "events.jsonl"
$sanitizedUartPath = Join-Path $OutputDir "uart-sanitized.log"
$resultPath = Join-Path $OutputDir "result.json"
$serial = $null
$lockAcquired = $false
$phase = "preflight"
$tail = ""
$lineBuffer = ""
$rawHasher = [Security.Cryptography.SHA256]::Create()
$rawFinalized = $false
$mtdBefore = @{}
$mtdAfter = @{}

function Write-Event([string]$Name, [string]$Status, [object]$Details = $null) {
    $record = [ordered]@{ at = [DateTime]::UtcNow.ToString("o"); event = $Name; status = $Status; phase = $script:phase }
    if ($null -ne $Details) { $record.details = $Details }
    Add-Content -LiteralPath $eventPath -Value ($record | ConvertTo-Json -Compress -Depth 8) -Encoding ascii
}

function Add-SanitizedLine([string]$Line) {
    $line = $Line.Replace([char]0, '').TrimEnd("`r")
    if (-not $line) { return }
    if ($line -match '(?i)(psk|passphrase|password|private[_ -]?key|secret|calibration|wifiaddr|ethaddr|serialnumber|txpower[.]cal|dc_iq|pdetector)' -or
        $line -match '(?i)([0-9a-f]{2}:){5}[0-9a-f]{2}') { return }
    $safe = ($line -match '^(OMRADAR_|OMF301_|BOOTBASE_)') -or
        ($line -match '^Read: flash=0x(40000|7e0000) mem=0x83000000 size=7995392 ret_size=7995392$') -or
        ($line -match '^\s*Verifying Checksum\s+\.\.\.\s+OK\s*$') -or
        ($line -match '^Linux version (2\.6\.35\.12|5\.10\.260-openmitrastar-radiohw)\b') -or
        ($line -match '^VFS: Mounted root \(squashfs filesystem\) readonly\b')
    if ($safe) { Add-Content -LiteralPath $sanitizedUartPath -Value $line -Encoding ascii }
}

function Read-Uart {
    $chunk = $serial.ReadExisting()
    if (-not $chunk) { return }
    $bytes = [Text.Encoding]::UTF8.GetBytes($chunk)
    $null = $rawHasher.TransformBlock($bytes, 0, $bytes.Length, $null, 0)
    $script:tail += $chunk
    if ($script:tail.Length -gt 131072) { $script:tail = $script:tail.Substring($script:tail.Length - 131072) }
    $script:lineBuffer += $chunk
    $parts = $script:lineBuffer -split "`n", -1
    if ($parts.Count -gt 1) {
        foreach ($line in $parts[0..($parts.Count - 2)]) { Add-SanitizedLine $line }
        $script:lineBuffer = $parts[-1]
    }
}

function Send-Uart([string]$Text, [switch]$NoRecord) {
    $serial.Write($Text + "`r")
    if (-not $NoRecord) { Write-Event "uart-command" "SENT" ([ordered]@{ command = $Text }) }
}

function Wait-Uart([string]$Pattern, [int]$Seconds, [string]$Description, [switch]$ClearTail) {
    if ($ClearTail) { $script:tail = "" }
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        Read-Uart
        if ($script:tail -match $Pattern) { Write-Event $Description "PASS"; return $Matches[0] }
        Start-Sleep -Milliseconds 25
    }
    throw "Timeout waiting for $Description"
}

function Acquire-TopazPrompt([int]$Seconds) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    $lastBreak = [DateTime]::MinValue
    while ([DateTime]::UtcNow -lt $deadline) {
        Read-Uart
        if ($tail -match 'topaz>\s*$') { Write-Event "topaz-prompt" "PASS"; return }
        if ($tail -match 'ZHAL>\s*$') { Send-Uart "ATGU"; $script:tail = "" }
        if ($tail -match 'Hit any key (?:to stop autoboot|to exit)' -and ([DateTime]::UtcNow - $lastBreak).TotalMilliseconds -gt 800) {
            $serial.Write(" "); Start-Sleep -Milliseconds 50; $serial.Write("`r")
            $lastBreak = [DateTime]::UtcNow
        }
        Start-Sleep -Milliseconds 25
    }
    throw "Timeout acquiring topaz prompt"
}

function Invoke-OemCommand([string]$Name, [string]$Command, [int]$Seconds = 60) {
    $marker = "OMRADAR_CMD_END_${Name}_RC="
    $script:tail = ""
    Send-Uart ("echo OMRADAR_CMD_BEGIN_{0}; {1}; rc=`$?; echo {2}`$rc" -f $Name, $Command, $marker)
    Wait-Uart ([regex]::Escape($marker) + '0') $Seconds $Name | Out-Null
}

function Wait-F301Ssh([int]$Seconds) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Tcp $RouterHost 22) {
            try {
                $version = Invoke-F301Ssh "sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release" 1
                if ($version.Trim() -eq $expectedF301Version) { return $version.Trim() }
            } catch { }
        }
        Start-Sleep -Seconds 4
    }
    throw "F301 SSH did not return"
}

function Attempt-Recovery {
    $recovery = [ordered]@{ attempted = $true; method = "none"; f301_restored = $false; error = "" }
    try {
        if ($null -ne $serial -and $serial.IsOpen) {
            $serial.BreakState = $true; Start-Sleep -Milliseconds 600; $serial.BreakState = $false
            Start-Sleep -Milliseconds 150; $serial.Write("b")
            $recovery.method = "uart-sysrq-reset-then-normal-bootselect"
            try { Acquire-TopazPrompt 120 } catch { }
            if ($tail -match 'topaz>\s*$') {
                Send-Uart "spi_flash read 0x007e0000 0x83000000 0x007a0000"
                Wait-Uart 'topaz>\s*$' 120 "recovery-live-read" -ClearTail | Out-Null
                if ($tail -notmatch 'ret_size=7995392') { throw "Recovery live-slot read size mismatch" }
                Send-Uart "iminfo 0x83000000"
                Wait-Uart 'topaz>\s*$' 60 "recovery-live-iminfo" -ClearTail | Out-Null
                if ($tail -notmatch 'Verifying Checksum\s+\.\.\.\s+OK') { throw "Recovery F301 iminfo failed" }
                Send-Uart "bootm 0x83000000"
                $recovery.method = "direct-readonly-mtd4-boot"
            }
        }
        $null = Wait-F301Ssh 420
        $recovery.f301_restored = $true
    } catch { $recovery.error = $_.Exception.Message }
    return $recovery
}

try {
    Acquire-SharedLock $OutputDir
    $lockAcquired = $true
    $campaignAfterLock = Get-CampaignState -IgnoreSharedLock
    if ($campaignAfterLock.active) { throw "Campaign became active while acquiring the hardware lock" }
    if (-not (Test-Tcp $RouterHost 22)) { throw "F301 SSH is unavailable" }
    if (-not ([IO.Ports.SerialPort]::GetPortNames() -contains $Port)) { throw "UART port $Port is unavailable" }
    $identity = Invoke-F301Ssh "set -eu; test `$(uname -r) = 5.10.260-openmitrastar-radiohw; sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release; grep -q 'mtd4/linux_live' /etc/openmitrastar/release || true"
    if ($identity -notmatch [regex]::Escape($expectedF301Version)) { throw "Installed firmware is not exact F301" }
    Write-Event "f301-readonly-preflight" "PASS"

    $serial = [IO.Ports.SerialPort]::new($Port, 115200, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
    $serial.Handshake = [IO.Ports.Handshake]::None
    $serial.DtrEnable = $false; $serial.RtsEnable = $false
    $serial.ReadTimeout = 100; $serial.WriteTimeout = 1000
    $serial.Open(); $serial.DiscardInBuffer()
    Write-Event "uart-open" "PASS"
    $plan.hardware_preflight = "PASS"
    $plan.execute_allowed_now = $true
    $plan.hardware_actions_performed = $true
    Write-AtomicJson (Join-Path $OutputDir "plan.json") $plan

    $phase = "reboot-to-bootbase"
    Invoke-F301Ssh "sync; reboot -d 2 >/dev/null 2>&1 &" | Out-Null
    Acquire-TopazPrompt $PhaseTimeoutSeconds

    $phase = "bootbase-preflight"
    Send-Uart "printenv bootcmd"
    Wait-Uart 'topaz>\s*$' 30 "bootcmd-read" -ClearTail | Out-Null
    if ($tail -notmatch '(?m)^bootcmd=bootselect\s*$') { throw "Bootbase bootcmd is not bootselect" }
    Send-Uart "printenv bootselect"
    Wait-Uart 'topaz>\s*$' 30 "bootselect-read" -ClearTail | Out-Null
    if ($tail -notmatch '(?m)^bootselect=0\s*$') { throw "Bootbase is not pinned to persistent live slot" }

    Send-Uart "spi_flash read 0x00040000 0x83000000 0x007a0000"
    Wait-Uart 'topaz>\s*$' 120 "mtd3-read-to-ram" -ClearTail | Out-Null
    if ($tail -notmatch 'ret_size=7995392') { throw "mtd3 read size mismatch" }
    Send-Uart "iminfo 0x83000000"
    Wait-Uart 'topaz>\s*$' 60 "mtd3-iminfo" -ClearTail | Out-Null
    if ($tail -notmatch 'Verifying Checksum\s+\.\.\.\s+OK') { throw "mtd3 image checksum failed" }
    Send-Uart 'setenv bootargs ${bootargs} init=/bin/sh'
    Wait-Uart 'topaz>\s*$' 30 "transient-init-override" -ClearTail | Out-Null
    Send-Uart "bootm 0x83000000"
    Wait-Uart 'Linux version 2\.6\.35\.12' $PhaseTimeoutSeconds "oem-kernel" -ClearTail | Out-Null
    Start-Sleep -Seconds 3
    Send-Uart "`r" -NoRecord
    Wait-Uart '#\s*$' 90 "oem-minimal-shell" | Out-Null

    $phase = "oem-readonly-setup"
    Invoke-OemCommand "MINIMAL_SETUP" "export PATH=/bin:/sbin:/usr/bin:/usr/sbin:/scripts:/usr/local/bin; export LD_LIBRARY_PATH=/lib:/usr/lib; mount -t proc proc /proc 2>/dev/null || true; mount -t sysfs sysfs /sys 2>/dev/null || true; mount -t tmpfs tmpfs /tmp; mount -t tmpfs tmpfs /var; mount -t tmpfs tmpfs /mnt/jffs2; mount -t tmpfs tmpfs /mnt/ccc; mount -o remount,ro /; test -r /proc/mtd; ! grep -E '[[:space:]](jffs2|mini_fo)[[:space:]]' /proc/mounts"
    Invoke-OemCommand "MTD_HASH_BEFORE" 'for n in 0 1 2 3 4 5; do h=$(md5sum /dev/mtdblock$n | cut -d" " -f1); echo OMRADAR_MTD_BEFORE_mtd$n=$h; done' 180

    $phase = "radar-start"
    Invoke-OemCommand "MODULES" "modprobe bootcfg; modprobe qtn_debug; modprobe qtsens; modprobe pm_interval; modprobe wlan; modprobe fwt_if; modprobe fwt_ctrl; modprobe auc_fw; modprobe radar; modprobe qdrv tqe_sem_en=1"
    Invoke-OemCommand "QDRV_START" "cp /scripts/dc_iq.cal /tmp/ >/dev/null; cp /scripts/txpower.cal /tmp/ >/dev/null; echo 'set aucfw auc_driver.default.0.bin' > /sys/devices/qdrv/control; echo 'set mucfw qtn_driver.qtn_ruby.0.bin' > /sys/devices/qdrv/control; echo 'set dspfw rdsp_driver.0.bin' > /sys/devices/qdrv/control; echo clearsram > /sys/devices/qdrv/control; echo start > /sys/devices/qdrv/control; sleep 8; test -r /proc/radar; test -d /sys/class/net/wifi0; ifconfig wifi0 down; echo OMRADAR_STAGE_START_READY"

    $phase = "bandwidth"
    Invoke-OemCommand "BANDWIDTH" ("iwpriv wifi0 radar_bw {0}; echo OMRADAR_STAGE_BW_{0}_READY" -f [int]$oracleCommands.bandwidth_mhz)
    $phase = "channel"
    Invoke-OemCommand "CHANNEL" ("ifconfig wifi0 down; iwconfig wifi0 channel {0}; echo OMRADAR_STAGE_CHANNEL_{0}_READY" -f [int]$oracleCommands.channel)
    $phase = "enable"
    Invoke-OemCommand "ENABLE" "echo enable:1 > /proc/radar; echo OMRADAR_STAGE_ENABLE_READY"
    Invoke-OemCommand "STATUS_BEFORE" "grep -E '^(th1|th2|dsample|poll|enable|detect_cnt|max_cnt|max_cntlsr|max_cntfh|max_rate|max_radar_rate)' /proc/radar | sed 's/^/OMRADAR_PROC_BEFORE_/'"

    $phase = "poll-detection"
    foreach ($command in @($oracleCommands.commands)) {
        $name = if ($command -match 'tstart') { "VECTOR_START" } elseif ($command -match 'tend') { "VECTOR_END" } else { "VECTOR_DATA" }
        Invoke-OemCommand $name ([string]$command)
    }
    Start-Sleep -Seconds $PollSeconds
    Invoke-OemCommand "STATUS_AFTER" "grep -E '^(th1|th2|dsample|poll|enable|detect_cnt|max_cnt|max_cntlsr|max_cntfh|max_rate|max_radar_rate)' /proc/radar | sed 's/^/OMRADAR_PROC_AFTER_/'"
    Invoke-OemCommand "DETECTION_LOG" "dmesg | grep -E 'radar|Radar|DFS|CAC|CSA' | tail -n 80 | sed 's/^/OMRADAR_DMESG_/'"

    $phase = "disable"
    Invoke-OemCommand "DISABLE" "echo enable:0 > /proc/radar; ifconfig wifi0 down; echo OMRADAR_STAGE_DISABLE_READY"
    Invoke-OemCommand "MTD_HASH_AFTER" 'for n in 0 1 2 3 4 5; do h=$(md5sum /dev/mtdblock$n | cut -d" " -f1); echo OMRADAR_MTD_AFTER_mtd$n=$h; done' 180

    $safeText = Get-Content -Raw -LiteralPath $sanitizedUartPath
    foreach ($match in [regex]::Matches($safeText, 'OMRADAR_MTD_BEFORE_(mtd[0-5])=([0-9a-f]{32})')) { $mtdBefore[$match.Groups[1].Value] = $match.Groups[2].Value }
    foreach ($match in [regex]::Matches($safeText, 'OMRADAR_MTD_AFTER_(mtd[0-5])=([0-9a-f]{32})')) { $mtdAfter[$match.Groups[1].Value] = $match.Groups[2].Value }
    if ($mtdBefore.Count -ne 6 -or $mtdAfter.Count -ne 6) { throw "Complete physical MTD hash set was not captured" }
    foreach ($name in @("mtd0", "mtd1", "mtd2", "mtd3", "mtd4", "mtd5")) {
        if ($mtdBefore[$name] -ne $mtdAfter[$name]) { throw "Physical partition changed during oracle capture: $name" }
    }

    $phase = "return-to-f301"
    Send-Uart "reboot -f"
    Wait-Uart 'Linux version 5\.10\.260-openmitrastar-radiohw' 300 "f301-kernel-return" -ClearTail | Out-Null
    $returnedVersion = Wait-F301Ssh 420
    Write-Event "f301-return" "PASS" ([ordered]@{ version = $returnedVersion })

    $null = $rawHasher.TransformFinalBlock([byte[]]::new(0), 0, 0)
    $rawFinalized = $true
    $rawStreamHash = ([BitConverter]::ToString($rawHasher.Hash)).Replace("-", "").ToLowerInvariant()
    $result = [ordered]@{
        schema = "openmitrastar.f303-radar-oracle-result/v1"
        status = "PASS"
        target = $device
        start_image = "F301/mtd4"
        temporary_image = "OEM/mtd3 read-to-RAM"
        final_image = "F301/mtd4"
        oracle_vector = $oracleCommands.vector_name
        region = "eu"
        channel = [int]$oracleCommands.channel
        bandwidth_mhz = [int]$oracleCommands.bandwidth_mhz
        pulse_count = [int]$oracleCommands.pulse_count
        mtd_hashes_unchanged = $true
        mtd_before_md5 = $mtdBefore
        mtd_after_md5 = $mtdAfter
        raw_uart_sha256 = $rawStreamHash
        raw_uart_retained = $false
        sanitized_uart_log = $sanitizedUartPath
        calibration_retained = $false
        credentials_retained = $false
        flash_writes = 0
        environment_writes = 0
        recovery = [ordered]@{ needed = $false }
    }
    Write-AtomicJson $resultPath $result
    & python $evidenceTool manifest --directory $OutputDir --output (Join-Path $OutputDir "evidence-sha256.json") | Out-Null
    Write-Output "OMF303_RADAR_ORACLE_PASS=1 result=$resultPath"
} catch {
    $failure = $_.Exception.Message
    Write-Event "capture-failure" "FAIL" ([ordered]@{ error = $failure })
    $recovery = Attempt-Recovery
    if (-not $rawFinalized) {
        $null = $rawHasher.TransformFinalBlock([byte[]]::new(0), 0, 0)
        $rawFinalized = $true
    }
    $rawStreamHash = ([BitConverter]::ToString($rawHasher.Hash)).Replace("-", "").ToLowerInvariant()
    Write-AtomicJson $resultPath ([ordered]@{
        schema = "openmitrastar.f303-radar-oracle-result/v1"
        status = "FAIL"
        failed_phase = $phase
        error = $failure
        recovery = $recovery
        final_image = if ($recovery.f301_restored) { "F301/mtd4" } else { "UNCONFIRMED" }
        raw_uart_sha256 = $rawStreamHash
        raw_uart_retained = $false
        sanitized_uart_log = $sanitizedUartPath
        flash_writes = 0
        environment_writes = 0
    })
    & python $evidenceTool manifest --directory $OutputDir --output (Join-Path $OutputDir "evidence-sha256.json") | Out-Null
    throw "F303 radar oracle failed at $phase; recovery restored=$($recovery.f301_restored): $failure"
} finally {
    if ($lineBuffer) { Add-SanitizedLine $lineBuffer }
    if ($null -ne $serial) {
        if ($serial.IsOpen) { $serial.Close() }
        $serial.Dispose()
    }
    $rawHasher.Dispose()
    if ($lockAcquired) { Release-SharedLock }
}
