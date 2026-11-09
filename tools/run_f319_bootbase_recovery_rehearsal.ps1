[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = '',
    [string]$OutputDir = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $root 'tools/f319_uart_guard.ps1')
$requiredAck = 'OPENMITRASTAR_F319_F314_RECOVERY_REHEARSAL_A0C7350A'
$build = Join-Path $env:USERPROFILE '.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f314-device-bound'
$stem = 'openmitrastar-linux510-f314-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
$candidate = Join-Path $build ($stem + '.webformat.bin')
$expectedSha = 'a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11'
$fullSlotSha = 'bc06db537f4eb20ae2b2c64c47262f44c678b1f46a035d2229a768aa36732989'
$version = 'lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device'
$pnp = 'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000'
$knownHosts = Join-Path $build 'known_hosts.f314'
$runner = Join-Path $root 'tools/run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py'
function Get-RehearsalSha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    try {
        $hash = [Security.Cryptography.SHA256]::Create()
        try { return ([BitConverter]::ToString($hash.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
        finally { $hash.Dispose() }
    } finally { $stream.Dispose() }
}
$guardEvidence = Get-ChildItem -Path (Join-Path $root 'outputs/preflight/f319-offline-guards-*/result.json') | Sort-Object LastWriteTimeUtc | Select-Object -Last 1
if (-not $guardEvidence) { throw 'Missing offline guard evidence' }
$verified = Get-Content -LiteralPath $guardEvidence.FullName -Raw | ConvertFrom-Json
if ($verified.status -ne 'PASS') { throw 'Offline guard evidence failed' }
foreach ($entry in $verified.sources.PSObject.Properties) {
    if ((Get-RehearsalSha256 (Join-Path $root ('tools/' + $entry.Name))) -ne $entry.Value) {
        throw ('Stale offline source proof: ' + $entry.Name)
    }
}

# This process-local configuration pins the unmodified, existing writer to F314.
$env:OM_Q3_FLASH_ACK = $requiredAck
$env:OM_Q3_FLASH_BUILD_DIR = $build
$env:OM_Q3_FLASH_CANDIDATE = $candidate
$env:OM_Q3_FLASH_BOOTBASE_CONTRACT = Join-Path $build 'bootbase-contract.json'
$env:OM_Q3_FLASH_MANIFEST = Join-Path $build 'manifest.json'
$env:OM_Q3_FLASH_INITRAMFS = Join-Path $build ($stem + '.kernel.raw.bin')
$env:OM_Q3_FLASH_KCONFIG = Join-Path $build ($stem + '.config')
$env:OM_Q3_FLASH_LAYOUT_MODE = 'squashfs-split'
$env:OM_Q3_FLASH_ROOTFS_IMAGE = Join-Path $build ($stem + '.rootfs.squashfs')
$env:OM_Q3_FLASH_DTB = Join-Path $build ($stem + '.dtb')
$env:OM_Q3_FLASH_ROOTFS_OFFSET = '0x180000'
$env:OM_Q3_FLASH_EXPECTED_SHA256 = $expectedSha
$env:OM_Q3_FLASH_EXPECTED_BYTES = '5292032'
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = 'd6b13baa'
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = $fullSlotSha
$env:OM_Q3_FLASH_POWERSHELL_BACKEND = Join-Path $root 'tools/q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_bootbase_flash.ps1'
$common = @('--transport', 'uart-ymodem', '--skip-reboot', '--uart-attach-topaz', '--timeout', '1800', '--erase-bytes', '0x5e0000')
$dry = @(& python $runner @common)
if ($LASTEXITCODE -ne 0) { throw 'F314 exact artifact/backup/Bootbase preflight failed' }
$local = (($dry | Where-Object { $_ -notmatch '^OMQ3_' }) -join "`n") | ConvertFrom-Json
if ($local.mode -ne 'dry-run' -or $local.candidate_sha256 -ne $expectedSha -or
    $local.current_live_sha256 -ne $fullSlotSha -or $local.expected_full_slot_sha256 -ne $fullSlotSha -or
    $local.expected_full_slot_crc32 -ne 'd6b13baa' -or $local.candidate_bytes -ne 5292032 -or
    $local.physical_write.partition -ne 'mtd4/linux_live') { throw 'F314 rehearsal contract mismatch' }
$plan = [ordered]@{
    schema = 'openmitrastar.f319-bootbase-recovery-rehearsal/v1'
    mode = if ($Execute) { 'execute' } else { 'dry-run' }
    target = 'HGW-500BNA-QCv2 A2 / 192.168.1.90'
    candidate = $candidate
    candidate_sha256 = $expectedSha
    candidate_bytes = 5292032
    physical_target = 'mtd4/linux_live @ 0x007e0000, slot 0x007a0000'
    current_and_restored_full_slot_crc32 = 'd6b13baa'
    local_preflight_pass = $true
    uart_guard_evidence = $guardEvidence.FullName
    transport = 'UART/YMODEM; no TFTP service'
    bootenv_write = $false
    protected_partitions = 'mtd0/mtd1/mtd2/mtd3/mtd5 unchanged'
    ssh_usage = 'initial authenticated identity and final acceptance only; restoration in Bootbase'
    safety_slot_recovery_claimed = $false
    hardware_actions_performed = $false
    required_ack = $requiredAck
}
if (-not $Execute) { $plan | ConvertTo-Json -Depth 6; exit 0 }
if ($Ack -ne $requiredAck) { throw 'Exact F314 rehearsal acknowledgement required' }
if (-not $OutputDir) { throw 'Execute requires a new explicit evidence directory' }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $OutputDir) { throw 'Evidence directory already exists' }
New-Item -ItemType Directory -Path $OutputDir | Out-Null

function Write-NewJson([string]$Path, [object]$Value) {
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($Value | ConvertTo-Json -Depth 12) + "`n")
        $stream.Write($bytes, 0, $bytes.Length)
    } finally { $stream.Dispose() }
}
Write-NewJson (Join-Path $OutputDir 'plan.json') $plan
Write-NewJson (Join-Path $OutputDir 'local-preflight.json') $local
$report = [ordered]@{
    schema = 'openmitrastar.f319-bootbase-recovery-rehearsal-result/v1'
    started_utc = [DateTime]::UtcNow.ToString('o')
    status = 'FAIL'
    phase = 'initial-identity'
    binding = $null
    f314_sha256 = $expectedSha
    full_slot_crc32 = 'd6b13baa'
    restore_ssh_dependency = $false
    protected_partitions_written = $false
    flash_attempted = $false
    safety_slot_boot_proven = $false
    initial_slot = 'exact F314 (not a simulated corrupt slot)'
    limits = 'Does not prove SysRq when the kernel is completely locked, or recovery after partial flash failure'
    error = $null
}
$guard = $null
try {
    $sshArgs = @('-i', (Join-Path $env:USERPROFILE '.ssh/id_ed25519'), '-o', 'IdentitiesOnly=yes',
        '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', '-o', 'StrictHostKeyChecking=yes',
        '-o', ('UserKnownHostsFile=' + $knownHosts), '-o', 'LogLevel=ERROR', 'root@192.168.1.90', 'sh', '-s')
    $baselineScript = @'
set -e
grep -qx 'OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device' /etc/openmitrastar/release
test "$(cat /run/openmitrastar/boot-state)" = ready
test "$(cat /run/openmitrastar/radio5g/state)" = ready
/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status | grep -qx 'state=ENABLED'
test "$(uname -r)" = 5.10.260-openmitrastar-radiohw
fatal=$(dmesg | grep -Eic 'MuC:.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|VFS: Unable to mount root' || true)
test "$fatal" = 0
echo OMF319_F314_BASELINE_PASS
'@
    $baseline = Invoke-F319SshScript -SshPath (Join-Path $env:WINDIR 'System32/OpenSSH/ssh.exe') -Arguments $sshArgs -Script $baselineScript -TimeoutSeconds 25
    if ($baseline.ExitCode -ne 0 -or $baseline.Stdout -notmatch '(?m)^OMF319_F314_BASELINE_PASS\r?$') { throw 'F314 baseline failed before UART acquisition' }
    $report.initial_baseline = 'F314, Linux 5.10.260, boot ready, both radios ready, fatal count zero'
    $guard = Enter-F319HardwareGuard -Port COM3 -ExpectedPnpDeviceId $pnp -PhysicalLockDir (Join-Path $root 'outputs/locks/f301-physical-radio.lock') -Owner 'f319-f314-recovery-rehearsal' -EvidenceDir $OutputDir
    $report.binding = Assert-F319UartBinding -Port COM3 -ExpectedPnpDeviceId $pnp -RouterHost '192.168.1.90' -KnownHosts $knownHosts -ExpectedVersion $version -HardwareLease $guard
    Write-Output 'OMF319_RECOVERY_STAGE=IDENTITY_AND_LIVE_GUARD_PASS'
    $report.phase = 'uart-reboot-to-bootbase'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'tools/reboot_to_topaz_prompt_sysrq.ps1') -Port COM3 -ExpectedPnpDeviceId $pnp -LogPath (Join-Path $OutputDir 'uart-to-topaz.log') -TimeoutSeconds 180 *> (Join-Path $OutputDir 'uart-entry.console.log')
    if ($LASTEXITCODE -ne 0) { throw 'Could not acquire Bootbase; no flash writer invoked' }
    [void](Assert-F319HardwareLease -PhysicalLockDir $guard.PhysicalLockDir -OwnerPid $guard.OwnerPid -OwnerStartTicks $guard.OwnerStartTicks -LeaseToken $guard.LeaseToken -Port COM3 -ExpectedPnpDeviceId $pnp)
    [void](Get-F319SerialDevice -Port COM3 -ExpectedPnpDeviceId $pnp)
    Write-Output 'OMF319_RECOVERY_STAGE=BOOTBASE_READY_SSH_NOT_REQUIRED'
    $report.phase = 'f314-uart-transfer-and-guarded-restore'
    $report.flash_attempted = $true
    $attemptDir = Join-Path $OutputDir 'f314-restore'
    $attemptId = [Guid]::NewGuid().ToString('N')
    & python $runner @common --execute --ack $requiredAck --evidence-dir $attemptDir --attempt-id $attemptId
    if ($LASTEXITCODE -ne 0) { throw 'F314 restore failed; do not retry or assume a bootable current slot' }
    $report.phase = 'f314-platform-acceptance'
    $post = Join-Path $OutputDir 'postflash-f314'
    & python (Join-Path $root 'tools/post_flash_f214_device_gate.py') --host 192.168.1.90 --wait-seconds 180 --output-dir $post --device-dir $build --expected-version $version --known-hosts-name known_hosts.f314
    if ($LASTEXITCODE -ne 0) { throw 'F314 restored but platform gate failed' }
    $report.final_binding = Assert-F319UartBinding -Port COM3 -ExpectedPnpDeviceId $pnp -RouterHost '192.168.1.90' -KnownHosts $knownHosts -ExpectedVersion $version -HardwareLease $guard
    $report.restore_result = Join-Path $attemptDir 'result.json'
    $report.platform_result = Join-Path $post 'status.json'
    $report.phase = 'complete'
    $report.status = 'PASS_F314_RESTORE_WITHOUT_SSH_IN_BOOTBASE'
} catch {
    $report.error = $_.Exception.Message
} finally {
    try { Exit-F319HardwareGuard -Guard $guard } catch { $report.status = 'FAIL'; $report.error = $_.Exception.Message }
    $report.finished_utc = [DateTime]::UtcNow.ToString('o')
    Write-NewJson (Join-Path $OutputDir 'result.json') $report
    $report | ConvertTo-Json -Depth 8
}
if ($report.status -ne 'PASS_F314_RESTORE_WITHOUT_SSH_IN_BOOTBASE') { exit 1 }
