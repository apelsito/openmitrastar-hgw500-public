[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$ExpectedPnpDeviceId = "FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000",
    [string]$RouterHost = "192.168.1.90",
    [string]$TftpHost = "192.168.1.43",
    [string]$RecoveryRehearsalResultPath = '',
    [ValidateSet("auto", "tftp", "uart-ymodem")][string]$Transport = "auto",
    [ValidateRange(600, 1800)][int]$FlashTimeoutSeconds = 1800
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
. (Join-Path $root "tools\f319_uart_guard.ps1")
. (Join-Path $root 'tools\f319_recovery_guard.ps1')
$deviceRoot = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary"
$build = Join-Path $deviceRoot "firmware\f319-device-bound"
$base = "openmitrastar-linux510-f319-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
$candidate = Join-Path $build ($base + ".webformat.bin")
$manifestPath = Join-Path $build "manifest.json"
$requiredAck = "OPENMITRASTAR_F319_MTD4_E33D8511"
$probeAck = "OPENMITRASTAR_F319_SPI_OWNER_CLAIM_E33D8511"
$expectedSha256 = "e33d851106aa342509184ab0d1d94fc0654d7206cb2a4c62c5fab7aa48c0dcc9"
$expectedBytes = 5292032
$expectedFullSlotCrc32 = "22d3802a"
$expectedFullSlotSha256 = "ad8bd328147e9fb03715b258bb99c69bbf0daa3b9c6a4dc993c0365ef7665601"
$currentF314FullSlotCrc32 = "d6b13baa"
$currentF314FullSlotSha256 = "bc06db537f4eb20ae2b2c64c47262f44c678b1f46a035d2229a768aa36732989"
$expectedVersion = "lyoko-foundation-6.8.3-f319-spi-owner-claim-device"
$currentVersion = "lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device"
$currentKnownHosts = Join-Path $deviceRoot "firmware\f314-device-bound\known_hosts.f314"
$f319KnownHosts = Join-Path $build "known_hosts.f319"
$sharedLockDir = Join-Path $root "outputs\locks\f301-physical-radio.lock"

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    try {
        $sha = [Security.Cryptography.SHA256]::Create()
        try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "").ToLowerInvariant() }
        finally { $sha.Dispose() }
    } finally { $stream.Dispose() }
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

function Test-LocalIPv4([string]$Address) {
    return [bool](Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -eq $Address } | Select-Object -First 1)
}

foreach ($path in @($manifestPath, $candidate)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing F319 artifact: $path" }
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$checks = [ordered]@{
    schema = $manifest.schema -eq "openmitrastar.f319-spi-owner-claim-candidate/v1"
    candidate_eligible = $manifest.candidate_eligible -eq $true
    flash_supported = $manifest.flash_supported -eq $true
    candidate_hash = (Get-Sha256 $candidate) -eq $expectedSha256
    candidate_bytes = (Get-Item -LiteralPath $candidate).Length -eq $expectedBytes
    full_slot_crc32 = $manifest.artifacts.full_slot.crc32 -eq $expectedFullSlotCrc32
    full_slot_sha256 = $manifest.artifacts.full_slot.sha256 -eq $expectedFullSlotSha256
    target_mtd4_only = $manifest.safety.normal_write_target -like "mtd4/linux_live*"
    protected_partitions = $manifest.safety.protected_partitions -eq "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged"
    module_autoload_disabled = $manifest.spi_owner_probe.autoload -eq $false
    module_mmio_zero = $manifest.spi_owner_probe.mmio_reads -eq 0 -and $manifest.spi_owner_probe.mmio_writes -eq 0
    uart_guard_present = Test-Path -LiteralPath (Join-Path $root "tools\f319_uart_guard.ps1") -PathType Leaf
    current_known_hosts_present = Test-Path -LiteralPath $currentKnownHosts -PathType Leaf
    f319_known_hosts_present = Test-Path -LiteralPath $f319KnownHosts -PathType Leaf
}
$localPass = @($checks.Values | Where-Object { $_ -ne $true }).Count -eq 0
$plan = [ordered]@{
    schema = "openmitrastar.f319-direct-promotion-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    target_model = "HGW-500BNA-QCv2 A2"
    target_host = $RouterHost
    write_target = "mtd4/linux_live"
    offset = "0x007e0000"
    slot_bytes = "0x007a0000"
    erase_bytes = "0x005e0000"
    candidate = $candidate
    candidate_bytes = $expectedBytes
    candidate_sha256 = $expectedSha256
    full_slot_crc32 = $expectedFullSlotCrc32
    full_slot_sha256 = $expectedFullSlotSha256
    expected_current = [ordered]@{version="lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device";full_slot_crc32=$currentF314FullSlotCrc32;full_slot_sha256=$currentF314FullSlotSha256}
    rollback = [ordered]@{primary="exact F314 mtd4 image";independent="verified Bootbase F314 restoration, not linux_safety";rehearsal_required=$true;rehearsal_result=$RecoveryRehearsalResultPath;automatic_after_completed_flash_failure=$true}
    postflash_gate = "tools/post_flash_f214_device_gate.py"
    runtime_probe = "tools/run_f319_spi_owner_probe.ps1"
    local_checks = $checks
    local_preflight_pass = $localPass
    required_ack = $requiredAck
    uart_pnp_device_id = $ExpectedPnpDeviceId
    physical_lock = $sharedLockDir
    uart_binding = "pinned PnP plus authenticated HGW console nonce before reboot"
    hardware_actions_performed = $false
}
$plan | ConvertTo-Json -Depth 8
if (-not $Execute) { exit $(if ($localPass) { 0 } else { 1 }) }

if ($Ack -ne $requiredAck) { throw "Refusing flash: exact -Ack is required" }
if (-not $localPass) { throw "F319 local artifact contract mismatch" }
if (-not $RecoveryRehearsalResultPath) { throw 'F319 requires a physically verified F314 Bootbase recovery rehearsal' }
$verifiedRecovery = Get-F319VerifiedRecoveryRehearsal -ResultPath $RecoveryRehearsalResultPath
if (-not (Test-Tcp $RouterHost 22)) { throw "Router SSH preflight failed" }
if ($Transport -ne 'uart-ymodem' -and -not (Test-LocalIPv4 $TftpHost)) { throw "TFTP host address $TftpHost is not local" }

$env:OM_Q3_FLASH_ACK = $requiredAck
$env:OM_Q3_FLASH_BUILD_DIR = $build
$env:OM_Q3_FLASH_CANDIDATE = $candidate
$env:OM_Q3_FLASH_BOOTBASE_CONTRACT = Join-Path $build "bootbase-contract.json"
$env:OM_Q3_FLASH_MANIFEST = $manifestPath
$env:OM_Q3_FLASH_INITRAMFS = Join-Path $build ($base + ".kernel.raw.bin")
$env:OM_Q3_FLASH_KCONFIG = Join-Path $build ($base + ".config")
$env:OM_Q3_FLASH_LAYOUT_MODE = "squashfs-split"
$env:OM_Q3_FLASH_ROOTFS_IMAGE = Join-Path $build ($base + ".rootfs.squashfs")
$env:OM_Q3_FLASH_DTB = Join-Path $build ($base + ".dtb")
$env:OM_Q3_FLASH_ROOTFS_OFFSET = "0x180000"
$env:OM_Q3_FLASH_EXPECTED_SHA256 = $expectedSha256
$env:OM_Q3_FLASH_EXPECTED_BYTES = [string]$expectedBytes
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $currentF314FullSlotCrc32
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = $currentF314FullSlotSha256

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$runDir = Join-Path $root "outputs\flash-watch\f319-direct-$stamp"
New-Item -ItemType Directory -Path $runDir | Out-Null
$runner = Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py"
$common = @("--execute", "--ack", $requiredAck, "--port", $Port, "--client-ip", $RouterHost, "--host", $RouterHost, "--skip-reboot", "--timeout", "$FlashTimeoutSeconds", "--erase-bytes", "0x5e0000")

$guard = $null
$bindingProof = $null
$flashed = $false
try {
    $guard = Enter-F319HardwareGuard -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId -PhysicalLockDir $sharedLockDir -Owner "f319-promotion" -EvidenceDir $runDir
    $initialBinding = Assert-F319UartBinding -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId -RouterHost $RouterHost -KnownHosts $currentKnownHosts -ExpectedVersion $currentVersion -HardwareLease $guard
    $bindingProof = [pscustomobject]@{OwnerPid=$guard.OwnerPid;OwnerStartTicks=$guard.OwnerStartTicks;LeaseToken=$guard.LeaseToken;Binding=$initialBinding}

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\reboot_to_topaz_prompt_sysrq.ps1") -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId -LogPath (Join-Path $runDir "uart-to-topaz.log") -TimeoutSeconds 240
    if ($LASTEXITCODE -ne 0) { throw "F319 could not acquire the Topaz prompt" }

    if ($Transport -in @("auto", "tftp")) {
        $tftpAttemptId = [Guid]::NewGuid().ToString('N')
        $tftpAttemptDir = Join-Path $runDir 'tftp-attempt'
        & python $runner @common --transport tftp --server-ip $TftpHost --uart-attach-topaz --evidence-dir $tftpAttemptDir --attempt-id $tftpAttemptId
        if ($LASTEXITCODE -eq 0) { $flashed = $true }
        if (-not $flashed -and $Transport -eq "tftp") { throw "F319 TFTP transport failed" }
        if (-not $flashed) {
            & python (Join-Path $root 'tools\f319_flash_fallback.py') --verify $tftpAttemptDir --attempt-id $tftpAttemptId --candidate-sha256 $expectedSha256 --current-live-crc32 $currentF314FullSlotCrc32
            if ($LASTEXITCODE -ne 0) { throw 'F319 automatic YMODEM fallback refused: pre-erase TFTP failure is not proven' }
        }
    }
    if (-not $flashed) {
        & python $runner @common --transport uart-ymodem --uart-attach-topaz
        if ($LASTEXITCODE -ne 0) { throw "F319 UART/YMODEM transport failed" }
        $flashed = $true
    }

    $postflash = Join-Path $root "outputs\postflash\f319-device-$stamp"
    & python (Join-Path $root "tools\post_flash_f214_device_gate.py") --host $RouterHost --wait-seconds 360 --output-dir $postflash --device-dir $build --expected-version $expectedVersion --known-hosts-name known_hosts.f319
    if ($LASTEXITCODE -ne 0) { throw "F319 platform gate failed: $postflash" }
    [void](Assert-F319UartBinding -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId -RouterHost $RouterHost -KnownHosts $f319KnownHosts -ExpectedVersion $expectedVersion -HardwareLease $guard)

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\run_f319_spi_owner_probe.ps1") -Execute -Ack $probeAck -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId -RouterHost $RouterHost -UartSeconds 60 -ParentHardwareGuardHeld -ParentGuardOwnerPid $guard.OwnerPid -ParentGuardOwnerStartTicks $guard.OwnerStartTicks -ParentGuardToken $guard.LeaseToken
    if ($LASTEXITCODE -ne 0) { throw "F319 SPI owner probe failed; restore exact F314 before further work" }
    Write-Output "OMF319_MTD4_PROMOTION_AND_OWNER_PROBE_PASS=1 output=$runDir"
} catch {
    $promotionError = $_.Exception.Message
    if ($flashed -and $guard -and $bindingProof) {
        # Only after the writer completed its full-slot/readback/boot checks.
        # Partial/ambiguous flash failures are not silently retried.
        Write-Output 'OMF319_AUTOMATIC_F314_RESTORE_START=1 same_live_guard=1'
        try {
            & (Join-Path $root 'tools\rollback_f319_to_f314_mtd4.ps1') -Execute -Ack 'OPENMITRASTAR_F319_ROLLBACK_TO_F314_A0C7350A' -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId -RouterHost $RouterHost -Transport uart-ymodem -BorrowedHardwareGuard $guard -RecoveryBindingProof $bindingProof -RecoveryRehearsalResultPath $verifiedRecovery.ResultPath
            Write-Output 'OMF319_AUTOMATIC_F314_RESTORE_PASS=1'
        } catch {
            throw ('F319 failed: ' + $promotionError + '; automatic F314 recovery failed: ' + $_.Exception.Message)
        }
        throw ('F319 failed and exact F314 was restored: ' + $promotionError)
    }
    throw
} finally {
    Exit-F319HardwareGuard -Guard $guard
}
