[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$ExpectedPnpDeviceId = "FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000",
    [string]$RouterHost = "192.168.1.90",
    [string]$TftpHost = "192.168.1.43",
    [object]$BorrowedHardwareGuard = $null,
    [object]$RecoveryBindingProof = $null,
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
$build = Join-Path $deviceRoot "firmware\f314-device-bound"
$base = "openmitrastar-linux510-f314-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
$candidate = Join-Path $build ($base + ".webformat.bin")
$manifestPath = Join-Path $build "manifest.json"
$requiredAck = "OPENMITRASTAR_F319_ROLLBACK_TO_F314_A0C7350A"
$expectedSha256 = "a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11"
$expectedBytes = 5292032
$expectedFullSlotCrc32 = "d6b13baa"
$expectedFullSlotSha256 = "bc06db537f4eb20ae2b2c64c47262f44c678b1f46a035d2229a768aa36732989"
$currentF319FullSlotCrc32 = "22d3802a"
$currentF319FullSlotSha256 = "ad8bd328147e9fb03715b258bb99c69bbf0daa3b9c6a4dc993c0365ef7665601"
$expectedVersion = "lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device"
$currentVersion = "lyoko-foundation-6.8.3-f319-spi-owner-claim-device"
$currentKnownHosts = Join-Path $deviceRoot "firmware\f319-device-bound\known_hosts.f319"
$sharedLockDir = Join-Path $root "outputs\locks\f301-physical-radio.lock"

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    try {
        $sha = [Security.Cryptography.SHA256]::Create()
        try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "").ToLowerInvariant() }
        finally { $sha.Dispose() }
    } finally { $stream.Dispose() }
}

function Test-LocalIPv4([string]$Address) {
    return [bool](Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -eq $Address } | Select-Object -First 1)
}

foreach ($path in @($manifestPath, $candidate)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing F314 rollback artifact: $path" }
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$checks = [ordered]@{
    schema = $manifest.schema -eq "openmitrastar.f314-qtn-nondfs-guard-candidate/v1"
    candidate_hash = (Get-Sha256 $candidate) -eq $expectedSha256
    candidate_bytes = (Get-Item -LiteralPath $candidate).Length -eq $expectedBytes
    full_slot_crc32 = $manifest.artifacts.full_slot.crc32 -eq $expectedFullSlotCrc32
    full_slot_sha256 = $manifest.artifacts.full_slot.sha256 -eq $expectedFullSlotSha256
    uart_guard_present = Test-Path -LiteralPath (Join-Path $root "tools\f319_uart_guard.ps1") -PathType Leaf
    current_known_hosts_present = Test-Path -LiteralPath $currentKnownHosts -PathType Leaf
}
$localPass = @($checks.Values | Where-Object { $_ -ne $true }).Count -eq 0
[ordered]@{
    schema = "openmitrastar.f319-to-f314-rollback-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    target = "mtd4/linux_live"
    rollback_candidate = $candidate
    rollback_sha256 = $expectedSha256
    expected_current_f319 = [ordered]@{full_slot_crc32=$currentF319FullSlotCrc32;full_slot_sha256=$currentF319FullSlotSha256}
    local_checks = $checks
    local_preflight_pass = $localPass
    required_ack = $requiredAck
    uart_pnp_device_id = $ExpectedPnpDeviceId
    physical_lock = $sharedLockDir
    uart_binding = "pinned PnP plus authenticated HGW console nonce before reboot"
    hardware_actions_performed = $false
} | ConvertTo-Json -Depth 6
if (-not $Execute) { exit $(if ($localPass) { 0 } else { 1 }) }

if ($Ack -ne $requiredAck) { throw "Refusing rollback: exact -Ack is required" }
if (-not $localPass) { throw "F314 rollback artifact contract mismatch" }
if ($Transport -ne 'uart-ymodem' -and -not (Test-LocalIPv4 $TftpHost)) { throw "TFTP host address $TftpHost is not local" }
if (($null -eq $BorrowedHardwareGuard) -ne ($null -eq $RecoveryBindingProof)) { throw 'Incomplete borrowed recovery guard' }
if ($BorrowedHardwareGuard) {
    if (-not $RecoveryRehearsalResultPath) { throw 'Borrowed recovery requires a verified Bootbase rehearsal' }
    [void](Get-F319VerifiedRecoveryRehearsal -ResultPath $RecoveryRehearsalResultPath)
    [void](Assert-F319BorrowedRecoveryGuard -Guard $BorrowedHardwareGuard -BindingProof $RecoveryBindingProof -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId)
}

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
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $currentF319FullSlotCrc32
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = $currentF319FullSlotSha256

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$runDir = Join-Path $root "outputs\recovery\f319-to-f314-$stamp"
New-Item -ItemType Directory -Path $runDir | Out-Null
$runner = Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py"
$common = @("--execute", "--ack", $requiredAck, "--port", $Port, "--client-ip", $RouterHost, "--host", $RouterHost, "--skip-reboot", "--timeout", "$FlashTimeoutSeconds", "--erase-bytes", "0x5e0000")

$guard = $null
try {
    if ($BorrowedHardwareGuard) {
        # No cached JSON/standalone SSH bypass: same PID, still-held lease and
        # original authenticated physical binding from the live promoter.
        [void](Assert-F319BorrowedRecoveryGuard -Guard $BorrowedHardwareGuard -BindingProof $RecoveryBindingProof -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId)
        [void](Get-F319SerialDevice -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId)
    } else {
        $guard = Enter-F319HardwareGuard -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId -PhysicalLockDir $sharedLockDir -Owner "f319-rollback-to-f314" -EvidenceDir $runDir
        [void](Assert-F319UartBinding -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId -RouterHost $RouterHost -KnownHosts $currentKnownHosts -ExpectedVersion $currentVersion -HardwareLease $guard)
    }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\reboot_to_topaz_prompt_sysrq.ps1") -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId -LogPath (Join-Path $runDir "uart-to-topaz.log") -TimeoutSeconds 240
    if ($LASTEXITCODE -ne 0) { throw "Could not acquire Topaz prompt for F314 rollback" }

    $restored = $false
    if ($Transport -in @("auto", "tftp")) {
        $tftpAttemptId = [Guid]::NewGuid().ToString('N')
        $tftpAttemptDir = Join-Path $runDir 'tftp-attempt'
        & python $runner @common --transport tftp --server-ip $TftpHost --uart-attach-topaz --evidence-dir $tftpAttemptDir --attempt-id $tftpAttemptId
        if ($LASTEXITCODE -eq 0) { $restored = $true }
        if (-not $restored -and $Transport -eq "tftp") { throw "F314 rollback TFTP failed" }
        if (-not $restored) {
            & python (Join-Path $root 'tools\f319_flash_fallback.py') --verify $tftpAttemptDir --attempt-id $tftpAttemptId --candidate-sha256 $expectedSha256 --current-live-crc32 $currentF319FullSlotCrc32
            if ($LASTEXITCODE -ne 0) { throw 'F314 automatic YMODEM fallback refused: pre-erase TFTP failure is not proven' }
        }
    }
    if (-not $restored) {
        & python $runner @common --transport uart-ymodem --uart-attach-topaz
        if ($LASTEXITCODE -ne 0) { throw "F314 rollback UART/YMODEM failed" }
    }

    $postflash = Join-Path $root "outputs\postflash\f314-restored-from-f319-$stamp"
    & python (Join-Path $root "tools\post_flash_f214_device_gate.py") --host $RouterHost --wait-seconds 360 --output-dir $postflash --device-dir $build --expected-version $expectedVersion --known-hosts-name known_hosts.f314
    if ($LASTEXITCODE -ne 0) { throw "F314 rollback platform gate failed: $postflash" }
    Write-Output "OMF319_ROLLBACK_TO_F314_PASS=1 output=$runDir"
} finally {
    Exit-F319HardwareGuard -Guard $guard
}
