[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$ExpectedPnpDeviceId = "FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000",
    [string]$RouterHost = "192.168.1.90",
    [ValidateRange(30, 180)][int]$UartSeconds = 60,
    [string]$OutputDir = "",
    [switch]$ParentHardwareGuardHeld,
    [int]$ParentGuardOwnerPid = 0,
    [long]$ParentGuardOwnerStartTicks = 0,
    [string]$ParentGuardToken = ''
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
. (Join-Path $root "tools\f319_uart_guard.ps1")
$device = "hgw500bna-qcv2-a2-primary"
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\$device\firmware\f319-device-bound"
$manifestPath = Join-Path $build "manifest.json"
$knownHosts = Join-Path $build "known_hosts.f319"
$moduleRelative = "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn-topaz-spi-owner-probe.ko"
$moduleRemote = "/$($moduleRelative -replace '\\','/')"
$moduleLocal = Join-Path $root "outputs\kernel-port\f319-spi-owner-probe-20260905\qtn-topaz-spi-owner-probe.ko"
$sourcePath = Join-Path $root "work\kernel-port\modules\qtn-topaz-spi-owner-probe\qtn-topaz-spi-owner-probe.c"
$expectedVersion = "lyoko-foundation-6.8.3-f319-spi-owner-claim-device"
$expectedFirmwareSha256 = "e33d851106aa342509184ab0d1d94fc0654d7206cb2a4c62c5fab7aa48c0dcc9"
$expectedModuleSha256 = "79436442b62110351fba44262a05ae0f2a9ffc87b36fabe74cc651112e431317"
$requiredAck = "OPENMITRASTAR_F319_SPI_OWNER_CLAIM_E33D8511"
$sharedLockDir = Join-Path $root "outputs\locks\f301-physical-radio.lock"

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
    $temporary = Join-Path $directory (".{0}.{1}.tmp" -f ([IO.Path]::GetFileName($Path)), $PID)
    try {
        $Value | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $temporary -Encoding ascii
        [IO.File]::Move($temporary, $Path)
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

foreach ($path in @($manifestPath, $knownHosts, $moduleLocal, $sourcePath)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing F319 contract input: $path" }
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$candidate = Join-Path $build ([string]$manifest.artifacts.webformat.file)
$source = Get-Content -LiteralPath $sourcePath -Raw
$forbidden = @('readl(', 'readb(', 'writel(', 'writeb(', 'memcpy_fromio', 'memcpy_toio', 'mtd_device_register', 'SPI_WRITE_ENABLE', 'SPI_PAGE_PROGRAM', 'SPI_SECTOR_ERASE', 'SPI_GBLOCK')
$forbiddenPresent = @($forbidden | Where-Object { $source.Contains($_) })
$checks = [ordered]@{
    schema = $manifest.schema -eq "openmitrastar.f319-spi-owner-claim-candidate/v1"
    candidate_hash = (Get-Sha256 $candidate) -eq $expectedFirmwareSha256
    candidate_bytes = (Get-Item -LiteralPath $candidate).Length -eq 5292032
    module_hash = (Get-Sha256 $moduleLocal) -eq $expectedModuleSha256
    module_autoload_disabled = $manifest.spi_owner_probe.autoload -eq $false
    mmio_reads_zero = $manifest.spi_owner_probe.mmio_reads -eq 0
    mmio_writes_zero = $manifest.spi_owner_probe.mmio_writes -eq 0
    mtd_registration_absent = $manifest.spi_owner_probe.mtd_registration -eq $false
    persistent_writes_disabled = $manifest.storage.persistent_writes_enabled -eq $false
    forbidden_access_absent = $forbiddenPresent.Count -eq 0
    uart_guard_present = Test-Path -LiteralPath (Join-Path $root "tools\f319_uart_guard.ps1") -PathType Leaf
}
$localPass = @($checks.Values | Where-Object { $_ -ne $true }).Count -eq 0

if (-not $OutputDir) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $OutputDir = Join-Path $root "outputs\preflight\f319-runtime-probe-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $OutputDir) { throw "Refusing to overwrite evidence directory: $OutputDir" }
New-Item -ItemType Directory -Path $OutputDir | Out-Null

$plan = [ordered]@{
    schema = "openmitrastar.f319-spi-owner-runtime-plan/v1"
    generated_at = [DateTime]::UtcNow.ToString("o")
    mode = if ($Execute) { "execute" } else { "dry-run" }
    required_runtime = $expectedVersion
    firmware_sha256 = $expectedFirmwareSha256
    module_sha256 = $expectedModuleSha256
    module_path = $moduleRemote
    local_checks = $checks
    local_preflight_pass = $localPass
    required_ack = $requiredAck
    uart_pnp_device_id = $ExpectedPnpDeviceId
    physical_lock = $sharedLockDir
    uart_binding = "pinned PnP plus authenticated HGW console nonce before insmod"
    hardware_actions_performed = $false
    runtime_actions = @("UART capture", "single insmod", "read-only parameter inspection", "rmmod")
    forbidden_actions = @("flash", "MTD write", "SPI opcode", "radio mutation", "reboot")
}
Write-AtomicJson (Join-Path $OutputDir "plan.json") $plan
$plan | ConvertTo-Json -Depth 10
if (-not $Execute) { exit $(if ($localPass) { 0 } else { 1 }) }

if ($Ack -ne $requiredAck) { throw "Refusing F319 probe: exact -Ack is required" }
if (-not $localPass) { throw "F319 local contract mismatch" }
if (-not (Test-Tcp $RouterHost 22)) { throw "Router SSH is unavailable" }

$guard = $null
$uart = $null
try {
    if ($ParentHardwareGuardHeld) {
        $leaseProof = Assert-F319HardwareLease -PhysicalLockDir $sharedLockDir -OwnerPid $ParentGuardOwnerPid -OwnerStartTicks $ParentGuardOwnerStartTicks -LeaseToken $ParentGuardToken -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId
        [void](Get-F319SerialDevice -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId)
    } else {
        $guard = Enter-F319HardwareGuard -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId -PhysicalLockDir $sharedLockDir -Owner "f319-spi-owner-probe" -EvidenceDir $OutputDir
        $leaseProof = $guard
    }
    [void](Assert-F319UartBinding -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId -RouterHost $RouterHost -KnownHosts $knownHosts -ExpectedVersion $expectedVersion -HardwareLease $leaseProof)

    $ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
    $sshBase = @("-i", "$env:USERPROFILE\.ssh\id_ed25519", "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=$knownHosts", "-o", "LogLevel=ERROR", "root@$RouterHost")
    $precheckScript = @'
grep -Fqx 'OPENMITRASTAR_PRODUCT_VERSION=__VERSION__' /etc/openmitrastar/release &&
test "$(sha256sum '__MODULE__' | cut -d' ' -f1)" = '__SHA256__' &&
! grep -q '^qtn_topaz_spi_owner_probe ' /proc/modules && echo OMF319_PREFLIGHT_PASS
'@
    $precheckScript = $precheckScript.Replace('__VERSION__', $expectedVersion).Replace('__MODULE__', $moduleRemote).Replace('__SHA256__', $expectedModuleSha256)
    $precheck = Invoke-F319SshScript -SshPath $ssh -Arguments ($sshBase + @('sh', '-s')) -Script $precheckScript -TimeoutSeconds 20
    if ($precheck.ExitCode -ne 0 -or @($precheck.Stdout -split '\r?\n') -notcontains "OMF319_PREFLIGHT_PASS") { throw "F319 runtime preflight failed" }

    $uartDir = Join-Path $OutputDir "uart"
    $captureRunId = 'f319-' + [Guid]::NewGuid().ToString('N')
    $uartArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $root "tools\capture_topaz_uart_resilient.ps1"), "-Port", $Port, "-ExpectedPnpDeviceId", $ExpectedPnpDeviceId, "-ExternalOwnershipHeld", "-ExternalGuardLockDir", $leaseProof.PhysicalLockDir, "-ExternalGuardOwnerPid", [string]$leaseProof.OwnerPid, "-ExternalGuardOwnerStartTicks", [string]$leaseProof.OwnerStartTicks, "-ExternalGuardToken", $leaseProof.LeaseToken, "-Seconds", [string]$UartSeconds, "-OutputDirectory", $uartDir, "-RunId", $captureRunId)
    $uartCommandLine = (($uartArgs | ForEach-Object { ConvertTo-F319NativeArgument $_ }) -join ' ')
    $uart = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList $uartCommandLine -RedirectStandardOutput (Join-Path $OutputDir "uart.stdout.log") -RedirectStandardError (Join-Path $OutputDir "uart.stderr.log") -PassThru
    # Keep the process handle while it is alive. Windows PowerShell 5.1 can
    # otherwise lose ExitCode after WaitForExit/Refresh (observed as $null).
    # Unknown/nonzero exit codes remain failures; never substitute zero.
    [void]$uart.Handle
    [void](Wait-F319UartCaptureReady -StatusPath (Join-Path $uartDir "capture-status.json") -Process $uart -ExpectedRunId $captureRunId -ExpectedPnpDeviceId $ExpectedPnpDeviceId -TimeoutSeconds 10)

    $remote = @'
set -eu
module=/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn-topaz-spi-owner-probe.ko
name=qtn_topaz_spi_owner_probe
before=$(sha256sum /proc/mtd | cut -d' ' -f1)
fatal_before=$(dmesg | grep -Eic 'kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset|Machine Check' || true)
loaded=0
cleanup() { if [ "$loaded" = 1 ]; then rmmod "$name" >/dev/null 2>&1 || true; fi; }
trap cleanup EXIT HUP INT TERM
printf '%s\n' '__F319_CAPTURE_RUN___BEGIN' >/dev/console
insmod "$module"
loaded=1
base=/sys/module/$name/parameters
test "$(cat "$base/controller_resource_claimed")" = Y
test "$(cat "$base/controller_mapped")" = Y
test "$(cat "$base/controller_read_count")" = 0
test "$(cat "$base/controller_write_count")" = 0
test "$(cat "$base/transaction_provider_ready")" = N
echo OMF319_OWNER_BEGIN
for key in controller_resource_claimed controller_mapped controller_read_count controller_write_count transaction_provider_ready; do printf '%s=' "$key"; cat "$base/$key"; done
rmmod "$name"
loaded=0
trap - EXIT HUP INT TERM
after=$(sha256sum /proc/mtd | cut -d' ' -f1)
fatal_after=$(dmesg | grep -Eic 'kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset|Machine Check' || true)
test "$before" = "$after"
test "$fatal_before" = "$fatal_after"
! grep -q "^$name " /proc/modules
printf 'MTD_TABLE_HASH_BEFORE=%s\nMTD_TABLE_HASH_AFTER=%s\n' "$before" "$after"
printf 'FATAL_BEFORE=%s\nFATAL_AFTER=%s\n' "$fatal_before" "$fatal_after"
echo MODULE_UNLOADED=1
printf '%s\n' '__F319_CAPTURE_RUN___END' >/dev/console
echo OMF319_SPI_OWNER_PASS
'@
    $remote = $remote.Replace('__F319_CAPTURE_RUN__', $captureRunId)
    $stdoutPath = Join-Path $OutputDir "probe.stdout.log"
    $stderrPath = Join-Path $OutputDir "probe.stderr.log"
    [void](Assert-F319HardwareLease -PhysicalLockDir $leaseProof.PhysicalLockDir -OwnerPid $leaseProof.OwnerPid -OwnerStartTicks $leaseProof.OwnerStartTicks -LeaseToken $leaseProof.LeaseToken -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId)
    [void](Wait-F319UartCaptureReady -StatusPath (Join-Path $uartDir 'capture-status.json') -Process $uart -ExpectedRunId $captureRunId -ExpectedPnpDeviceId $ExpectedPnpDeviceId -TimeoutSeconds 2)
    $probeResult = Invoke-F319SshScript -SshPath $ssh -Arguments ($sshBase + @('sh', '-s')) -Script $remote -TimeoutSeconds 30
    $probe = @($probeResult.Stdout -split '\r?\n' | Where-Object { $_.Length -gt 0 })
    $probeRc = $probeResult.ExitCode
    $probeResult.Stderr | Set-Content -LiteralPath $stderrPath -Encoding ascii
    $probe | Set-Content -LiteralPath $stdoutPath -Encoding ascii
    if ($probeRc -ne 0 -or $probe -notcontains "OMF319_SPI_OWNER_PASS") { throw "F319 runtime probe failed" }
    if ($uart -and -not $uart.HasExited) { $uart.WaitForExit($UartSeconds * 1000 + 15000) | Out-Null }
    if ($uart -and -not $uart.HasExited) { throw 'UART capture did not finish; runtime evidence is incomplete' }
    $uart.Refresh()
    [void](Assert-F319UartCaptureComplete -StatusPath (Join-Path $uartDir 'capture-status.json') -RawPath (Join-Path $uartDir 'uart.raw.bin') -TextPath (Join-Path $uartDir 'uart.log') -ExpectedRunId $captureRunId -ExpectedPnpDeviceId $ExpectedPnpDeviceId -CapturePid $uart.Id -CaptureExitCode $uart.ExitCode)

    $text = Get-Content -LiteralPath $stdoutPath -Raw
    $uartLog = Join-Path $uartDir "uart.log"
    $uartFatal = (Test-Path -LiteralPath $uartLog) -and [bool](Select-String -LiteralPath $uartLog -Pattern 'kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset|Machine Check' -CaseSensitive:$false -Quiet)
    $runtimeChecks = [ordered]@{
        claim = $text -match '(?m)^controller_resource_claimed=Y\s*$'
        mapping = $text -match '(?m)^controller_mapped=Y\s*$'
        reads_zero = $text -match '(?m)^controller_read_count=0\s*$'
        writes_zero = $text -match '(?m)^controller_write_count=0\s*$'
        provider_disabled = $text -match '(?m)^transaction_provider_ready=N\s*$'
        mtd_table_unchanged = $text -match '(?ms)^MTD_TABLE_HASH_BEFORE=([0-9a-f]{64}).*^MTD_TABLE_HASH_AFTER=\1\s*$'
        fatal_count_unchanged = $text -match '(?ms)^FATAL_BEFORE=([0-9]+).*^FATAL_AFTER=\1\s*$'
        module_unloaded = $text -match '(?m)^MODULE_UNLOADED=1\s*$'
        uart_no_fatal = -not $uartFatal
        uart_complete_correlated = $true
    }
    $status = if (@($runtimeChecks.Values | Where-Object { $_ -ne $true }).Count -eq 0) { "PASS" } else { "FAIL" }
    Write-AtomicJson (Join-Path $OutputDir "result.json") ([ordered]@{schema="openmitrastar.f319-spi-owner-runtime/v1";generated_at=[DateTime]::UtcNow.ToString("o");status=$status;firmware=$expectedVersion;firmware_sha256=$expectedFirmwareSha256;module_sha256=$expectedModuleSha256;checks=$runtimeChecks;uart_capture_exit_code=$uart.ExitCode;uart_capture_pid=$uart.Id;uart_capture_run_id=$captureRunId;flash=$false;mtd_writes=$false})
    if ($status -ne "PASS") { throw "F319 runtime invariants failed" }
    Write-Output "OMF319_SPI_OWNER_PASS=1 output=$OutputDir"
} finally {
    if ($uart -and -not $uart.HasExited) { Stop-Process -Id $uart.Id -Force -ErrorAction SilentlyContinue }
    Exit-F319HardwareGuard -Guard $guard
}
