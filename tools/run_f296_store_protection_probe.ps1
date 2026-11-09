[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [ValidateRange(30, 180)][int]$UartSeconds = 60,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f296-device-bound"
$manifestPath = Join-Path $build "manifest.json"
$knownHosts = Join-Path $build "known_hosts.f296"
$moduleRelative = "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn-topaz-store-protection-observer.ko"
$moduleLocal = Join-Path $root "outputs\kernel-port\f295-store-protection-observer-20260904\qtn-topaz-store-protection-observer.ko"
$moduleRemote = "/$($moduleRelative -replace '\\','/')"
$moduleName = "qtn_topaz_store_protection_observer"
$expectedVersion = "lyoko-foundation-6.5.3-f296-store-protection-ui-device"
$expectedFirmwareSha256 = "2b9c7adc2ec6ecfc40e7f150d468feea61c7b9468db57a68cbdfa0327b10c2c6"
$expectedModuleSha256 = "2f00a2db7103e0eb5691d86ae9122cdb22e34d935d7042339d131d2e55c906f8"
$requiredAck = "OPENMITRASTAR_F296_STORE_PROTECTION_READONLY_2F00A2DB"

function Test-Tcp([string]$HostName, [int]$TcpPort, [int]$TimeoutMs = 1200) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $pending = $client.BeginConnect($HostName, $TcpPort, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne($TimeoutMs)) { return $false }
        $client.EndConnect($pending)
        return $true
    } catch { return $false } finally { $client.Dispose() }
}

$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$moduleHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $moduleLocal).Hash.ToLowerInvariant()
$candidate = Join-Path $build $manifest.artifacts.webformat.file
$candidateHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant()
$manifestContract = (
    $manifest.schema -eq "openmitrastar.f296-store-protection-ui-from-f294/v1" -and
    $manifest.candidate_eligible -eq $false -and
    $manifest.flash_supported -eq $false -and
    $manifest.store_protection_observer.autoload -eq $false -and
    $manifest.store_protection_observer.write_capable -eq $false -and
    $manifest.store_protection_observer.sha256 -eq $expectedModuleSha256
)
$preflight = [ordered]@{
    schema = "openmitrastar.f296-store-protection-probe-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    required_runtime = $expectedVersion
    router_ssh = Test-Tcp $RouterHost 22
    uart_present = [IO.Ports.SerialPort]::GetPortNames() -contains $Port
    candidate_sha256 = $candidateHash
    candidate_matches = $candidateHash -eq $expectedFirmwareSha256
    manifest_contract = $manifestContract
    module_sha256 = $moduleHash
    module_matches = $moduleHash -eq $expectedModuleSha256
    module_autoload = $false
    module_write_capable = $false
    flash = $false
    mtd_write = $false
    target = "runtime observation only"
}
$preflight | ConvertTo-Json -Depth 5

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing probe: exact -Ack is required" }
if (-not $preflight.candidate_matches -or -not $preflight.module_matches -or -not $preflight.manifest_contract) { throw "F296 artifact contract mismatch" }
if (-not $preflight.router_ssh) { throw "router SSH is unavailable" }
if (-not $preflight.uart_present) { throw "UART port $Port is unavailable" }

if (-not $OutputDir) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $OutputDir = Join-Path $root "outputs\storage\f296-protection-probe-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$sshBase = @(
    "-i", "$env:USERPROFILE\.ssh\id_ed25519",
    "-o", "IdentitiesOnly=yes",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=8",
    "-o", "ServerAliveInterval=5",
    "-o", "ServerAliveCountMax=2",
    "-o", "StrictHostKeyChecking=yes",
    "-o", "UserKnownHostsFile=$knownHosts",
    "-o", "LogLevel=ERROR",
    "root@$RouterHost"
)

$precheckCommand = @'
set -eu
test "$(sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release)" = lyoko-foundation-6.5.3-f296-store-protection-ui-device
test -r /etc/openmitrastar/features/store-protection-observer-v1
grep -q '^OPENMITRASTAR_STORE_PROTECTION_OBSERVER=0$' /etc/openmitrastar/features/store-protection-observer-v1
grep -q '^OPENMITRASTAR_STORE_PROTECTION_AUTOLOAD=0$' /etc/openmitrastar/features/store-protection-observer-v1
grep -q '^OPENMITRASTAR_STORE_PROTECTION_WRITE_CAPABLE=0$' /etc/openmitrastar/features/store-protection-observer-v1
test -r /lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn-topaz-store-protection-observer.ko
test "$(sha256sum /lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn-topaz-store-protection-observer.ko | cut -d' ' -f1)" = 2f00a2db7103e0eb5691d86ae9122cdb22e34d935d7042339d131d2e55c906f8
grep -q '^mtd4: 001c0000 00010000 "lyoko_store"$' /proc/mtd
! grep -q '^/dev/mtdblock4 ' /proc/mounts
! grep -q '^qtn_topaz_store_protection_observer ' /proc/modules
echo OMF296_STORE_PROBE_PREFLIGHT_PASS
'@
$precheck = & $ssh @sshBase $precheckCommand
if ($LASTEXITCODE -ne 0 -or $precheck -notcontains "OMF296_STORE_PROBE_PREFLIGHT_PASS") {
    throw "F296 runtime preflight failed before module load"
}

$uartDir = Join-Path $OutputDir "uart"
$uartArgs = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
    (Join-Path $root "tools\capture_topaz_uart_resilient.ps1"),
    "-Port", $Port, "-Seconds", [string]$UartSeconds,
    "-OutputDirectory", $uartDir, "-RunId", "f296-store-protection"
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
before=$(sha256sum /dev/mtdblock4 | cut -d' ' -f1)
mtd_before=$(sha256sum /proc/mtd | cut -d' ' -f1)
fatal_before=$(dmesg | grep -Eic 'kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset' || true)
insmod "$module"
trap 'rmmod qtn_topaz_store_protection_observer 2>/dev/null || true' EXIT HUP INT TERM
base=/sys/module/qtn_topaz_store_protection_observer/parameters
test "$(cat "$base/read_commands_only")" = Y
test "$(cat "$base/store_dpb_scan_count")" = 28
test "$(cat "$base/control_restored")" = Y
echo OMF296_PROBE_BEGIN
for name in jedec_id jedec_matches status_register security_register store_first_dpb store_last_dpb store_dpb_zero_count store_dpb_nonzero_count store_dpb_scan_count control_restored read_commands_only; do
  printf '%s=' "$name"
  cat "$base/$name"
done
dmesg | grep 'OMSTOREPROBE' | tail -n 4
rmmod qtn_topaz_store_protection_observer
trap - EXIT HUP INT TERM
after=$(sha256sum /dev/mtdblock4 | cut -d' ' -f1)
mtd_after=$(sha256sum /proc/mtd | cut -d' ' -f1)
fatal_after=$(dmesg | grep -Eic 'kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset' || true)
test "$before" = "$after"
test "$mtd_before" = "$mtd_after"
test "$fatal_before" = "$fatal_after"
! grep -q '^qtn_topaz_store_protection_observer ' /proc/modules
printf 'STORE_HASH_BEFORE=%s\nSTORE_HASH_AFTER=%s\n' "$before" "$after"
printf 'MTD_TABLE_HASH_BEFORE=%s\nMTD_TABLE_HASH_AFTER=%s\n' "$mtd_before" "$mtd_after"
printf 'FATAL_BEFORE=%s\nFATAL_AFTER=%s\n' "$fatal_before" "$fatal_after"
echo MODULE_UNLOADED=1
echo OMF296_PROBE_PASS
'@

$stdoutPath = Join-Path $OutputDir "probe.stdout.log"
$stderrPath = Join-Path $OutputDir "probe.stderr.log"
try {
    $probe = & $ssh @sshBase $remoteCommand 2>$stderrPath
    $probeRc = $LASTEXITCODE
    $probe | Set-Content -LiteralPath $stdoutPath -Encoding ascii
    if ($probeRc -ne 0 -or $probe -notcontains "OMF296_PROBE_PASS") {
        throw "F296 read-only protection probe failed"
    }
} finally {
    if (-not $uart.HasExited) { $uart.WaitForExit($UartSeconds * 1000 + 15000) | Out-Null }
    if (-not $uart.HasExited) { Stop-Process -Id $uart.Id -Force }
}

$text = Get-Content -Raw -LiteralPath $stdoutPath
$fatalUart = $false
$uartLog = Join-Path $uartDir "uart.log"
if (Test-Path -LiteralPath $uartLog) {
    $fatalUart = [bool](Select-String -LiteralPath $uartLog -Pattern 'kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset' -CaseSensitive:$false -Quiet)
}
$checks = [ordered]@{
    preflight = $true
    probe_pass = $text -match '(?m)^OMF296_PROBE_PASS\s*$'
    jedec_match = $text -match '(?m)^jedec_matches=Y\s*$'
    dpb_scan_complete = $text -match '(?m)^store_dpb_scan_count=28\s*$'
    control_restored = $text -match '(?m)^control_restored=Y\s*$'
    read_commands_only = $text -match '(?m)^read_commands_only=Y\s*$'
    store_hash_unchanged = $text -match '(?ms)^STORE_HASH_BEFORE=([0-9a-f]{64}).*^STORE_HASH_AFTER=\1\s*$'
    mtd_table_unchanged = $text -match '(?ms)^MTD_TABLE_HASH_BEFORE=([0-9a-f]{64}).*^MTD_TABLE_HASH_AFTER=\1\s*$'
    module_unloaded = $text -match '(?m)^MODULE_UNLOADED=1\s*$'
    fatal_count_unchanged = $text -match '(?ms)^FATAL_BEFORE=([0-9]+).*^FATAL_AFTER=\1\s*$'
    uart_no_fatal = -not $fatalUart
    mtd_write_attempted = $false
}
$status = if (($checks.Values | Where-Object { $_ -ne $true }).Count -eq 0) { "PASS" } else { "FAIL" }
[ordered]@{
    schema = "openmitrastar.f296-store-protection-probe/v1"
    status = $status
    firmware = $expectedVersion
    module_sha256 = $expectedModuleSha256
    checks = $checks
    stdout = $stdoutPath
    stderr = $stderrPath
    uart = $uartLog
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputDir "result.json") -Encoding ascii

if ($status -ne "PASS") { throw "F296 protection probe did not satisfy every read-only invariant" }
Write-Output "OMF296_STORE_PROTECTION_PROBE_PASS=1 output=$OutputDir"
