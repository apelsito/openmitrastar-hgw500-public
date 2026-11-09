[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [string]$TftpHost = "192.168.1.43",
    [ValidateSet("auto", "tftp", "uart-ymodem")][string]$Transport = "auto",
    [ValidateRange(600, 1800)][int]$FlashTimeoutSeconds = 1800
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f300-device-bound"
$base = "openmitrastar-linux510-f300-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
$candidate = Join-Path $build ($base + ".webformat.bin")
$manifestPath = Join-Path $build "manifest.json"
$requiredAck = "OPENMITRASTAR_ROLLBACK_F301_TO_F300_734BBA8A"
$expectedSha256 = "734bba8ad1b706c0c17ad5e73341cbb7c7a5c4d78cf05e069d955705d789edbb"
$expectedBytes = 5259264
$expectedFullSlotCrc32 = "841f11c8"
$expectedFullSlotSha256 = "fb7867874640a428124a18be38b8521e52e5d27322393f88ab44bbd6d17baf9b"
$currentF301FullSlotCrc32 = "2483522f"
$currentF301FullSlotSha256 = "c9c98d000fa9ea1c2fd53738e97decf83ef9a21132b382a23df03121fac1577b"
$expectedVersion = "lyoko-foundation-6.5.3-f300-emac-hw-demand-two-sample-device"

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
        Where-Object { $_.IPAddress -eq $Address } |
        Select-Object -First 1)
}

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "").ToLowerInvariant()
    } finally {
        $sha.Dispose()
        $stream.Dispose()
    }
}

if (-not (Test-Path -LiteralPath $candidate) -or -not (Test-Path -LiteralPath $manifestPath)) {
    throw "F300 rollback artifact or manifest is missing"
}
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ((Get-Sha256 $candidate) -ne $expectedSha256 -or
    (Get-Item -LiteralPath $candidate).Length -ne $expectedBytes -or
    $manifest.schema -ne "openmitrastar.f300-emac-hw-demand-two-sample-from-f299/v1" -or
    $manifest.artifacts.webformat.sha256 -ne $expectedSha256 -or
    [int64]$manifest.artifacts.webformat.bytes -ne $expectedBytes -or
    $manifest.artifacts.full_slot.crc32 -ne $expectedFullSlotCrc32 -or
    $manifest.artifacts.full_slot.sha256 -ne $expectedFullSlotSha256 -or
    $manifest.contracts.bootbase -ne "PASS" -or
    $manifest.candidate_eligible -ne $true -or
    $manifest.flash_supported -ne $true) {
    throw "F300 rollback artifact contract mismatch"
}

[ordered]@{
    schema = "openmitrastar.f301-to-f300-rollback-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    target = "mtd4/linux_live"
    candidate = $candidate
    bytes = $expectedBytes
    sha256 = $expectedSha256
    full_slot_crc32 = $expectedFullSlotCrc32
    full_slot_sha256 = $expectedFullSlotSha256
    expected_current_full_slot_crc32 = $currentF301FullSlotCrc32
    expected_current_full_slot_sha256 = $currentF301FullSlotSha256
    erase_bytes = "0x005e0000"
    preserved_store_bytes = "0x001c0000"
    preferred_transport = "TFTP through wired controller $TftpHost"
    fallback_transport = "UART/YMODEM only before any erase"
    hardware_preflight = if ($Execute) { "REQUIRED_BEFORE_WRITE" } else { "DEFERRED_TO_EXECUTE" }
    hardware_actions_performed = $false
} | ConvertTo-Json -Depth 5

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing rollback: exact -Ack is required" }
if (-not (Test-Tcp $RouterHost 22)) { throw "Router SSH preflight failed" }
if (-not (Test-LocalIPv4 $TftpHost)) { throw "TFTP host address $TftpHost is not local" }
if (-not ([IO.Ports.SerialPort]::GetPortNames() -contains $Port)) { throw "UART port $Port is not present" }

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
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $currentF301FullSlotCrc32
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = $currentF301FullSlotSha256

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$runDir = Join-Path $root "outputs\flash-watch\f301-to-f300-rollback-$stamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$runner = Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py"
$common = @(
    "--execute", "--ack", $requiredAck, "--port", $Port,
    "--client-ip", $RouterHost, "--host", $RouterHost, "--skip-reboot",
    "--timeout", "$FlashTimeoutSeconds", "--erase-bytes", "0x5e0000"
)

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\reboot_to_topaz_prompt_sysrq.ps1") `
    -Port $Port -LogPath (Join-Path $runDir "uart-to-topaz.log") -TimeoutSeconds 240
if ($LASTEXITCODE -ne 0) { throw "F301 rollback could not acquire the Topaz prompt" }

$flashed = $false
if ($Transport -in @("auto", "tftp")) {
    & python $runner @common --transport tftp --server-ip $TftpHost --uart-attach-topaz
    if ($LASTEXITCODE -eq 0) { $flashed = $true }
    if (-not $flashed) {
        $latest = Get-ChildItem -LiteralPath $build -Directory -Filter "flash-one-shot-*" |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        $transcript = if ($latest) { Join-Path $latest.FullName "bootbase-flash-uart.log" } else { "" }
        if ($transcript -and (Test-Path -LiteralPath $transcript) -and
            (Select-String -LiteralPath $transcript -SimpleMatch "spi_flash erase" -Quiet)) {
            throw "TFTP failed after erase began; automatic fallback refused"
        }
        if ($Transport -eq "tftp") { throw "TFTP transport failed" }
    }
}
if (-not $flashed) {
    & python $runner @common --transport uart-ymodem --uart-attach-topaz
    if ($LASTEXITCODE -ne 0) { throw "UART/YMODEM transport failed" }
}

$platformGate = Join-Path $root "outputs\postflash\f300-device-$stamp"
& python (Join-Path $root "tools\post_flash_f214_device_gate.py") `
    --host $RouterHost --wait-seconds 360 --output-dir $platformGate --device-dir $build `
    --expected-version $expectedVersion --known-hosts-name known_hosts.f300
if ($LASTEXITCODE -ne 0) { throw "F300 platform gate failed after rollback: $platformGate" }

$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$knownHosts = Join-Path $build "known_hosts.f300"
$probe = & $ssh -i "$env:USERPROFILE\.ssh\id_ed25519" -o IdentitiesOnly=yes -o BatchMode=yes `
    -o ConnectTimeout=8 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$knownHosts" -o LogLevel=ERROR `
    "root@$RouterHost" 'set -eu; test "$(sed -n ''s/^OPENMITRASTAR_PRODUCT_VERSION=//p'' /etc/openmitrastar/release)" = lyoko-foundation-6.5.3-f300-emac-hw-demand-two-sample-device; test "$(cat /run/openmitrastar/boot-state)" = ready; stats=/sys/bus/platform/devices/e8000000.ethernet/lyoko_emac_stats; grep -q "^napi_weight=256$" "$stats"; grep -q "^rx_restart_reason_hw_demand=" "$stats"; grep -q "^rx_restart_last_trigger_pokes=" "$stats"; echo OMF300_ROLLBACK_RUNTIME_PASS'
if ($LASTEXITCODE -ne 0 -or $probe -notcontains "OMF300_ROLLBACK_RUNTIME_PASS") {
    throw "F300 runtime contract failed after rollback"
}

$statusPath = Join-Path $runDir "status.json"
[ordered]@{
    schema = "openmitrastar.f301-to-f300-rollback/v1"
    status = "PASS"
    target = "mtd4/linux_live"
    candidate_sha256 = $expectedSha256
    full_slot_crc32 = $expectedFullSlotCrc32
    full_slot_sha256 = $expectedFullSlotSha256
    erase_bytes = "0x005e0000"
    preserved_store_bytes = "0x001c0000"
    platform_gate = $platformGate
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statusPath -Encoding ascii

Write-Output "OMF301_TO_F300_ROLLBACK_PASS=1 status=$statusPath"
