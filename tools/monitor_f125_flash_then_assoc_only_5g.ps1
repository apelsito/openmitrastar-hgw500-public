[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RunDir = "",
    [int]$TimeoutSeconds = 21600,
    [int]$PollSeconds = 10,
    [string]$HostAddress = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "/workspace/user-home\Desktop\MitraStar\.codex_tmp\openmitrastar_ramssh_client_ed25519",
    [string]$OracleHost = "192.168.1.63",
    [string]$OracleUser = "AELITA",
    [ValidateLength(1, 32)]
    [string]$TestSsid = "OpenMitraStar-5G-DIAG",
    [ValidateLength(1, 32)]
    [string]$RestoreSsid = "MOVISTAR-WIFI6-A348",
    [ValidateRange(60, 600)]
    [int]$AssocTimeoutSeconds = 180,
    [ValidateRange(30, 300)]
    [int]$RadioReadyTimeoutSeconds = 120,
    [ValidateRange(1, 200)]
    [double]$Min2gMbps = 20.0,
    [ValidateSet("download", "upload", "both")]
    [string]$TwoGTrafficDirection = "both",
    [switch]$Skip2gGateFirst,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$F125Sha256 = "d7118a035628b612deba33ea9b8fa43e52da6faf9dbd07aecb26f91789ae370e"
$BuildDir = Join-Path $Root "work\mission-state\q3-persistent-composite-f125-5g-assoc-window-guard-from-f124\build"
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f125-5g-assoc-only-monitor-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$statusOut = Join-Path $OutputDir "monitor-status.json"
$logPath = Join-Path $OutputDir "monitor.log"

function Test-TcpPort([string]$HostName, [int]$Port, [int]$Timeout = 3) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne([TimeSpan]::FromSeconds($Timeout))
        if (-not $ok) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Read-JsonFile([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $null }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

function Test-ProcessAlive([AllowNull()][object]$PidValue) {
    if ($null -eq $PidValue) { return $false }
    try {
        $pidInt = [int]$PidValue
    } catch {
        return $false
    }
    return [bool](Get-Process -Id $pidInt -ErrorAction SilentlyContinue)
}

function Write-MonitorStatus(
    [string]$State,
    [string]$Message,
    [AllowNull()][object]$WatcherStatus = $null,
    [AllowNull()][object]$FlashEvidence = $null,
    [string]$GateResult = ""
) {
    [ordered]@{
        schema = "openmitrastar.f125-flash-then-5g-assoc-only-monitor/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        run_dir = $RunDir
        output_dir = $OutputDir
        process_id = $PID
        host = $HostAddress
        candidate = "f125-5g-assoc-window-guard-from-f124"
        candidate_sha256 = $F125Sha256
        policy = [ordered]@{
            serial_uart = $false
            router_flash_writes = $false
            boot_setting_writes = $false
            two_g_gate_first = -not [bool]$Skip2gGateFirst
            two_g_l3_traffic = -not [bool]$Skip2gGateFirst
            association_only = $true
            five_g_l3_traffic = $false
        }
        min_2g_mbps = $Min2gMbps
        two_g_traffic_direction = $TwoGTrafficDirection
        test_ssid = $TestSsid
        restore_ssid = $RestoreSsid
        assoc_timeout_seconds = $AssocTimeoutSeconds
        radio_ready_timeout_seconds = $RadioReadyTimeoutSeconds
        watcher = $WatcherStatus
        flash_evidence = $FlashEvidence
        gate_result = $GateResult
    } | ConvertTo-Json -Depth 10 | Set-Content -Encoding ascii -LiteralPath $statusOut
}

function Get-LatestF125RunDir {
    $latest = @(Get-ChildItem -LiteralPath (Join-Path $Root "outputs\flash-watch") -Directory -Filter "f125-5g-assoc-window-guard*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1)
    if ($latest.Count -gt 0) { return $latest[0].FullName }
    return ""
}

function Get-F125FlashEvidence([AllowNull()][object]$Status) {
    $stdoutPath = ""
    if ($Status -and ($Status.PSObject.Properties.Name -contains "stdout")) {
        $stdoutPath = [string]$Status.stdout
    }
    if (-not $stdoutPath -and $RunDir) {
        $stdoutPath = Join-Path $RunDir "flash-watch.stdout.log"
    }
    $text = ""
    if ($stdoutPath -and (Test-Path -LiteralPath $stdoutPath -PathType Leaf)) {
        $text = Get-Content -LiteralPath $stdoutPath -Raw
    }

    $evidenceDir = ""
    $resultPath = ""
    if ($text -match "OMQ3_F45_FLASH_EVIDENCE_DIR=([^\r\n]+)") {
        $evidenceDir = $Matches[1].Trim()
        $candidateResult = Join-Path $evidenceDir "result.json"
        if (Test-Path -LiteralPath $candidateResult -PathType Leaf) {
            $resultPath = $candidateResult
        }
    }
    if (-not $resultPath -and $text -match "OMQ3_F45_RADIO5_POWERSELECT_NONFATAL_OPENLAB_MTD4_FLASH_ONE_SHOT_PASS=1[^\r\n]*result=([^\r\n]+)") {
        $candidateResult = $Matches[1].Trim()
        if (-not [IO.Path]::IsPathRooted($candidateResult)) {
            $candidateResult = Join-Path $Root $candidateResult
        }
        if (Test-Path -LiteralPath $candidateResult -PathType Leaf) {
            $resultPath = $candidateResult
            $evidenceDir = Split-Path -Parent $candidateResult
        }
    }

    $result = Read-JsonFile $resultPath
    $pass = $false
    if ($result) {
        $pass = (
            [string]$result.status -eq "PASS" -and
            [string]$result.candidate_sha256 -eq $F125Sha256
        )
    }
    if (-not $pass -and $text -match "OMQ3_F45_RADIO5_POWERSELECT_NONFATAL_OPENLAB_MTD4_FLASH_ONE_SHOT_PASS=1[^\r\n]*candidate=$F125Sha256") {
        $pass = $true
    }
    $uartLogPath = ""
    if ($text -match "log=([^\r\n]+\.log)") {
        $uartLogPath = $Matches[1].Trim()
    }
    $uartLogBytes = $null
    if ($uartLogPath -and (Test-Path -LiteralPath $uartLogPath -PathType Leaf)) {
        $uartLogBytes = [int64](Get-Item -LiteralPath $uartLogPath).Length
    }
    $blindSpaceCount = 0
    $blindMatches = @([regex]::Matches($text, "OMQ3_F45_AUTOBREAK_BLIND_SPACE_SENT=(\d+)"))
    if ($blindMatches.Count -gt 0) {
        $blindSpaceCount = [int64]$blindMatches[-1].Groups[1].Value
    }
    $uartRxZero = [bool](
        $text -match "UART_RX_SILENT_ZERO_BYTES|OMQ3_F45_AUTOBREAK_UART_RX_SILENT_ZERO_BYTES" -or
        ($uartLogPath -and $uartLogBytes -eq 0 -and $blindSpaceCount -ge 20)
    )

    return [ordered]@{
        pass = $pass
        stdout = $stdoutPath
        uart_log = $uartLogPath
        uart_log_bytes = $uartLogBytes
        blind_space_count = $blindSpaceCount
        evidence_dir = $evidenceDir
        result = $resultPath
        one_shot_pass_marker = [bool]($text -match "OMQ3_F45_RADIO5_POWERSELECT_NONFATAL_OPENLAB_MTD4_FLASH_ONE_SHOT_PASS=1")
        topaz_seen = [bool]($text -match "OMQ3_F45_AUTOBREAK_TOPAZ_READY=1|topaz>")
        uart_rx_zero = $uartRxZero
    }
}

function Invoke-RouterCommand([string]$Remote, [string]$StdoutPath, [string]$StderrPath, [int]$Timeout) {
    $ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
    $sshKeyscan = Join-Path $env:WINDIR "System32\OpenSSH\ssh-keyscan.exe"
    $knownHosts = Join-Path $OutputDir "router_known_hosts"
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $scanText = & $sshKeyscan -T 5 -t ed25519,rsa $HostAddress 2>&1
    $ErrorActionPreference = $previousErrorActionPreference
    $scan = @($scanText |
        ForEach-Object { [string]$_ } |
        Where-Object { $_ -and -not $_.StartsWith("#") })
    if ($scan) {
        $scan | Set-Content -Encoding ascii -LiteralPath $knownHosts
    }

    $sshArgs = @(
        "-i", $RouterKey,
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=$knownHosts",
        "-o", "HostKeyAlgorithms=+ssh-rsa",
        "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa",
        "-o", "LogLevel=ERROR",
        "$RouterUser@$HostAddress",
        $Remote
    )
    $proc = Start-Process -FilePath $ssh -ArgumentList $sshArgs -NoNewWindow -PassThru `
        -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath
    if (-not $proc.WaitForExit($Timeout * 1000)) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        return 124
    }
    $proc.Refresh()
    return [int]$proc.ExitCode
}

function Invoke-2gPreflightGate([string]$GateDir) {
    $twoGDir = Join-Path $GateDir "two-g-preflight"
    New-Item -ItemType Directory -Force -Path $twoGDir | Out-Null
    $twoGOut = Join-Path $GateDir "two-g-preflight.stdout.log"
    $twoGErr = Join-Path $GateDir "two-g-preflight.stderr.log"
    $twoGArgs = @(
        (Join-Path $PSScriptRoot "run_aelita_2g_wpa2_speed_router_probe.py"),
        "--router-host", $HostAddress,
        "--router-user", $RouterUser,
        "--router-key", $RouterKey,
        "--oracle-host", $OracleHost,
        "--oracle-user", $OracleUser,
        "--traffic-direction", $TwoGTrafficDirection,
        "--output-dir", $twoGDir
    )
    $proc = Start-Process -FilePath "python" -ArgumentList $twoGArgs -NoNewWindow -PassThru `
        -RedirectStandardOutput $twoGOut -RedirectStandardError $twoGErr
    $timeoutSeconds = 720
    if (-not $proc.WaitForExit($timeoutSeconds * 1000)) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        return [ordered]@{
            requested = $true
            skipped = $false
            exit_code = 124
            pass = $false
            speed_mbps = $null
            reason = "two_g_preflight_timeout"
            output_dir = $twoGDir
            stdout = $twoGOut
            stderr = $twoGErr
            summary = Join-Path $twoGDir "summary.json"
        }
    }
    $proc.Refresh()
    $summaryPath = Join-Path $twoGDir "summary.json"
    $summary = Read-JsonFile $summaryPath
    $speedMbps = $null
    $downloadMbps = $null
    $uploadMbps = $null
    $download = $null
    $upload = $null
    $routerHealthGate = $null
    if ($summary) {
        if ($summary.PSObject.Properties.Name -contains "controller_download") {
            $download = $summary.controller_download
        }
        if ($summary.PSObject.Properties.Name -contains "controller_upload") {
            $upload = $summary.controller_upload
        }
        if ($summary.PSObject.Properties.Name -contains "router_health_gate") {
            $routerHealthGate = $summary.router_health_gate
        }
    }
    if ($TwoGTrafficDirection -in @("download", "both") -and $download -and $download.PSObject.Properties.Name -contains "speed_Bps") {
        $downloadMbps = [Math]::Round(([double]$download.speed_Bps * 8.0) / 1000000.0, 2)
    }
    if ($TwoGTrafficDirection -in @("upload", "both") -and $upload -and $upload.PSObject.Properties.Name -contains "speed_Bps") {
        $uploadMbps = [Math]::Round(([double]$upload.speed_Bps * 8.0) / 1000000.0, 2)
    }
    $requestedSpeeds = @()
    if ($TwoGTrafficDirection -in @("download", "both")) { $requestedSpeeds += $downloadMbps }
    if ($TwoGTrafficDirection -in @("upload", "both")) { $requestedSpeeds += $uploadMbps }
    $validSpeeds = @($requestedSpeeds | Where-Object { $null -ne $_ })
    if ($validSpeeds.Count -gt 0) {
        $speedMbps = ($validSpeeds | Measure-Object -Minimum).Minimum
    }
    $childPass = [bool]($proc.ExitCode -eq 0)
    $directionPass = $true
    if ($TwoGTrafficDirection -in @("download", "both")) {
        $directionPass = [bool]($directionPass -and $download -and $download.pass)
    }
    if ($TwoGTrafficDirection -in @("upload", "both")) {
        $directionPass = [bool]($directionPass -and $upload -and $upload.pass)
    }
    $speedPass = [bool](
        $validSpeeds.Count -eq $requestedSpeeds.Count -and
        @($validSpeeds | Where-Object { [double]$_ -lt $Min2gMbps }).Count -eq 0
    )
    $routerHealthPass = [bool]($routerHealthGate -and $routerHealthGate.pass)
    return [ordered]@{
        requested = $true
        skipped = $false
        exit_code = [int]$proc.ExitCode
        pass = [bool]($childPass -and $directionPass -and $speedPass -and $routerHealthPass)
        child_pass = $childPass
        direction_pass = $directionPass
        speed_pass = $speedPass
        router_health_pass = $routerHealthPass
        speed_mbps = $speedMbps
        download_mbps = $downloadMbps
        upload_mbps = $uploadMbps
        min_mbps = $Min2gMbps
        traffic_direction = $TwoGTrafficDirection
        reason = if ($childPass -and $directionPass -and $speedPass -and $routerHealthPass) { "" } elseif (-not $directionPass) { "two_g_preflight_direction_failed" } elseif (-not $speedPass) { "two_g_preflight_speed_low" } elseif (-not $routerHealthPass) { "two_g_router_health_failed" } else { "two_g_preflight_child_failed" }
        router_health_gate = $routerHealthGate
        output_dir = $twoGDir
        stdout = $twoGOut
        stderr = $twoGErr
        summary = $summaryPath
    }
}

function Invoke-F125AssocOnlyGate([AllowNull()][object]$FlashEvidence) {
    $gateDir = Join-Path $OutputDir "assoc-only-gate"
    New-Item -ItemType Directory -Force -Path $gateDir | Out-Null
    $sshOut = Join-Path $gateDir "router-snapshot-and-radio5-start.stdout.log"
    $sshErr = Join-Path $gateDir "router-snapshot-and-radio5-start.stderr.log"
    $assocOut = Join-Path $gateDir "aelita-assoc-only.stdout.log"
    $assocErr = Join-Path $gateDir "aelita-assoc-only.stderr.log"
    $assocJson = Join-Path $gateDir "aelita-assoc-only-result.json"
    $gateJson = Join-Path $gateDir "result.json"

    $twoGPreflight = [ordered]@{
        requested = -not [bool]$Skip2gGateFirst
        skipped = [bool]$Skip2gGateFirst
        reason = if ($Skip2gGateFirst) { "skip_switch" } else { "" }
    }
    if (-not $Skip2gGateFirst) {
        $twoGPreflight = Invoke-2gPreflightGate $gateDir
    }
    if (-not $Skip2gGateFirst -and -not $twoGPreflight.pass) {
        [ordered]@{
            schema = "openmitrastar.f125-5g-assoc-only-gate/v1"
            terminal_state = "TWO_G_PREFLIGHT_FAIL"
            updated_at = (Get-Date).ToString("o")
            output_dir = $gateDir
            host = $HostAddress
            candidate_sha256 = $F125Sha256
            flash_evidence = $FlashEvidence
            two_g_preflight = $twoGPreflight
            radio5_ready = $false
            assoc_only = [ordered]@{
                requested = $true
                skipped = $true
                reason = "two_g_preflight_failed"
            }
            policy = [ordered]@{
                two_g_gate_first = $true
                five_g_association_only = $true
                five_g_l3_probe = $false
                five_g_traffic = $false
                static_ip = $false
                router_flash_writes = $false
                serial_uart = $false
            }
        } | ConvertTo-Json -Depth 12 | Set-Content -Encoding ascii -LiteralPath $gateJson
        return [ordered]@{
            terminal_state = "TWO_G_PREFLIGHT_FAIL"
            pass = $false
            path = $gateJson
        }
    }

    $remote = @'
echo OMF125_ASSOC_GATE_BEGIN
echo SECTION_UNAME
uname -a
echo SECTION_RELEASE
cat /etc/openmitrastar-release 2>/dev/null || true
echo SECTION_LINKS
ip -br link 2>/dev/null || ifconfig -a
echo SECTION_ADDRS
ip -br addr 2>/dev/null || ifconfig -a
echo SECTION_BR0
brctl show 2>/dev/null || true
ls -1 /sys/class/net/br0/brif 2>/dev/null || true
echo SECTION_RADIO5_STATE_BEFORE
for f in /run/openmitrastar/radio5g/*; do [ -r "$f" ] && printf '%s=' "$f" && cat "$f"; done
echo SECTION_RADIO5_START
if [ -x /usr/sbin/om-radio5-start ]; then
    /usr/sbin/om-radio5-start 2>&1 || true
else
    echo OMF125_OM_RADIO5_START_MISSING=1
fi
echo SECTION_RADIO5_READY_WAIT
i=0
while [ "$i" -lt 120 ]; do
    state=""
    [ -r /run/openmitrastar/radio5g/state ] && state=$(cat /run/openmitrastar/radio5g/state 2>/dev/null || true)
    printf 'OMF125_RADIO5_STATE_POLL i=%s state=%s\n' "$i" "$state"
    [ "$state" = ready ] && break
    dmesg | tail -n 80 | grep -q 'OMRADIO5_READY' && break
    i=$((i + 1))
    sleep 1
done
echo SECTION_RADIO5_STATE_AFTER
for f in /run/openmitrastar/radio5g/*; do [ -r "$f" ] && printf '%s=' "$f" && cat "$f"; done
echo SECTION_WIFI0
ifconfig wifi0 2>/dev/null || true
for p in /sys/class/net/wifi0/operstate /sys/class/net/wifi0/carrier /sys/class/net/wifi0/address; do
    [ -r "$p" ] && printf '%s=' "$p" && cat "$p"
done
echo SECTION_QTN_CONTROL
command -v iwconfig-qtn >/dev/null 2>&1 && /usr/sbin/iwconfig-qtn wifi0 2>&1 || true
command -v iwpriv-qtn >/dev/null 2>&1 && /usr/sbin/iwpriv-qtn wifi0 get_mode 2>&1 || true
command -v hostapd-cli-qtn >/dev/null 2>&1 && /usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 status 2>&1 || true
echo SECTION_DMESG_RADIO5
dmesg | grep -E 'OMRADIO5|OMQDRV|qdrv|wifi0|wlan|hostapd|AUTH|ASSOC|Misaligned|Oops|panic' | tail -n 260 || true
echo OMF125_ASSOC_GATE_END
'@

    $sshRc = Invoke-RouterCommand $remote $sshOut $sshErr ([Math]::Max(180, $RadioReadyTimeoutSeconds + 90))
    $sshText = if (Test-Path -LiteralPath $sshOut) { [string](Get-Content -LiteralPath $sshOut -Raw) } else { "" }
    $sshOk = [bool]($sshRc -eq 0 -and $sshText.Contains("OMF125_ASSOC_GATE_BEGIN") -and $sshText.Contains("OMF125_ASSOC_GATE_END"))
    $radioReady = [bool](
        $sshText -match "OMF125_RADIO5_STATE_POLL[^\r\n]*state=ready" -or
        $sshText -match "OMRADIO5_READY" -or
        $sshText -match "/run/openmitrastar/radio5g/state=ready"
    )

    $assoc = [ordered]@{
        requested = $true
        skipped = $true
        reason = "radio5_not_ready"
        exit_code = $null
        stdout = $assocOut
        stderr = $assocErr
        result = $assocJson
    }
    if ($sshOk -and $radioReady) {
        $assocArgs = @(
            (Join-Path $PSScriptRoot "run_qtn_5g_aelita_assoc_only.py"),
            "--execute",
            "--ack", "OPENMITRASTAR_QTN_5G_AELITA_ASSOC_ONLY",
            "--oracle-host", $OracleHost,
            "--oracle-user", $OracleUser,
            "--test-ssid", $TestSsid,
            "--restore-ssid", $RestoreSsid,
            "--timeout", "$AssocTimeoutSeconds",
            "--output", $assocJson
        )
        $assocProc = Start-Process -FilePath "python" -ArgumentList $assocArgs -NoNewWindow -PassThru `
            -RedirectStandardOutput $assocOut -RedirectStandardError $assocErr
        $assocWaitSeconds = $AssocTimeoutSeconds + 120
        if (-not $assocProc.WaitForExit($assocWaitSeconds * 1000)) {
            Stop-Process -Id $assocProc.Id -Force -ErrorAction SilentlyContinue
            $assoc.exit_code = 124
            $assoc.skipped = $false
            $assoc.reason = "assoc_only_timeout"
        } else {
            $assocProc.Refresh()
            $assoc.exit_code = [int]$assocProc.ExitCode
            $assoc.skipped = $false
            $assoc.reason = ""
        }
    }

    $assocPayload = Read-JsonFile $assocJson
    $assocPass = [bool]($assocPayload -and [string]$assocPayload.status -eq "PASS_ASSOC_ONLY")
    $terminal = if (-not $sshOk) {
        "SSH_SNAPSHOT_FAIL"
    } elseif (-not $radioReady) {
        "RADIO5_NOT_READY"
    } elseif ($assocPass) {
        "PASS_FLASH_BOOT_SSH_RADIO5_ASSOC_ONLY"
    } else {
        "ASSOC_ONLY_FAIL"
    }

    [ordered]@{
        schema = "openmitrastar.f125-5g-assoc-only-gate/v1"
        terminal_state = $terminal
        updated_at = (Get-Date).ToString("o")
        output_dir = $gateDir
        host = $HostAddress
        candidate_sha256 = $F125Sha256
        flash_evidence = $FlashEvidence
        two_g_preflight = $twoGPreflight
        ssh = [ordered]@{
            ok = $sshOk
            exit_code = $sshRc
            stdout = $sshOut
            stderr = $sshErr
        }
        radio5_ready = $radioReady
        assoc_only = $assoc
        assoc_result = $assocPayload
        policy = [ordered]@{
            association_only = $true
            two_g_gate_first = -not [bool]$Skip2gGateFirst
            l3_probe = $false
            traffic = $false
            static_ip = $false
            router_flash_writes = $false
            serial_uart = $false
        }
    } | ConvertTo-Json -Depth 12 | Set-Content -Encoding ascii -LiteralPath $gateJson

    return [ordered]@{
        terminal_state = $terminal
        pass = [bool]($terminal -eq "PASS_FLASH_BOOT_SSH_RADIO5_ASSOC_ONLY")
        path = $gateJson
    }
}

"F125_5G_ASSOC_MONITOR_START at=$(Get-Date -Format o) output=$OutputDir" |
    Add-Content -Encoding ascii -LiteralPath $logPath
Write-MonitorStatus "watching" "waiting for F125 flash evidence or router TCP/22"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    if (-not $RunDir) {
        $RunDir = Get-LatestF125RunDir
    }
    if (-not $RunDir) {
        "F125_5G_ASSOC_MONITOR_POLL at=$(Get-Date -Format o) no_f125_run_dir=1" |
            Add-Content -Encoding ascii -LiteralPath $logPath
        Write-MonitorStatus "waiting_f125_run" "no F125 flash-watch directory yet"
        Start-Sleep -Seconds $PollSeconds
        continue
    }

    $statusPath = Join-Path $RunDir "status.json"
    $status = Read-JsonFile $statusPath
    $flashEvidence = Get-F125FlashEvidence $status
    $tcp22 = [bool](Test-TcpPort $HostAddress 22 3)
    $alive = $false
    if ($status -and ($status.PSObject.Properties.Name -contains "pid")) {
        $alive = Test-ProcessAlive $status.pid
    } elseif ($status -and ($status.PSObject.Properties.Name -contains "watcher_pid")) {
        $alive = Test-ProcessAlive $status.watcher_pid
    }
    $state = if ($status) { [string]$status.state } else { "missing_status" }
    "F125_5G_ASSOC_MONITOR_POLL at=$(Get-Date -Format o) state=$state alive=$alive tcp22=$tcp22 pass=$($flashEvidence.pass) run_dir=$RunDir" |
        Add-Content -Encoding ascii -LiteralPath $logPath
    Write-MonitorStatus "watching" "F125 state=$state alive=$alive tcp22=$tcp22 flash_pass=$($flashEvidence.pass)" $status $flashEvidence

    if ($flashEvidence.pass -or $tcp22) {
        Write-MonitorStatus "starting_assoc_only_gate" "F125 flash evidence or TCP/22 observed; starting 5G association-only gate" $status $flashEvidence
        $gate = Invoke-F125AssocOnlyGate $flashEvidence
        Write-MonitorStatus $(if ($gate.pass) { "pass" } else { "gate_failed" }) "5G association-only gate terminal=$($gate.terminal_state)" $status $flashEvidence $gate.path
        if ($gate.pass) { exit 0 }
        exit 1
    }

    if ($flashEvidence.uart_rx_zero) {
        Write-MonitorStatus "uart_rx_zero_no_flash" "F125 helper reports zero UART RX; waiting for physical UART path or power cycle" $status $flashEvidence
    } elseif (-not $status) {
        Write-MonitorStatus "waiting_f125_status" "F125 status.json not present yet" $status $flashEvidence
    } elseif (-not $alive -and $state -in @("armed_waiting_bootbase", "attempt_running", "retry_wait", "starting")) {
        Write-MonitorStatus "stale_f125_watcher" "F125 watcher process is not alive and no pass/SSH evidence exists" $status $flashEvidence
        exit 1
    }

    Start-Sleep -Seconds $PollSeconds
}

Write-MonitorStatus "timeout" "timeout waiting for F125 flash evidence or router TCP/22"
exit 1
