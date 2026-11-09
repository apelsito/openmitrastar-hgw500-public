[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [string]$OracleHost = "192.168.1.63",
    [string]$OracleUser = "AELITA",
    [string]$ControllerUrl = "http://192.168.1.43:8008/speed.bin",
    [ValidateSet("auto", "tftp", "uart-ymodem")][string]$Transport = "auto"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f247-device-bound"
$candidate = Join-Path $build "openmitrastar-linux510-f247-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin"
$manifestPath = Join-Path $build "manifest.json"
$rollbackTool = Join-Path $root "tools\restore_f222_mtd4_from_f247.ps1"
$requiredAck = "OPENMITRASTAR_F247_FULL_CYCLE_8BD78674"
$expectedSha = "8bd786744ca618a012f585a4e2f5de50ea7850ea91d7d04c076fd9a753cbda12"

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
$controller = [Uri]$ControllerUrl
$controllerPort = if ($controller.IsDefaultPort) { if ($controller.Scheme -eq "https") { 443 } else { 80 } } else { $controller.Port }
$preflight = [ordered]@{
    schema = "openmitrastar.f247-full-cycle-preflight/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    target = "mtd4/linux_live"
    candidate_sha256 = $expectedSha
    candidate_contract = (Test-Path $candidate) -and ((Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant() -eq $expectedSha) -and $manifest.schema -eq "openmitrastar.f247-integrated-physical-test-candidate/v1" -and $manifest.candidate_eligible -eq $true -and $manifest.flash_supported -eq $true
    rollback_artifact = (Test-Path $rollbackTool) -and (Test-Path "$HOME\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f222-device-bound\openmitrastar-linux510-f222-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin")
    router_ssh = Test-Tcp $RouterHost 22
    oracle_ssh = Test-Tcp $OracleHost 22
    controller_tcp = Test-Tcp $controller.Host $controllerPort
    uart_present = [IO.Ports.SerialPort]::GetPortNames() -contains $Port
    sequence = @("flash", "platform", "packages", "radio-control", "2g-three-run", "5g-32m-120s", "final-health")
    stop_on_first_failure = $true
    automatic_reflash = $false
}
$preflight | ConvertTo-Json -Depth 5
if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing F247 full cycle: exact -Ack is required" }
foreach ($required in ("candidate_contract", "rollback_artifact", "router_ssh", "oracle_ssh", "controller_tcp", "uart_present")) {
    if (-not $preflight[$required]) { throw "F247 preflight failed before flash: $required" }
}

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$output = Join-Path $root "outputs\f3-certification\f247-full-cycle-$stamp"
New-Item -ItemType Directory -Force -Path $output | Out-Null
$phase = "flash"
try {
    & pwsh.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\promote_f247_mtd4_direct.ps1") -Execute -Ack OPENMITRASTAR_F247_INTEGRATED_8BD78674 -Port $Port -RouterHost $RouterHost -AelitaHost $OracleHost -Transport $Transport
    if ($LASTEXITCODE -ne 0) { throw "F247 flash/platform gate failed" }

    $phase = "packages"
    & python (Join-Path $root "tools\run_f247_package_catalog_physical_gate.py") --execute --ack OPENMITRASTAR_F247_PACKAGE_CATALOG_PHYSICAL --host $RouterHost --expected-version lyoko-foundation-4.9-f245-device --known-hosts (Join-Path $build "known_hosts.f247") --output-dir (Join-Path $output "packages")
    if ($LASTEXITCODE -ne 0) { throw "F247 package catalog gate failed" }

    $phase = "radio-control"
    & pwsh.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\run_f247_dual_radio_control_postflash_gate.ps1") -Execute -Ack OPENMITRASTAR_F247_DUAL_RADIO_CONTROL_PHYSICAL -RouterHost $RouterHost -KnownHostsPath (Join-Path $build "known_hosts.f247") -OutputDir (Join-Path $output "radio-control")
    if ($LASTEXITCODE -ne 0) { throw "F247 dual-radio control gate failed" }

    $phase = "radio2"
    & pwsh.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "tools\run_f247_physical_campaign.ps1") -Execute -Ack OPENMITRASTAR_F247_RXRING256_PHYSICAL -RouterHost $RouterHost -OracleHost $OracleHost -OracleUser $OracleUser -ControllerUrl $ControllerUrl -OutputDir (Join-Path $output "radio2")
    if ($LASTEXITCODE -ne 0) { throw "F247 2.4 GHz campaign failed" }

    $phase = "radio5"
    $radio5Dir = Join-Path $output "radio5"
    & python (Join-Path $root "tools\run_f151_5g_bridge_trial.py") --execute --ack OPENMITRASTAR_F151_5G_BRIDGE_TRIAL --router-host $RouterHost --seconds 120 --transfer-mib 32 --transfer-timeout-seconds 90 --persistent-bridge --expected-qdrv-sha 0ef6cac2fe68ba62dcba21c4878b9d4697d8e6560579bf74f3ed9a5ae09c0dff --expected-wlan-sha f4f6099b43dd675dd44e7021374f1ea2f4380a4d9d9fd81b1d35ea411984897f --output-dir $radio5Dir
    if ($LASTEXITCODE -ne 0) { throw "F247 5 GHz regression failed" }
    $windowsResult = Get-ChildItem -LiteralPath $radio5Dir -Filter "windows-*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $windowsResult) { throw "F247 5 GHz Windows evidence missing" }
    $radio5 = Get-Content -Raw -LiteralPath $windowsResult.FullName | ConvertFrom-Json
    if ([long]$radio5.test.ap_to_client.bytes -lt 33554432 -or [long]$radio5.test.client_to_ap.bytes -lt 33554432 -or [int]$radio5.test.soak.disconnects -ne 0) {
        throw "F247 5 GHz gate did not transfer 32 MiB per direction with zero disconnects"
    }

    $phase = "final-health"
    $ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
    $health = & $ssh -i "$env:USERPROFILE\.ssh\id_ed25519" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$(Join-Path $build 'known_hosts.f247')" -o LogLevel=ERROR "root@$RouterHost" 'test "$(cat /run/openmitrastar/boot-state)" = ready; /usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 ping; /usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping; test "$(dmesg | grep -Eic "MuC:.*exception|MuC has halted|QMAC.*(fatal|halt)|DMA.*(fatal|error)|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|Misaligned Access|Machine Check")" = 0'
    $pongCount = @($health | Where-Object { $_ -eq "PONG" }).Count
    if ($LASTEXITCODE -ne 0 -or $pongCount -lt 2) { throw "F247 final health gate failed" }

    [ordered]@{schema="openmitrastar.f247-full-cycle/v1";status="PASS";candidate_sha256=$expectedSha;target="mtd4/linux_live";packages="PASS";radio_control="PASS";radio2="PASS";radio5="PASS";final_health="PASS";rollback="available-manual-F222-mtd4"} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output "result.json") -Encoding ascii
    Write-Output "OMF247_FULL_CYCLE_PASS=1 output=$output"
} catch {
    [ordered]@{schema="openmitrastar.f247-full-cycle/v1";status="FAIL";phase=$phase;error=$_.Exception.Message;automatic_reflash=$false;rollback_tool=$rollbackTool} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output "result.json") -Encoding ascii
    throw
}
