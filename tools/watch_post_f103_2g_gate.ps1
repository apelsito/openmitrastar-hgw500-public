[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RouterHost = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "$env:USERPROFILE\.ssh\id_ed25519",
    [string]$OracleHost = "192.168.1.63",
    [string]$OracleUser = "AELITA",
    [string]$ControllerUrl = "http://192.168.1.43:8008/speed.bin",
    [ValidateRange(5, 300)]
    [int]$PollSeconds = 15,
    [ValidateRange(60, 43200)]
    [int]$MaxWaitSeconds = 21600,
    [double]$MinDownloadMbps = 12.0,
    [double]$MinUploadMbps = 18.0,
    [switch]$AllowSshWithoutF103FlashMarker,
    [switch]$Once,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f103-postflash-autogate-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StatusPath = Join-Path $OutputDir "status.json"

function Write-Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f103-postflash-2g-autogate/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        router_host = $RouterHost
        oracle_host = $OracleHost
        poll_seconds = $PollSeconds
        max_wait_seconds = $MaxWaitSeconds
        min_download_mbps = $MinDownloadMbps
        min_upload_mbps = $MinUploadMbps
        require_f103_flash_marker = -not [bool]$AllowSshWithoutF103FlashMarker
        touches_uart = $false
        flashes = $false
    }
    foreach ($key in $Extra.Keys) { $payload[$key] = $Extra[$key] }
    $payload | ConvertTo-Json -Depth 10 | Set-Content -Encoding ascii -LiteralPath $StatusPath
}

function Test-Tcp22([string]$HostName) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, 22, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(900, $false)
        if (-not $ok) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Get-Mbps($Node) {
    if ($null -eq $Node) { return $null }
    $speed = $Node.speed_Bps
    if ($null -eq $speed) { return $null }
    return [Math]::Round(([double]$speed * 8.0 / 1000000.0), 3)
}

function Get-JsonProp($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $Default }
    return $prop.Value
}

function Invoke-SshProof() {
    $proofLog = Join-Path $OutputDir "ssh-proof.log"
    $knownHosts = ".codex_tmp\f103_postflash_known_hosts"
    $remote = @'
echo F103_POSTFLASH_PROBE
uname -a
printf 'POLLFB_COUNT='; dmesg | grep -c 'poll-fallback enabled' || true
printf 'RXRESTART_COUNT='; dmesg | grep -c 'OMEMAC rx restart' || true
printf 'SWENC='; cat /sys/module/rtl8192ee/parameters/swenc 2>/dev/null || echo MISSING
printf 'MCS7='; cat /sys/module/rtl8192ee/parameters/hgw500_force_data_mcs7 2>/dev/null || echo MISSING
printf 'RECLAIM_POLL='; cat /sys/module/rtl_pci/parameters/hgw500_tx_reclaim_poll 2>/dev/null || echo MISSING
printf 'QUEUE_GUARD='; cat /sys/module/rtl_pci/parameters/hgw500_tx_queue_guard 2>/dev/null || echo MISSING
dmesg | grep -E 'OMEMAC|poll-fallback|rx restart|wlan0|hostapd|rtl' | tail -n 120
'@
    $output = & (Join-Path $Root "tools\ssh_openmitrastar_510.ps1") `
        -HostAddress $RouterHost `
        -User $RouterUser `
        -KeyPath $RouterKey `
        -KnownHostsPath $knownHosts `
        -RemoteCommand $remote 2>&1
    $rc = $LASTEXITCODE
    $output | Set-Content -Encoding utf8 -LiteralPath $proofLog
    return [ordered]@{
        rc = $rc
        log = $proofLog
        swenc_disabled = (($output -join "`n") -match "SWENC=N")
        mcs7_forced = (($output -join "`n") -match "MCS7=Y")
        reclaim_poll = (($output -join "`n") -match "RECLAIM_POLL=Y")
        queue_guard = (($output -join "`n") -match "QUEUE_GUARD=Y")
    }
}

function Invoke-SpeedGate() {
    $twoGDir = Join-Path $OutputDir "two-g"
    New-Item -ItemType Directory -Force -Path $twoGDir | Out-Null
    $stdout = Join-Path $OutputDir "aelita-2g-speed.stdout.log"
    $stderr = Join-Path $OutputDir "aelita-2g-speed.stderr.log"
    $args = @(
        (Join-Path $Root "tools\run_aelita_2g_wpa2_speed_router_probe.py"),
        "--router-host", $RouterHost,
        "--router-user", $RouterUser,
        "--router-key", $RouterKey,
        "--oracle-host", $OracleHost,
        "--oracle-user", $OracleUser,
        "--controller-url", $ControllerUrl,
        "--traffic-direction", "both",
        "--output-dir", $twoGDir
    )
    $output = & python @args 2>&1
    $rc = $LASTEXITCODE
    $output | Set-Content -Encoding utf8 -LiteralPath $stdout
    "" | Set-Content -Encoding utf8 -LiteralPath $stderr
    $summaryPath = Join-Path $twoGDir "summary.json"
    $summary = if (Test-Path -LiteralPath $summaryPath -PathType Leaf) {
        Get-Content -Raw -LiteralPath $summaryPath | ConvertFrom-Json
    } else {
        $null
    }
    $download = Get-JsonProp $summary "controller_download" $null
    $upload = Get-JsonProp $summary "controller_upload" $null
    $downloadMbps = Get-Mbps $download
    $uploadMbps = Get-Mbps $upload
    $downloadPass = if ($download) { [bool](Get-JsonProp $download "pass" $false) } else { $false }
    $uploadPass = if ($upload) { [bool](Get-JsonProp $upload "pass" $false) } else { $false }
    $recommend = "UNKNOWN"
    if ($rc -ne 0 -or -not $downloadPass -or -not $uploadPass) {
        $recommend = "F103_GATE_FAIL_RETRY_OR_DIAGNOSE"
    } elseif ($downloadMbps -lt $MinDownloadMbps -or $uploadMbps -lt $MinUploadMbps) {
        $recommend = "F104_RECOMMENDED_LOW_THROUGHPUT"
    } else {
        $recommend = "F103_ACCEPT_FOR_2G_BASELINE"
    }
    return [ordered]@{
        rc = $rc
        stdout = $stdout
        stderr = $stderr
        summary = $summaryPath
        download_mbps = $downloadMbps
        upload_mbps = $uploadMbps
        download_pass = $downloadPass
        upload_pass = $uploadPass
        recommendation = $recommend
    }
}

function Get-GoalDecision() {
    $raw = & (Join-Path $Root "tools\aelita_radio_goal_decision.ps1") 2>$null
    $exitVar = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
    $rc = if ($exitVar) { [int]$exitVar.Value } else { 0 }
    if ($rc -ne 0 -or -not $raw) { return $null }
    try {
        return ($raw -join "`n") | ConvertFrom-Json
    } catch {
        return $null
    }
}

$deadline = [DateTime]::UtcNow.AddSeconds($MaxWaitSeconds)
Write-Status "waiting_ssh" "waiting for router SSH after F103 flash"
while ([DateTime]::UtcNow -lt $deadline) {
    $tcp22 = Test-Tcp22 $RouterHost
    $goalDecision = Get-GoalDecision
    $decision = Get-JsonProp $goalDecision "decision" $null
    $flashMarkerOk = ($decision -eq "F103_FLASHED_VERIFY_2G")
    $mayRunGate = $tcp22 -and ($flashMarkerOk -or $AllowSshWithoutF103FlashMarker)
    if ($mayRunGate) {
        Write-Status "ssh_seen" "router SSH is reachable; running proof"
        $proof = Invoke-SshProof
        if ($proof.rc -ne 0) {
            Write-Status "ssh_proof_failed" "router SSH reachable but proof failed" @{ ssh_proof = $proof }
            exit 2
        }
        Write-Status "ssh_proof_pass" "router SSH proof passed; running AELITA 2.4 speed gate" @{ ssh_proof = $proof }
        $speed = Invoke-SpeedGate
        $state = if ($speed.recommendation -eq "F103_ACCEPT_FOR_2G_BASELINE") {
            "f103_2g_accept"
        } elseif ($speed.recommendation -eq "F104_RECOMMENDED_LOW_THROUGHPUT") {
            "f104_recommended"
        } else {
            "speed_gate_failed"
        }
        Write-Status $state "post-F103 2.4 gate completed" @{
            ssh_proof = $proof
            speed_gate = $speed
            f104_command = "powershell -NoProfile -ExecutionPolicy Bypass -File tools\arm_f104_2g_be_guard16_flash.ps1 -Execute"
        }
        if ($state -eq "f103_2g_accept") { exit 0 }
        if ($state -eq "f104_recommended") { exit 3 }
        exit 4
    }
    if ($Once) {
        Write-Status "waiting_ssh_once_noop" "post-F103 gate conditions not met in one-shot check" @{
            tcp22 = $tcp22
            goal_decision = $decision
            flash_marker_ok = $flashMarkerOk
            allow_ssh_without_f103_flash_marker = [bool]$AllowSshWithoutF103FlashMarker
        }
        exit 1
    }
    Write-Status "waiting_ssh" "router SSH not reachable yet; post-SSH 2.4 gate remains armed" @{
        tcp22 = $tcp22
        goal_decision = $decision
        flash_marker_ok = $flashMarkerOk
        allow_ssh_without_f103_flash_marker = [bool]$AllowSshWithoutF103FlashMarker
    }
    Start-Sleep -Seconds $PollSeconds
}

Write-Status "timeout_waiting_ssh" "router SSH did not become reachable before timeout"
exit 1
