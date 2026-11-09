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
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f272-device-bound"
$base = "openmitrastar-linux510-f272-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
$candidate = Join-Path $build ($base + ".webformat.bin")
$manifestPath = Join-Path $build "manifest.json"
$requiredAck = "OPENMITRASTAR_F272_QTN_JSON_875F8148"
$expectedSha256 = "875f81484a08f1d4acf6b36f1adcb4dc5f912ee608107dcd6b438f640ce12832"
$expectedBytes = 5259264
$currentF271FullSlotSha256 = "66d49fe62c8437a8cd41e8a457bf5d26c35d7d0fa29a139c713b58506329ced2"
$currentF271FullSlotCrc32 = "a07fec42"

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
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant() -ne $expectedSha256 -or
    (Get-Item -LiteralPath $candidate).Length -ne $expectedBytes -or
    $manifest.schema -ne "openmitrastar.f272-qtn-json-fix/v1" -or
    $manifest.contracts.bootbase -ne "PASS" -or
    $manifest.candidate_eligible -ne $true -or
    $manifest.flash_supported -ne $true -or
    $manifest.native_qtn_control.default_enabled -ne $false -or
    $manifest.dfs_observability.radar_backend_ready -ne $false -or
    $manifest.developer_console.mode -ne "single-developer-console") {
    throw "F272 candidate contract mismatch"
}

[ordered]@{
    schema = "openmitrastar.f272-direct-promotion-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    target = "mtd4/linux_live"
    candidate = $candidate
    bytes = $expectedBytes
    sha256 = $expectedSha256
    full_slot_crc32 = $manifest.artifacts.full_slot.crc32
    erase_bytes = "0x005e0000"
    preserved_store_bytes = "0x001c0000"
    preferred_transport = "TFTP through wired controller $TftpHost"
    fallback_transport = "UART/YMODEM only before any erase"
    router_ssh = Test-Tcp $RouterHost 22
    tftp_host_local = $TftpHost -eq "192.168.1.43"
    uart_present = [IO.Ports.SerialPort]::GetPortNames() -contains $Port
} | ConvertTo-Json -Depth 5

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing flash: exact -Ack is required" }
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
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $currentF271FullSlotCrc32
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = $currentF271FullSlotSha256

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$runDir = Join-Path $root "outputs\flash-watch\f272-direct-$stamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$runner = Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py"
$common = @("--execute", "--ack", $requiredAck, "--port", $Port, "--client-ip", $RouterHost, "--host", $RouterHost, "--skip-reboot", "--timeout", "$FlashTimeoutSeconds", "--erase-bytes", "0x5e0000")
$useTftp = $Transport -in @("auto", "tftp")

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\reboot_to_topaz_prompt_sysrq.ps1") -Port $Port -LogPath (Join-Path $runDir "uart-to-topaz.log") -TimeoutSeconds 240
if ($LASTEXITCODE -ne 0) { throw "F272 could not acquire the Topaz prompt" }
$flashed = $false
if ($useTftp) {
    & python $runner @common --transport tftp --server-ip $TftpHost --uart-attach-topaz
    if ($LASTEXITCODE -eq 0) { $flashed = $true }
    if (-not $flashed) {
        $latest = Get-ChildItem -LiteralPath $build -Directory -Filter "flash-one-shot-*" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        $transcript = if ($latest) { Join-Path $latest.FullName "bootbase-flash-uart.log" } else { "" }
        if ($transcript -and (Test-Path -LiteralPath $transcript) -and (Select-String -LiteralPath $transcript -SimpleMatch "spi_flash erase" -Quiet)) {
            throw "TFTP failed after erase began; automatic fallback refused"
        }
        if ($Transport -eq "tftp") { throw "TFTP transport failed" }
    }
}
if (-not $flashed) {
    & python $runner @common --transport uart-ymodem --uart-attach-topaz
    if ($LASTEXITCODE -ne 0) { throw "UART/YMODEM transport failed" }
    $flashed = $true
}

$platformGate = Join-Path $root "outputs\postflash\f272-device-$stamp"
& python (Join-Path $root "tools\post_flash_f214_device_gate.py") --host $RouterHost --wait-seconds 360 --output-dir $platformGate --device-dir $build --expected-version lyoko-foundation-6.2.1-f272-qtn-json-fix-device --known-hosts-name known_hosts.f272
if ($LASTEXITCODE -ne 0) { throw "F272 platform gate failed: $platformGate" }

$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$probe = & $ssh -i "$env:USERPROFILE\.ssh\id_ed25519" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$(Join-Path $build 'known_hosts.f272')" -o LogLevel=ERROR "root@$RouterHost" 'set +e; grep "^napi_weight=128$" /sys/bus/platform/devices/e8000000.ethernet/lyoko_emac_stats; grep -E ''^(irq_count|napi_polls|rx_head_dma_owned_samples)='' /sys/bus/platform/devices/e8000000.ethernet/lyoko_emac_stats; /usr/bin/lyoko-pkg update; /usr/sbin/om-qtnctl available; echo QTN_MUTATION_RC=$?; /usr/sbin/om-rtlctl available; echo RTL_MUTATION_RC=$?; /usr/sbin/om-qtn-step available; echo QTN_STEP_RC=$?; test "$(/usr/sbin/om-qtn-step list | wc -l)" = 12; echo QTN_STEP_LIST_RC=$?; grep -q ''ifconfig_bin=.*bin/ifconfig'' /usr/sbin/om-qtn-step; echo QTN_STEP_PATH_RC=$?; /usr/sbin/om-radioctl contract 2g | grep -q ''"ssid_broadcast"''; echo RTL_EXPANDED_CONTRACT_RC=$?; /usr/sbin/om-radioctl contract 5g | grep -q ''"ssid_broadcast".*"current":true''; echo QTN_BOOLEAN_JSON_RC=$?; /usr/sbin/om-radioctl contract 5g | grep -q ''"multicast_rate"''; echo QTN_READBACK_CONTRACT_RC=$?; grep -q ''setting-source'' /usr/share/openmitrastar/web/dashboard.html && grep -q ''qtn-dynamic-control-disabled-after-management-loss'' /usr/sbin/om-radioctl && echo OMF272_UI_CONTRACT_PASS'
$probeRc = $LASTEXITCODE
$probeText = ($probe | Out-String)
if ($probeRc -ne 0 -or
    $probeText -notmatch '(?m)^napi_weight=128\s*$' -or
    $probeText -notmatch '(?m)^irq_count=[0-9]+\s*$' -or
    $probeText -notmatch '(?m)^napi_polls=[0-9]+\s*$' -or
    $probeText -notmatch '(?m)^rx_head_dma_owned_samples=[0-9]+\s*$' -or
    $probeText -notmatch 'LYOKO_PKG_UPDATE_PASS' -or
    $probeText -notmatch '(?m)^QTN_MUTATION_RC=1\s*$' -or
    $probeText -notmatch '(?m)^RTL_MUTATION_RC=0\s*$' -or
    $probeText -notmatch '(?m)^QTN_STEP_RC=0\s*$' -or
    $probeText -notmatch '(?m)^QTN_STEP_LIST_RC=0\s*$' -or
    $probeText -notmatch '(?m)^QTN_STEP_PATH_RC=0\s*$' -or
    $probeText -notmatch '(?m)^RTL_EXPANDED_CONTRACT_RC=0\s*$' -or
    $probeText -notmatch '(?m)^QTN_BOOLEAN_JSON_RC=0\s*$' -or
    $probeText -notmatch '(?m)^QTN_READBACK_CONTRACT_RC=0\s*$' -or
    $probeText -notmatch 'OMF272_UI_CONTRACT_PASS') {
    $probeText | Set-Content -LiteralPath (Join-Path $runDir "live-integrated-probe.log") -Encoding ascii
    throw "F272 live integrated contract failed; inspect $(Join-Path $runDir 'live-integrated-probe.log')"
}

[ordered]@{
    schema = "openmitrastar.f272-direct-promotion/v1"
    status = "PASS"
    target = "mtd4/linux_live"
    candidate_sha256 = $expectedSha256
    full_slot_crc32 = [string]$manifest.artifacts.full_slot.crc32
    erase_bytes = "0x005e0000"
    preserved_store_bytes = "0x001c0000"
    platform_gate = $platformGate
    physical_campaign = "NOT_RUN"
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $runDir "status.json") -Encoding ascii

Write-Output "OMF272_MTD4_FLASH_GATE_PASS=1 status=$(Join-Path $runDir 'status.json')"
