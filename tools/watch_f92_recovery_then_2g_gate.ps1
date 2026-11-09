[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$WatchDir = "",
    [string]$RouterHost = "192.168.1.90",
    [string]$OracleHost = "192.168.1.63",
    [string]$OracleUser = "AELITA",
    [string]$ControllerUrl = "http://192.168.1.43:8008/speed.bin",
    [ValidateRange(30, 21600)]
    [int]$TimeoutSeconds = 7200,
    [ValidateRange(5, 120)]
    [int]$PollSeconds = 10
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $WatchDir) {
    $WatchDir = Get-ChildItem (Join-Path $Root "outputs\flash-watch") -Directory |
        Where-Object { $_.Name -like "f92-armed-recovery-*" -or $_.Name -like "f92-2g-ht40sgi-fixedsize-after-f90-*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $WatchDir -or -not (Test-Path -LiteralPath $WatchDir -PathType Container)) {
    throw "F92 watch directory not found"
}
$WatchDir = [IO.Path]::GetFullPath($WatchDir)
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$OutDir = Join-Path $Root "outputs\postflash\f92-2g-gate-$stamp"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$ResultPath = Join-Path $OutDir "result.json"
$RouterKey = Join-Path $Root ".codex_tmp\openmitrastar_ramssh_client_ed25519"
$KnownHosts = Join-Path $Root ".codex_tmp\router_known_hosts_f92_gate"
$Ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"

function Write-Result([hashtable]$Payload) {
    $Payload.updated_at = (Get-Date).ToString("o")
    $Payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $ResultPath
}

function Invoke-Router([string]$RemoteCommand, [int]$Timeout = 20) {
    & $Ssh -i $RouterKey `
        -o "ConnectTimeout=$([Math]::Min($Timeout, 8))" `
        -o BatchMode=yes `
        -o IdentitiesOnly=yes `
        -o StrictHostKeyChecking=no `
        -o "UserKnownHostsFile=$KnownHosts" `
        -o HostKeyAlgorithms=+ssh-rsa `
        -o PubkeyAcceptedAlgorithms=+ssh-rsa `
        -o LogLevel=ERROR `
        "root@$RouterHost" $RemoteCommand
}

function Test-RouterSsh {
    $out = Invoke-Router "echo OMSSH_OK; uname -r" 8 2>$null
    return ($LASTEXITCODE -eq 0 -and ($out -join "`n") -match "OMSSH_OK")
}

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$statusPath = Join-Path $WatchDir "status.json"
$state = "waiting"
while ([DateTime]::UtcNow -lt $deadline) {
    $status = $null
    if (Test-Path -LiteralPath $statusPath -PathType Leaf) {
        try { $status = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json } catch { $status = $null }
    }
    if ($status -and [string]$status.state -eq "pass") {
        $state = "flash_pass"
        break
    }
    if ($status -and [string]$status.state -match "failed|uart_rx_zero") {
        Write-Result @{
            schema = "openmitrastar.f92-postflash-2g-gate/v1"
            status = "FLASH_WATCHER_FAILED"
            watch_dir = $WatchDir
            flash_state = [string]$status.state
            flash_message = [string]$status.message
        }
        throw "F92 flash watcher failed: $($status.state)"
    }
    if (Test-RouterSsh) {
        $state = "ssh_seen"
        break
    }
    Start-Sleep -Seconds $PollSeconds
}
if ($state -eq "waiting") {
    Write-Result @{
        schema = "openmitrastar.f92-postflash-2g-gate/v1"
        status = "TIMEOUT_WAITING_FLASH_OR_SSH"
        watch_dir = $WatchDir
    }
    throw "timeout waiting for F92 flash pass or SSH"
}

$sshStatus = Join-Path $OutDir "router-ssh-radio-status.txt"
Invoke-Router @'
echo SECTION_UNAME
uname -a
echo SECTION_UPTIME
uptime
echo SECTION_IW
iw dev 2>/dev/null || true
echo SECTION_HOSTAPD
/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status 2>/dev/null || true
echo SECTION_PARAMS
for f in /sys/module/rtl8192ee/parameters/hgw500_* /sys/module/rtl_pci/parameters/*; do [ -f "$f" ] && printf "%s=" "$f" && cat "$f"; done
echo SECTION_DMESG
dmesg | grep -E "OMRADIO|OMNETWORK|OMSSH|OMRTLRA|rtl8192|wlan0|hostapd" | tail -n 220
'@ 25 | Set-Content -Encoding utf8 -LiteralPath $sshStatus

$speedDir = Join-Path $OutDir "aelita-2g-speed"
$probeArgs = @(
    ".\tools\run_aelita_2g_wpa2_speed_router_probe.py",
    "--router-host", $RouterHost,
    "--router-user", "root",
    "--router-key", ".\.codex_tmp\openmitrastar_ramssh_client_ed25519",
    "--oracle-host", $OracleHost,
    "--oracle-user", $OracleUser,
    "--controller-url", $ControllerUrl,
    "--soak-seconds", "5",
    "--interval", "2",
    "--wait-result", "180",
    "--child-timeout", "220",
    "--output-dir", $speedDir
)
& python @probeArgs > (Join-Path $OutDir "aelita-speed.stdout.log") 2> (Join-Path $OutDir "aelita-speed.stderr.log")
$probeRc = $LASTEXITCODE

$rateLog = Join-Path $OutDir "router-dmesg-omrtlra.log"
Invoke-Router "dmesg | grep OMRTLRA || true" 15 | Set-Content -Encoding utf8 -LiteralPath $rateLog
$rateJson = Join-Path $OutDir "rate-trace-analysis.json"
& python .\tools\analyze_rtl8192ee_tx_rate_trace.py $rateLog --output $rateJson > (Join-Path $OutDir "rate-trace-analysis.stdout.log") 2> (Join-Path $OutDir "rate-trace-analysis.stderr.log")
$rateRc = $LASTEXITCODE

Write-Result @{
    schema = "openmitrastar.f92-postflash-2g-gate/v1"
    status = "PASS"
    watch_dir = $WatchDir
    reached_by = $state
    router_status = $sshStatus
    aelita_probe_rc = $probeRc
    aelita_speed_dir = $speedDir
    rate_trace_rc = $rateRc
    rate_trace_log = $rateLog
    rate_trace_analysis = $rateJson
}
Write-Host "OMF92_POSTFLASH_2G_GATE_DONE result=$ResultPath"
