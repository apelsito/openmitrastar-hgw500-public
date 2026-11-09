[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [ValidateRange(30, 180)][int]$UartSeconds = 60,
    [string]$OutputDir = "",
    [string]$CampaignStateRoot = "",
    [string]$SharedLockDir = "",
    [switch]$SkipProcessInventory
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$device = "hgw500bna-qcv2-a2-primary"
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\$device\firmware\f301-device-bound"
$manifestPath = Join-Path $build "manifest.json"
$knownHosts = Join-Path $build "known_hosts.f301"
$moduleRelative = "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn-topaz-store-protection-observer.ko"
$moduleRemote = "/$($moduleRelative -replace '\\','/')"
$moduleLocal = Join-Path $root "outputs\kernel-port\f295-store-protection-observer-20260904\qtn-topaz-store-protection-observer.ko"
$moduleManifestPath = Join-Path $root "outputs\kernel-port\f295-store-protection-observer-20260904\manifest.json"
$undefinedSymbolsPath = Join-Path $root "outputs\kernel-port\f295-store-protection-observer-20260904\undefined-symbols.txt"
$sourcePath = Join-Path $root "work\kernel-port\modules\qtn-topaz-store-protection-observer\qtn-topaz-store-protection-observer.c"
$featurePath = Join-Path $root "versions\lyoko-foundation-6.6.1-f301-f300-capability-truth\overlay\etc\openmitrastar\features\store-protection-observer-v1"
$moduleName = "qtn_topaz_store_protection_observer"
$expectedVersion = "lyoko-foundation-6.6.1-f301-f300-capability-truth-device"
$expectedFirmwareSha256 = "4c280e84b4593008b900cec70041b801d204bdde748b09064410708253b87262"
$expectedModuleSha256 = "2f00a2db7103e0eb5691d86ae9122cdb22e34d935d7042339d131d2e55c906f8"
$expectedVermagic = "5.10.260-openmitrastar-radiohw mod_unload ARC700"
$expectedKernel = "5.10.260-openmitrastar-radiohw"
$requiredAck = "OPENMITRASTAR_F301_STORE_PROTECTION_READONLY_2F00A2DB"
$defaultCampaignStateRoot = Join-Path $root "outputs"
$defaultSharedLockDir = Join-Path $root "outputs\locks\f301-physical-radio.lock"

if (-not $CampaignStateRoot) { $CampaignStateRoot = $defaultCampaignStateRoot }
if (-not $SharedLockDir) { $SharedLockDir = $defaultSharedLockDir }
$CampaignStateRoot = [IO.Path]::GetFullPath($CampaignStateRoot)
$SharedLockDir = [IO.Path]::GetFullPath($SharedLockDir)

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    try {
        $sha = [Security.Cryptography.SHA256]::Create()
        try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "").ToLowerInvariant() }
        finally { $sha.Dispose() }
    } finally { $stream.Dispose() }
}

function Write-AtomicJson([string]$Path, [object]$Value) {
    $directory = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $temporary = Join-Path $directory (".{0}.{1}.{2}.tmp" -f ([IO.Path]::GetFileName($Path)), $PID, [DateTime]::UtcNow.Ticks)
    $backup = Join-Path $directory (".{0}.{1}.{2}.bak" -f ([IO.Path]::GetFileName($Path)), $PID, [DateTime]::UtcNow.Ticks)
    try {
        $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $temporary -Encoding ascii
        if (Test-Path -LiteralPath $Path) {
            [IO.File]::Replace($temporary, $Path, $backup)
            Remove-Item -LiteralPath $backup -Force
        } else {
            [IO.File]::Move($temporary, $Path)
        }
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
    }
}

function Get-AsciiString([string]$Path, [string]$Prefix) {
    $text = [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes($Path))
    foreach ($item in ($text -split "`0")) {
        if ($item.StartsWith($Prefix, [StringComparison]::Ordinal)) { return $item }
    }
    return ""
}

function Test-SourceContract([string]$Path) {
    $source = Get-Content -Raw -LiteralPath $Path
    $required = @(
        "SPI_READ_STATUS", "SPI_READ_ID", "SPI_READ_SCUR", "SPI_READ_DPB",
        "SPI_SCUR_READ_OPCODE", "SPI_DPB_READ_OPCODE", "store_dpb_scan_count",
        "read_commands_only = true", "control_restored", "module_param(jedec_id, uint, 0444)",
        "module_param(status_register, uint, 0444)", "module_param(security_register, uint, 0444)"
    )
    $forbidden = @(
        "SPI_WRITE_ENABLE", "SPI_WRITE_DISABLE", "SPI_PAGE_PROGRAM", "SPI_SECTOR_ERASE",
        "SPI_WRITE_DPB", "SPI_GBLOCK", "mtd_device_register", "mtd_device_unregister",
        "add_mtd", "del_mtd", "memcpy_toio", "writeb("
    )
    $missing = @($required | Where-Object { -not $source.Contains($_) })
    $presentForbidden = @($forbidden | Where-Object { $source.Contains($_) })
    $readCallCount = ([regex]::Matches($source, [regex]::Escape("qtn_spi_read_command(ctrl,"))).Count
    return [ordered]@{
        pass = ($missing.Count -eq 0 -and $presentForbidden.Count -eq 0 -and $readCallCount -eq 2)
        missing_required = $missing
        forbidden_present = $presentForbidden
        scur_dpb_read_call_sites = $readCallCount
        write_enable_absent = -not $source.Contains("SPI_WRITE_ENABLE")
        erase_absent = -not $source.Contains("SPI_SECTOR_ERASE")
        program_absent = -not $source.Contains("SPI_PAGE_PROGRAM")
        mtd_registration_absent = (-not $source.Contains("mtd_device_register") -and -not $source.Contains("add_mtd"))
    }
}

function Get-CampaignState([switch]$IgnoreSharedLock) {
    $processes = @()
    $checkpoints = @()
    $errors = @()
    if (-not $SkipProcessInventory) {
        try {
            $processes = @(Get-CimInstance Win32_Process -ErrorAction Stop |
                Where-Object {
                    $_.ProcessId -ne $PID -and $_.CommandLine -and (
                        $_.CommandLine -match 'run_f301_sequential_dual_radio_soak[.]py' -or
                        $_.CommandLine -match 'run_f301_multicast_igmp_physical[.]py'
                    )
                } |
                ForEach-Object {
                    [ordered]@{ pid = [int]$_.ProcessId; name = [string]$_.Name; kind = if ($_.CommandLine -match 'multicast') { "multicast" } else { "soak" } }
                })
        } catch { $errors += "process_inventory: $($_.Exception.Message)" }
    }

    $soakRoot = Join-Path $CampaignStateRoot "soak"
    if (Test-Path -LiteralPath $soakRoot) {
        foreach ($path in @(Get-ChildItem -LiteralPath $soakRoot -Recurse -Filter "checkpoint.json" -File -ErrorAction SilentlyContinue)) {
            try {
                $payload = Get-Content -Raw -LiteralPath $path.FullName | ConvertFrom-Json
                if ($payload.status -eq "IN_PROGRESS" -and [string]$payload.schema -like "openmitrastar.f301-sequential-dual-radio-soak-checkpoint/*") {
                    $checkpoints += [ordered]@{
                        path = $path.FullName
                        status = "IN_PROGRESS"
                        updated_at = [string]$payload.updated_at
                        cycles_completed = [int]$payload.cycles_completed
                    }
                }
            } catch { $errors += "checkpoint:$($path.FullName): $($_.Exception.Message)" }
        }
    }

    $sharedLockPresent = $false
    $sharedLockOwner = $null
    if (-not $IgnoreSharedLock -and (Test-Path -LiteralPath $SharedLockDir)) {
        $sharedLockPresent = $true
        $ownerPath = Join-Path $SharedLockDir "owner.json"
        try { $sharedLockOwner = Get-Content -Raw -LiteralPath $ownerPath | ConvertFrom-Json }
        catch { $errors += "shared_lock_owner: $($_.Exception.Message)" }
    }
    $active = ($processes.Count -gt 0 -or $checkpoints.Count -gt 0 -or $sharedLockPresent -or $errors.Count -gt 0)
    return [ordered]@{
        active = $active
        processes = $processes
        in_progress_checkpoints = $checkpoints
        shared_lock_present = $sharedLockPresent
        shared_lock_owner = $sharedLockOwner
        detection_errors = $errors
        fail_closed = $true
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

function Acquire-SharedLock([string]$EvidenceDir) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $SharedLockDir) | Out-Null
    try { New-Item -ItemType Directory -Path $SharedLockDir -ErrorAction Stop | Out-Null }
    catch { throw "F301 physical campaign lock is already held" }
    $owner = [ordered]@{
        schema = "openmitrastar.f301-physical-radio-lock/v1"
        owner = "f301-store-protection-probe"
        pid = $PID
        started_at = [DateTime]::UtcNow.ToString("o")
        evidence_dir = $EvidenceDir
    }
    $owner | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $SharedLockDir "owner.json") -Encoding ascii
}

function Release-SharedLock {
    if (Test-Path -LiteralPath $SharedLockDir) { Remove-Item -LiteralPath $SharedLockDir -Recurse -Force }
}

foreach ($requiredPath in @($manifestPath, $knownHosts, $moduleLocal, $moduleManifestPath, $undefinedSymbolsPath, $sourcePath, $featurePath)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) { throw "Missing local contract input: $requiredPath" }
}

$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$moduleManifest = Get-Content -Raw -LiteralPath $moduleManifestPath | ConvertFrom-Json
$candidate = Join-Path $build ([string]$manifest.artifacts.webformat.file)
if (-not (Test-Path -LiteralPath $candidate)) { throw "Missing F301 candidate: $candidate" }
$candidateHash = Get-Sha256 $candidate
$moduleHash = Get-Sha256 $moduleLocal
$featureHash = Get-Sha256 $featurePath
$sourceContract = Test-SourceContract $sourcePath
$vermagic = (Get-AsciiString $moduleLocal "vermagic=") -replace '^vermagic=', ''
$imports = @(Get-Content -LiteralPath $undefinedSymbolsPath | Where-Object { $_.Trim() } | ForEach-Object { $_.Trim() })
$allowedImports = @("ioremap", "iounmap", "of_machine_is_compatible", "param_ops_bool", "param_ops_uint", "printk")
$importsExact = (@(Compare-Object ($imports | Sort-Object) ($allowedImports | Sort-Object)).Count -eq 0)
$packagedModule = $manifest.foundation_assets.rootfs_diff.new.PSObject.Properties[$moduleRelative].Value
$featureText = Get-Content -Raw -LiteralPath $featurePath
$featureDisabled = (
    $featureText -match '(?m)^OPENMITRASTAR_STORE_PROTECTION_OBSERVER=0\s*$' -and
    $featureText -match '(?m)^OPENMITRASTAR_STORE_PROTECTION_AUTOLOAD=0\s*$' -and
    $featureText -match '(?m)^OPENMITRASTAR_STORE_PROTECTION_WRITE_CAPABLE=0\s*$'
)
$manifestContract = (
    $manifest.schema -eq "openmitrastar.f301-f300-datapath-f301-capability-truth/v2" -and
    $manifest.artifacts.webformat.sha256 -eq $expectedFirmwareSha256 -and
    $manifest.store_protection_observer.sha256 -eq $expectedModuleSha256 -and
    $manifest.store_protection_observer.autoload -eq $false -and
    $manifest.store_protection_observer.write_capable -eq $false -and
    $manifest.store_protection_observer.read_commands_only -eq $true -and
    $manifest.store_protection_observer.mtd_registration -eq $false -and
    $manifest.store_protection_observer.erase -eq $false -and
    $manifest.store_protection_observer.program -eq $false -and
    $manifest.store_protection_observer.protection_mutation -eq $false -and
    $packagedModule.sha256 -eq $expectedModuleSha256
)
$moduleManifestContract = (
    $moduleManifest.schema -eq "openmitrastar.f295-store-protection-observer/v1" -and
    $moduleManifest.status -eq "PASS" -and
    $moduleManifest.artifact.sha256 -eq $expectedModuleSha256 -and
    $moduleManifest.kernel_contract.vermagic -eq $expectedVermagic -and
    $moduleManifest.kernel_contract.all_imports_exported_by_f293_vmlinux -eq $true -and
    $moduleManifest.safety.read_commands_only -eq $true -and
    $moduleManifest.safety.write_enable -eq $false -and
    $moduleManifest.safety.erase -eq $false -and
    $moduleManifest.safety.program -eq $false -and
    $moduleManifest.safety.mtd_registration -eq $false -and
    $moduleManifest.safety.protection_mutation -eq $false
)
$localPreflightPass = (
    $candidateHash -eq $expectedFirmwareSha256 -and
    $moduleHash -eq $expectedModuleSha256 -and
    $vermagic -eq $expectedVermagic -and
    $importsExact -and $sourceContract.pass -and $manifestContract -and
    $moduleManifestContract -and $featureDisabled -and
    $featureHash -eq "e97f75da41bd098c831398387f405a0e2f0cbdc2e0c499d29876e9fa148d5eca"
)
$campaign = Get-CampaignState

if (-not $OutputDir) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $OutputDir = Join-Path $root "outputs\preflight\f301-store-protection-probe-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $OutputDir) {
    if (@(Get-ChildItem -LiteralPath $OutputDir -Force).Count -gt 0) { throw "Refusing to overwrite evidence directory: $OutputDir" }
} else { New-Item -ItemType Directory -Path $OutputDir | Out-Null }

$plan = [ordered]@{
    schema = "openmitrastar.f301-store-protection-probe-plan/v1"
    generated_at = [DateTime]::UtcNow.ToString("o")
    mode = if ($Execute) { "execute" } else { "dry-run" }
    required_firmware = $expectedVersion
    candidate_file = [IO.Path]::GetFileName($candidate)
    candidate_sha256 = $candidateHash
    candidate_matches = $candidateHash -eq $expectedFirmwareSha256
    module_file = [IO.Path]::GetFileName($moduleLocal)
    module_sha256 = $moduleHash
    module_matches = $moduleHash -eq $expectedModuleSha256
    module_vermagic = $vermagic
    vermagic_matches = $vermagic -eq $expectedVermagic
    module_imports = $imports
    imports_exact_allowlist = $importsExact
    source_contract = $sourceContract
    manifest_contract = $manifestContract
    module_manifest_contract = $moduleManifestContract
    feature_disabled = $featureDisabled
    local_preflight_pass = $localPreflightPass
    campaign_guard = $campaign
    execute_allowed_now = [bool]($localPreflightPass -and -not $campaign.active)
    hardware_preflight = "DEFERRED_UNTIL_EXECUTE"
    hardware_actions_performed = $false
    runtime_scope = "RAM-only module load from read-only SquashFS"
    observations = @("JEDEC", "status", "SCUR", "DPB")
    mutation_primitives = [ordered]@{
        write_enable = $false
        erase = $false
        program = $false
        protection_mutation = $false
        mtd_registration = $false
    }
    before_after = @("/proc/mtd exact content", "all registered /dev/mtdblock hashes", "fatal count", "observer feature flags")
    module_cleanup_required = $true
    observer_disabled_after = $true
    flash = $false
    persistent_writes = $false
    mtd_writes = $false
}
Write-AtomicJson (Join-Path $OutputDir "plan.json") $plan
$plan | ConvertTo-Json -Depth 12

if (-not $Execute) { exit $(if ($localPreflightPass) { 0 } else { 1 }) }
if ([IO.Path]::GetFullPath($CampaignStateRoot) -ne [IO.Path]::GetFullPath($defaultCampaignStateRoot) -or
    [IO.Path]::GetFullPath($SharedLockDir) -ne [IO.Path]::GetFullPath($defaultSharedLockDir) -or
    $SkipProcessInventory) {
    throw "Execute mode refuses campaign-state or lock-path overrides"
}
if ($Ack -ne $requiredAck) { throw "Refusing probe: exact -Ack is required" }
if (-not $localPreflightPass) { throw "F301 local artifact/module contract mismatch" }
if ($campaign.active) {
    Write-AtomicJson (Join-Path $OutputDir "blocked.json") ([ordered]@{
        schema = "openmitrastar.f301-store-protection-probe/v1"
        status = "BLOCKED"
        phase = "campaign-exclusion"
        campaign_guard = $campaign
        hardware_actions_performed = $false
    })
    exit 2
}

$lockAcquired = $false
$uart = $null
try {
    Acquire-SharedLock $OutputDir
    $lockAcquired = $true
    $campaignAfterLock = Get-CampaignState -IgnoreSharedLock
    if ($campaignAfterLock.active) { throw "Campaign became active while acquiring the F301 hardware lock" }
    if (-not (Test-Tcp $RouterHost 22)) { throw "Router SSH is unavailable" }
    if (-not ([IO.Ports.SerialPort]::GetPortNames() -contains $Port)) { throw "UART port $Port is unavailable" }

    $ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
    $sshBase = @(
        "-i", "$env:USERPROFILE\.ssh\id_ed25519", "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=5",
        "-o", "ServerAliveCountMax=2", "-o", "StrictHostKeyChecking=yes",
        "-o", "UserKnownHostsFile=$knownHosts", "-o", "LogLevel=ERROR", "root@$RouterHost"
    )

    $precheckCommand = @'
set -eu
test "$(sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release)" = lyoko-foundation-6.6.1-f301-f300-capability-truth-device
test "$(uname -r)" = 5.10.260-openmitrastar-radiohw
feature=/etc/openmitrastar/features/store-protection-observer-v1
module=/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn-topaz-store-protection-observer.ko
test -r "$feature"
grep -q '^OPENMITRASTAR_STORE_PROTECTION_OBSERVER=0$' "$feature"
grep -q '^OPENMITRASTAR_STORE_PROTECTION_AUTOLOAD=0$' "$feature"
grep -q '^OPENMITRASTAR_STORE_PROTECTION_WRITE_CAPABLE=0$' "$feature"
test "$(sha256sum "$module" | awk '{print $1}')" = 2f00a2db7103e0eb5691d86ae9122cdb22e34d935d7042339d131d2e55c906f8
grep -q '^mtd0: 00010000 00010000 "uboot_env"$' /proc/mtd
grep -q '^mtd1: 00010000 00010000 "uboot_env_bak"$' /proc/mtd
grep -q '^mtd2: 00080000 00010000 "data"$' /proc/mtd
grep -q '^mtd3: 00460000 00010000 "rootfs_live"$' /proc/mtd
grep -q '^mtd4: 001c0000 00010000 "lyoko_store"$' /proc/mtd
test "$(grep -c '^mtd[0-9]:' /proc/mtd)" = 5
! grep -q '^qtn_topaz_store_protection_observer ' /proc/modules
! grep -q '^/dev/mtdblock4 ' /proc/mounts
awk '$2 == "/" { found=1; if ($4 !~ /(^|,)ro(,|$)/) exit 1 } END { exit found ? 0 : 1 }' /proc/mounts
echo OMF301_STORE_PROBE_PREFLIGHT_PASS
'@
    $precheck = & $ssh @sshBase $precheckCommand
    if ($LASTEXITCODE -ne 0 -or $precheck -notcontains "OMF301_STORE_PROBE_PREFLIGHT_PASS") {
        throw "F301 runtime preflight failed before module load"
    }

    $uartDir = Join-Path $OutputDir "uart"
    $uartArgs = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
        (Join-Path $root "tools\capture_topaz_uart_resilient.ps1"),
        "-Port", $Port, "-Seconds", [string]$UartSeconds,
        "-OutputDirectory", $uartDir, "-RunId", "f301-store-protection"
    )
    $uartStdout = Join-Path $OutputDir "uart-capture.stdout.log"
    $uartStderr = Join-Path $OutputDir "uart-capture.stderr.log"
    $uart = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList $uartArgs `
        -RedirectStandardOutput $uartStdout -RedirectStandardError $uartStderr -PassThru

    $captureStatus = Join-Path $uartDir "capture-status.json"
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath $captureStatus) {
            $capture = Get-Content -Raw -LiteralPath $captureStatus | ConvertFrom-Json
            if ($capture.ready) { break }
            if ($capture.state -eq "error") { throw "UART capture failed: $($capture.error)" }
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not (Test-Path -LiteralPath $captureStatus)) { throw "UART capture did not become ready" }

    $remoteCommand = @'
set -eu
module=/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn-topaz-store-protection-observer.ko
name=qtn_topaz_store_protection_observer
feature=/etc/openmitrastar/features/store-protection-observer-v1
tmp=/tmp/f301-store-protection-probe.$$
mkdir "$tmp"
loaded=0
cleanup() {
  if [ "$loaded" = 1 ]; then rmmod "$name" >/dev/null 2>&1 || true; fi
  rm -rf "$tmp"
}
trap cleanup EXIT HUP INT TERM
cp /proc/mtd "$tmp/mtd.before"
for n in 0 1 2 3 4; do sha256sum "/dev/mtdblock$n" | awk -v n="$n" '{print "mtd" n "=" $1}' >>"$tmp/hashes.before"; done
fatal_before=$(dmesg | grep -Eic 'kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset|Machine Check' || true)
insmod "$module"
loaded=1
base=/sys/module/$name/parameters
test -d "$base"
test "$(cat "$base/read_commands_only")" = Y
test "$(cat "$base/store_dpb_scan_count")" = 28
test "$(cat "$base/control_restored")" = Y
test "$(cat "$base/jedec_matches")" = Y
for parameter in jedec_id status_register security_register store_first_dpb store_last_dpb store_dpb_zero_count store_dpb_nonzero_count store_dpb_scan_count control_restored read_commands_only; do
  ls -l "$base/$parameter" | grep -q '^-r--r--r--'
done
echo OMF301_PROBE_BEGIN
for parameter in jedec_id jedec_matches status_register security_register store_first_dpb store_last_dpb store_dpb_zero_count store_dpb_nonzero_count store_dpb_scan_count control_restored read_commands_only; do
  printf '%s=' "$parameter"
  cat "$base/$parameter"
done
dmesg | grep 'OMSTOREPROBE' | tail -n 4
rmmod "$name"
loaded=0
trap - EXIT HUP INT TERM
cp /proc/mtd "$tmp/mtd.after"
for n in 0 1 2 3 4; do sha256sum "/dev/mtdblock$n" | awk -v n="$n" '{print "mtd" n "=" $1}' >>"$tmp/hashes.after"; done
fatal_after=$(dmesg | grep -Eic 'kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset|Machine Check' || true)
cmp -s "$tmp/mtd.before" "$tmp/mtd.after"
cmp -s "$tmp/hashes.before" "$tmp/hashes.after"
test "$fatal_before" = "$fatal_after"
! grep -q "^$name " /proc/modules
test ! -e "/sys/module/$name"
grep -q '^OPENMITRASTAR_STORE_PROTECTION_OBSERVER=0$' "$feature"
grep -q '^OPENMITRASTAR_STORE_PROTECTION_AUTOLOAD=0$' "$feature"
grep -q '^OPENMITRASTAR_STORE_PROTECTION_WRITE_CAPABLE=0$' "$feature"
sed 's/^/MTD_HASH_BEFORE_/' "$tmp/hashes.before"
sed 's/^/MTD_HASH_AFTER_/' "$tmp/hashes.after"
printf 'MTD_TABLE_HASH_BEFORE=%s\n' "$(sha256sum "$tmp/mtd.before" | awk '{print $1}')"
printf 'MTD_TABLE_HASH_AFTER=%s\n' "$(sha256sum "$tmp/mtd.after" | awk '{print $1}')"
printf 'FATAL_BEFORE=%s\nFATAL_AFTER=%s\n' "$fatal_before" "$fatal_after"
echo MODULE_UNLOADED=1
echo OBSERVER_DISABLED=1
echo MTD_REGISTRATION_ABSENT=1
echo OMF301_STORE_PROTECTION_PROBE_PASS
rm -rf "$tmp"
'@

    $stdoutPath = Join-Path $OutputDir "probe.stdout.log"
    $stderrPath = Join-Path $OutputDir "probe.stderr.log"
    $probe = & $ssh @sshBase $remoteCommand 2>$stderrPath
    $probeRc = $LASTEXITCODE
    $probe | Set-Content -LiteralPath $stdoutPath -Encoding ascii
    if ($probeRc -ne 0 -or $probe -notcontains "OMF301_STORE_PROTECTION_PROBE_PASS") {
        throw "F301 read-only store-protection probe failed"
    }

    if ($uart -and -not $uart.HasExited) { $uart.WaitForExit($UartSeconds * 1000 + 15000) | Out-Null }
    if ($uart -and -not $uart.HasExited) { Stop-Process -Id $uart.Id -Force }
    $text = Get-Content -Raw -LiteralPath $stdoutPath
    $uartLog = Join-Path $uartDir "uart.log"
    $uartFatal = $false
    if (Test-Path -LiteralPath $uartLog) {
        $uartFatal = [bool](Select-String -LiteralPath $uartLog -Pattern 'kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset|Machine Check' -CaseSensitive:$false -Quiet)
    }
    $allMtdHashes = $true
    foreach ($n in 0..4) {
        $beforeMatch = [regex]::Match($text, "(?m)^MTD_HASH_BEFORE_mtd$n=([0-9a-f]{64})\s*$")
        $afterMatch = [regex]::Match($text, "(?m)^MTD_HASH_AFTER_mtd$n=([0-9a-f]{64})\s*$")
        if (-not $beforeMatch.Success -or -not $afterMatch.Success -or $beforeMatch.Groups[1].Value -ne $afterMatch.Groups[1].Value) { $allMtdHashes = $false }
    }
    $checks = [ordered]@{
        runtime_preflight = $true
        probe_pass = $text -match '(?m)^OMF301_STORE_PROTECTION_PROBE_PASS\s*$'
        jedec_match = $text -match '(?m)^jedec_matches=Y\s*$'
        status_read = $text -match '(?m)^status_register=[0-9]+\s*$'
        scur_read = $text -match '(?m)^security_register=[0-9]+\s*$'
        dpb_scan_complete = $text -match '(?m)^store_dpb_scan_count=28\s*$'
        control_restored = $text -match '(?m)^control_restored=Y\s*$'
        read_commands_only = $text -match '(?m)^read_commands_only=Y\s*$'
        all_registered_mtd_hashes_unchanged = $allMtdHashes
        mtd_table_unchanged = $text -match '(?ms)^MTD_TABLE_HASH_BEFORE=([0-9a-f]{64}).*^MTD_TABLE_HASH_AFTER=\1\s*$'
        mtd_registration_absent = $text -match '(?m)^MTD_REGISTRATION_ABSENT=1\s*$'
        module_unloaded = $text -match '(?m)^MODULE_UNLOADED=1\s*$'
        observer_disabled = $text -match '(?m)^OBSERVER_DISABLED=1\s*$'
        fatal_count_unchanged = $text -match '(?ms)^FATAL_BEFORE=([0-9]+).*^FATAL_AFTER=\1\s*$'
        uart_no_fatal = -not $uartFatal
        write_enable_absent = $sourceContract.write_enable_absent
        erase_absent = $sourceContract.erase_absent
        program_absent = $sourceContract.program_absent
        persistent_write_attempted = $false
    }
    $status = if (@($checks.Values | Where-Object { $_ -ne $true }).Count -eq 0) { "PASS" } else { "FAIL" }
    $result = [ordered]@{
        schema = "openmitrastar.f301-store-protection-probe/v1"
        generated_at = [DateTime]::UtcNow.ToString("o")
        status = $status
        firmware = $expectedVersion
        firmware_sha256 = $expectedFirmwareSha256
        module_sha256 = $expectedModuleSha256
        module_vermagic = $expectedVermagic
        runtime_scope = "RAM-only"
        observations = @("JEDEC", "status", "SCUR", "DPB")
        checks = $checks
        stdout = $stdoutPath
        stderr = $stderrPath
        uart = $uartLog
        flash = $false
        persistent_writes = $false
    }
    Write-AtomicJson (Join-Path $OutputDir "result.json") $result
    if ($status -ne "PASS") { throw "F301 protection probe did not satisfy every read-only invariant" }
    Write-Output "OMF301_STORE_PROTECTION_PROBE_PASS=1 output=$OutputDir"
} finally {
    if ($uart -and -not $uart.HasExited) { Stop-Process -Id $uart.Id -Force -ErrorAction SilentlyContinue }
    if ($lockAcquired) { Release-SharedLock }
}
