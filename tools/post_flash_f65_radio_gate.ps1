[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$HostAddress = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "/workspace/user-home\Desktop\MitraStar\.codex_tmp\openmitrastar_ramssh_client_ed25519",
    [string]$OracleHost = "192.168.1.63",
    [string]$OracleUser = "AELITA",
    [string]$ControllerUrl = "http://192.168.1.43:8008/speed.bin",
    [switch]$Run2gProbe,
    [switch]$Run5gProbe,
    [switch]$Allow5gManualOff,
    [double]$Min2gMbps = 5.0,
    [double]$Diag2gMbps = 20.0,
    [ValidateSet("txpath", "v6scheduler")]
    [string]$FiveGProfile = "txpath",
    [ValidateRange(60, 900)]
    [int]$FiveGSeconds = 120,
    [int]$SshTimeoutSeconds = 20,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f65-radio-gate-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$stdoutPath = Join-Path $OutputDir "ssh.stdout.log"
$stderrPath = Join-Path $OutputDir "ssh.stderr.log"
$twoGLowOut = Join-Path $OutputDir "two-g-low-evidence.stdout.log"
$twoGLowErr = Join-Path $OutputDir "two-g-low-evidence.stderr.log"
$fiveGOut = Join-Path $OutputDir "five-g-aelita.stdout.log"
$fiveGErr = Join-Path $OutputDir "five-g-aelita.stderr.log"
$resultPath = Join-Path $OutputDir "result.json"

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutSeconds) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne([TimeSpan]::FromSeconds($TimeoutSeconds))
        if (-not $ok) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Write-Result([hashtable]$Payload) {
    $Payload.updated_at = (Get-Date).ToString("o")
    $Payload.output_dir = $OutputDir
    $Payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $resultPath
    Get-Content -LiteralPath $resultPath -Raw
}

function Get-JsonPropertyValue($Object, [string]$Name) {
    if ($null -eq $Object) { return $null }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $null }
    return $prop.Value
}

function Read-2gProbeSummary([string]$ProbeDir) {
    $summaryPath = Join-Path $ProbeDir "summary.json"
    if (-not (Test-Path -LiteralPath $summaryPath -PathType Leaf)) {
        return @{
            available = $false
            summary = $summaryPath
        }
    }
    $summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
    $payload = $null
    $payloadPath = $summary.aelita_result_path
    if ($payloadPath) {
        $resolvedPayloadPath = [string]$payloadPath
        if (-not [IO.Path]::IsPathRooted($resolvedPayloadPath)) {
            $resolvedPayloadPath = Join-Path $Root $resolvedPayloadPath
        }
        if (Test-Path -LiteralPath $resolvedPayloadPath -PathType Leaf) {
            $payload = Get-Content -LiteralPath $resolvedPayloadPath -Raw | ConvertFrom-Json
        }
    }
    $download = Get-JsonPropertyValue $summary "controller_download"
    $payloadTest = Get-JsonPropertyValue $payload "test"
    if (-not $download -and $payload) {
        $download = Get-JsonPropertyValue $payloadTest "controller_download"
    }
    $speedBps = $null
    $speedMbps = $null
    if ($download -and $null -ne $download.speed_Bps) {
        $speedBps = [int]$download.speed_Bps
        $speedMbps = [Math]::Round(($speedBps * 8.0) / 1000000.0, 2)
    }
    return @{
        available = $true
        summary = $summaryPath
        aelita_result_path = $summary.aelita_result_path
        aelita_rc = $summary.aelita_rc
        effective_aelita_rc = $summary.effective_aelita_rc
        connected = [bool](Get-JsonPropertyValue $payloadTest "connected")
        ping_ok = [bool](Get-JsonPropertyValue (Get-JsonPropertyValue $payloadTest "router_ping") "pass")
        download_ok = [bool](Get-JsonPropertyValue $download "pass")
        speed_Bps = $speedBps
        speed_Mbps = $speedMbps
        min_Mbps = $Min2gMbps
        meets_min = [bool]($null -ne $speedMbps -and $speedMbps -ge $Min2gMbps)
        diagnostic_Mbps = $Diag2gMbps
        meets_diagnostic = [bool]($null -ne $speedMbps -and $speedMbps -ge $Diag2gMbps)
        irq28_delta = $summary.irq28_delta
        first_station = $summary.first_station
        last_station = $summary.last_station
    }
}

function Get-RealtekLowThroughputEvidence([string]$Text) {
    $qguardStop = @($Text | Select-String -AllMatches -Pattern 'OMRTLQGUARD stage=stop[^\r\n]*' |
        ForEach-Object { $_.Matches.Value })
    $qguardWake = @($Text | Select-String -AllMatches -Pattern 'OMRTLQGUARD stage=wake[^\r\n]*' |
        ForEach-Object { $_.Matches.Value })
    $qguardPoll = @($Text | Select-String -AllMatches -Pattern 'OMRTLQGUARD stage=reclaim-poll[^\r\n]*' |
        ForEach-Object { $_.Matches.Value })
    $beLines = @($Text | Select-String -AllMatches -Pattern 'OMRTLBE[^\r\n]*|q=1[^\r\n]*(?:rp|wp|queued)[^\r\n]*' |
        ForEach-Object { $_.Matches.Value })
    $rateLines = @($Text | Select-String -AllMatches -Pattern 'OMRTLRA[^\r\n]*' |
        ForEach-Object { $_.Matches.Value })

    $rpProgress = $false
    $lastRp = $null
    $lastWp = $null
    foreach ($line in @($qguardStop + $qguardWake + $qguardPoll + $beLines)) {
        if ($line -match '\brp=(\d+)\b') {
            $rp = [int]$Matches[1]
            if ($null -ne $lastRp -and $rp -ne $lastRp) { $rpProgress = $true }
            $lastRp = $rp
        }
        if ($line -match '\bwp=(\d+)\b') {
            $lastWp = [int]$Matches[1]
        }
    }

    $rateStatus = if ($rateLines.Count -gt 0) {
        "rate_trace_present"
    } else {
        "rate_trace_absent"
    }
    $queueStatus = if ($qguardStop.Count -gt 0 -and $qguardWake.Count -gt 0 -and $rpProgress) {
        "guard_cycles_with_rp_progress"
    } elseif ($qguardStop.Count -gt 0 -and $qguardWake.Count -eq 0) {
        "guard_stops_without_wake"
    } elseif ($qguardStop.Count -eq 0 -and $beLines.Count -gt 0) {
        "be_trace_without_guard_stop"
    } elseif ($qguardStop.Count -eq 0) {
        "no_guard_stop_observed"
    } else {
        "guard_observed_without_rp_progress"
    }
    $next = switch ($queueStatus) {
        "guard_cycles_with_rp_progress" { "inspect rate/MCS/client path; BE reclaim is moving" }
        "guard_stops_without_wake" { "raise reclaim-poll attention; BE guard stops but never wakes" }
        "guard_observed_without_rp_progress" { "focus TXBD consumption/RP path; guard fires but RP does not advance" }
        "be_trace_without_guard_stop" { "inspect BE queue depth and guard thresholds; queue trace exists without stop/wake cycle" }
        default { "enable/collect OMRTLQGUARD and OMRTLBE evidence before changing rates" }
    }

    [ordered]@{
        schema = "openmitrastar.realtek-low-throughput-evidence/v1"
        queue_status = $queueStatus
        rate_status = $rateStatus
        qguard_stop_count = $qguardStop.Count
        qguard_wake_count = $qguardWake.Count
        qguard_reclaim_poll_count = $qguardPoll.Count
        be_trace_count = $beLines.Count
        rate_trace_count = $rateLines.Count
        rp_progress_observed = $rpProgress
        last_rp = $lastRp
        last_wp = $lastWp
        qguard_samples = @($qguardStop + $qguardPoll + $qguardWake | Select-Object -First 12)
        be_samples = @($beLines | Select-Object -First 12)
        rate_samples = @($rateLines | Select-Object -First 12)
        next_action = $next
    }
}

function Get-Quantenna5gEvidence([string]$Text) {
    $qdrvLines = @($Text | Select-String -AllMatches -Pattern '(?m)^qdrv\s+[^\r\n]*|OMQDRV[^\r\n]*|qdrv[^\r\n]*' |
        ForEach-Object { $_.Matches.Value })
    $wlanLines = @($Text | Select-String -AllMatches -Pattern '(?m)^wlan\s+[^\r\n]*|wlan[^\r\n]*qdrv[^\r\n]*' |
        ForEach-Object { $_.Matches.Value })
    $wifi0Lines = @($Text | Select-String -AllMatches -Pattern 'wifi0[^\r\n]*|192\.168\.77\.1[^\r\n]*' |
        ForEach-Object { $_.Matches.Value })
    $qcsapiLines = @($Text | Select-String -AllMatches -Pattern 'OMQTN_QCSAPI_[^\r\n]*|call_qcsapi[^\r\n]*|qcsapi[^\r\n]*' |
        ForEach-Object { $_.Matches.Value })
    $nativeLines = @($Text | Select-String -AllMatches -Pattern 'OMQTN_NATIVE_[^\r\n]*|OMQTN_HOSTAPD_QTN_[^\r\n]*|OMQTN_RF_ENABLE[^\r\n]*|OMQTN_WIFI0_[^\r\n]*|iwconfig-qtn[^\r\n]*|iwpriv-qtn[^\r\n]*|hostapd-cli-qtn[^\r\n]*|get_mode:[^\r\n]*|get_vht:[^\r\n]*|ESSID:"[^"\r\n]*"|Frequency:5\.[^\r\n]*|Channel:[^\r\n]*' |
        ForEach-Object { $_.Matches.Value })
    $fatalLines = @($Text | Select-String -AllMatches -Pattern 'Misaligned Access[^\r\n]*|Oops[^\r\n]*|kernel panic[^\r\n]*|panic:[^\r\n]*|TLBMiss[^\r\n]*|MuC[^\r\n]*(?:exception|\bpanic\b|\bfault\b)[^\r\n]*|qdrv[^\r\n]*(?:\bcrash\b|\bfault\b|\bpanic\b(?!-(?:policy|sysfs-pass)))[^\r\n]*' |
        ForEach-Object { $_.Matches.Value })

    $qdrvLoaded = [bool]($Text -match '(?m)^qdrv\s+')
    $wlanLoaded = [bool]($Text -match '(?m)^wlan\s+')
    $wifi0Present = [bool]($Text -match '\bwifi0\b')
    $wifi0L3 = [bool]($Text -match '192\.168\.77\.1')
    $wifi0InBr0 = [bool]($Text -match '(?m)^wifi0$|br0\s+.*\bwifi0\b')
    $wifi0Isolated = [bool]($wifi0Present -and $wifi0L3 -and -not $wifi0InBr0)
    $qcsapiPresent = [bool]($Text -match 'OMQTN_QCSAPI_PRESENT')
    $qcsapiOk = [bool]($Text -match 'OMQTN_QCSAPI_OK')
    $nativeControlOk = [bool]($Text -match 'OMQTN_NATIVE_OK')
    $hostapdQtnPong = [bool]($Text -match 'OMQTN_HOSTAPD_QTN_PONG')
    $rfOpen = [bool]($Text -match 'OMQTN_RF_ENABLE=1')
    $wifi0Running = [bool]($Text -match 'OMQTN_WIFI0_RUNNING=1')
    $hostapdWifi0 = [bool]($Text -match 'hostapd[^\r\n]*wifi0|wifi0[^\r\n]*hostapd')

    $state = "unknown"
    if ($fatalLines.Count -gt 0) {
        $state = "fatal_marker"
    } elseif (-not $qdrvLoaded -and -not $wlanLoaded) {
        $state = "drivers_not_loaded"
    } elseif ($qdrvLoaded -and $wlanLoaded -and -not $wifi0Present) {
        $state = "drivers_loaded_no_wifi0"
    } elseif ($wifi0InBr0) {
        $state = "wifi0_bridged_not_isolated"
    } elseif ($wifi0Isolated -and $nativeControlOk -and $hostapdQtnPong -and $rfOpen -and $wifi0Running) {
        $state = "native_ap_ready_isolated"
    } elseif ($wifi0Isolated -and $nativeControlOk -and $hostapdQtnPong) {
        $state = "native_hostapd_ready_isolated_rf_or_carrier_unproven"
    } elseif ($wifi0Isolated -and $nativeControlOk) {
        $state = "wifi0_isolated_native_control_no_hostapd"
    } elseif ($wifi0Isolated -and $qcsapiOk) {
        $state = "control_plane_ready_isolated"
    } elseif ($wifi0Isolated) {
        $state = "wifi0_isolated_native_control_unproven"
    } elseif ($wifi0Present) {
        $state = "wifi0_present_l3_missing"
    }

    $next = switch ($state) {
        "fatal_marker" { "symbolize Quantenna fatal marker before another 5G mutation" }
        "drivers_not_loaded" { "inspect init ordering/module dependencies; qdrv and wlan are absent" }
        "drivers_loaded_no_wifi0" { "inspect qdrv VAP/start path; modules loaded but wifi0 was not created" }
        "wifi0_bridged_not_isolated" { "fix product topology; wifi0 must stay isolated from br0 during this gate" }
        "native_ap_ready_isolated" { "run bounded 5G client/auth/data gate next" }
        "native_hostapd_ready_isolated_rf_or_carrier_unproven" { "inspect qdrv RF/carrier flags before client gate" }
        "wifi0_isolated_native_control_no_hostapd" { "start or inspect hostapd-qtn for wifi0; native WEXT control is alive" }
        "control_plane_ready_isolated" { "run bounded 5G client/auth/data gate next" }
        "wifi0_isolated_native_control_unproven" { "capture iwpriv-qtn/iwconfig-qtn/hostapd-cli-qtn failures before changing qdrv" }
        "wifi0_present_l3_missing" { "restore wifi0 isolated 192.168.77.1 address before client gate" }
        default { "collect full qdrv/wlan/wifi0/qcsapi snapshot" }
    }

    [ordered]@{
        schema = "openmitrastar.quantenna-5g-evidence/v1"
        state = $state
        qdrv_loaded = $qdrvLoaded
        wlan_loaded = $wlanLoaded
        wifi0_present = $wifi0Present
        wifi0_isolated_l3 = $wifi0Isolated
        wifi0_in_br0 = $wifi0InBr0
        qcsapi_present = $qcsapiPresent
        qcsapi_ok = $qcsapiOk
        native_control_ok = $nativeControlOk
        hostapd_qtn_pong = $hostapdQtnPong
        rf_open = $rfOpen
        wifi0_running = $wifi0Running
        hostapd_wifi0_seen = $hostapdWifi0
        fatal_marker_count = $fatalLines.Count
        qdrv_marker_count = $qdrvLines.Count
        qcsapi_line_count = $qcsapiLines.Count
        wifi0_line_count = $wifi0Lines.Count
        qdrv_samples = @($qdrvLines | Select-Object -First 12)
        wlan_samples = @($wlanLines | Select-Object -First 8)
        wifi0_samples = @($wifi0Lines | Select-Object -First 12)
        qcsapi_samples = @($qcsapiLines | Select-Object -First 12)
        native_samples = @($nativeLines | Select-Object -First 16)
        fatal_samples = @($fatalLines | Select-Object -First 12)
        next_action = $next
    }
}

function Invoke-2gLowThroughputEvidence {
    $remote = @'
echo OM2G_LOW_EVIDENCE_BEGIN
echo SECTION_IW_DEV
iw dev 2>/dev/null || true
echo SECTION_IW_STATION
iw dev wlan0 station dump 2>/dev/null || iw wlan0 station dump 2>/dev/null || true
echo SECTION_HOSTAPD
hostapd_cli -i wlan0 status 2>/dev/null || true
hostapd_cli -i wlan0 all_sta 2>/dev/null || true
echo SECTION_RTL_PARAMS
for p in /sys/module/rtl_pci/parameters/* /sys/module/rtl8192ee/parameters/*; do
    [ -r "$p" ] && printf '%s=' "$(basename "$p")" && cat "$p"
done
echo SECTION_NETDEV
cat /proc/net/dev
echo SECTION_INTERRUPTS
cat /proc/interrupts
echo SECTION_DMESG_OMRTL
dmesg | grep -E 'OMRTLBE|OMRTLQGUARD|OMRTLRA|OMRTLMGMT|rtl8192ee|wlan0|BE_QUEUE|TXBD' | tail -n 320 || true
echo OM2G_LOW_EVIDENCE_END
'@
    $ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
    $knownHosts = Join-Path $OutputDir "known_hosts"
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
        $remote
    )
    $proc = Start-Process -FilePath $ssh -ArgumentList $sshArgs -NoNewWindow -PassThru `
        -RedirectStandardOutput $twoGLowOut -RedirectStandardError $twoGLowErr
    if (-not $proc.WaitForExit($SshTimeoutSeconds * 1000)) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        return @{
            ok = $false
            exit_code = 124
            classification = "LOW_2G_EVIDENCE_TIMEOUT"
            stdout = $twoGLowOut
            stderr = $twoGLowErr
            parsed = $null
        }
    }
    $text = ""
    if (Test-Path -LiteralPath $twoGLowOut) {
        $text = Get-Content -LiteralPath $twoGLowOut -Raw
    }
    $proc.Refresh()
    $exitCode = $proc.ExitCode
    $ok = [bool]($text.Contains("OM2G_LOW_EVIDENCE_BEGIN") -and $text.Contains("OM2G_LOW_EVIDENCE_END"))
    return @{
        ok = $ok
        exit_code = $exitCode
        classification = if ($ok) { "LOW_2G_EVIDENCE_OK" } else { "LOW_2G_EVIDENCE_FAIL" }
        stdout = $twoGLowOut
        stderr = $twoGLowErr
        parsed = Get-RealtekLowThroughputEvidence $text
    }
}

function Invoke-5gAelitaProbe {
    $probeDir = Join-Path $OutputDir "aelita-5g"
    New-Item -ItemType Directory -Force -Path $probeDir | Out-Null
    $profileArg = if ($FiveGProfile -eq "v6scheduler") { "--v6-scheduler-diag" } else { "--tx-path-trace" }
    $args = @(
        (Join-Path $PSScriptRoot "run_qtn_5g_aelita_one_shot.py"),
        "--execute",
        "--ack", "OPENMITRASTAR_QTN_5G_AELITA_ONE_SHOT_RAM_ONLY",
        "--stable-2g-ack", "OPENMITRASTAR_2G_STABLE_FOR_QTN5G",
        "--router-host", $HostAddress,
        "--oracle-host", $OracleHost,
        "--oracle-user", $OracleUser,
        "--controller-ip", "192.168.1.43",
        "--restore-ssid", "MOVISTAR-WIFI6-A348",
        "--seconds", "$FiveGSeconds",
        "--output-dir", $probeDir,
        $profileArg
    )
    $proc = Start-Process -FilePath "python" -ArgumentList $args -NoNewWindow -PassThru `
        -RedirectStandardOutput $fiveGOut -RedirectStandardError $fiveGErr
    $timeoutMs = [Math]::Max(300000, ($FiveGSeconds + 960) * 1000)
    if (-not $proc.WaitForExit($timeoutMs)) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        return @{
            requested = $true
            skipped = $false
            exit_code = 124
            classification = "FIVE_G_AELITA_TIMEOUT"
            profile = $FiveGProfile
            output_dir = $probeDir
            stdout = $fiveGOut
            stderr = $fiveGErr
            result = $null
        }
    }
    $stdout = if (Test-Path -LiteralPath $fiveGOut) { Get-Content -LiteralPath $fiveGOut -Raw } else { "" }
    $resultFile = $null
    if ($stdout -match 'OMQTN5G_AELITA_ONE_SHOT_PASS=1 result=([^\r\n]+)') {
        $resultFile = $Matches[1].Trim()
    }
    $proc.Refresh()
    $exitCode = $proc.ExitCode
    $pass = ($exitCode -eq 0) -and [bool]$resultFile
    return @{
        requested = $true
        skipped = $false
        exit_code = $exitCode
        classification = if ($pass) { "FIVE_G_AELITA_PASS" } else { "FIVE_G_AELITA_FAIL" }
        profile = $FiveGProfile
        output_dir = $probeDir
        stdout = $fiveGOut
        stderr = $fiveGErr
        result = $resultFile
    }
}

$pingOk = [bool](Test-Connection -ComputerName $HostAddress -Count 2 -Quiet -ErrorAction SilentlyContinue)
$tcp22 = [bool](Test-TcpPort $HostAddress 22 $SshTimeoutSeconds)
if (-not $pingOk -or -not $tcp22) {
    Write-Result @{
        schema = "openmitrastar.f65-postflash-radio-gate/v1"
        terminal_state = "NO_MANAGEMENT"
        ping = $pingOk
        tcp22 = $tcp22
        ssh = $false
        two_g_probe = @{
            requested = [bool]$Run2gProbe
            skipped = $true
            reason = "no_management"
        }
        five_g_probe = @{
            requested = [bool]$Run5gProbe
            skipped = $true
            reason = "no_management"
        }
        flash = $false
        router_mutations = $false
    }
    exit 1
}

$remote = @'
echo OMF65_GATE_BEGIN
echo SECTION_UNAME
uname -a
echo SECTION_PROC_UPTIME
cat /proc/uptime
echo SECTION_IP_LINK
ip -br link 2>/dev/null || ifconfig -a
echo SECTION_IP_ADDR
ip -br addr 2>/dev/null || ifconfig -a
echo SECTION_BRCTL
brctl show 2>/dev/null || true
echo SECTION_BR0_MEMBERS
ls -1 /sys/class/net/br0/brif 2>/dev/null || true
echo SECTION_WIFI0_ADDR
ifconfig wifi0 2>/dev/null || true
echo SECTION_WIFI0_SYSFS
for p in /sys/class/net/wifi0/operstate /sys/class/net/wifi0/carrier /sys/class/net/wifi0/address; do
    [ -r "$p" ] && printf '%s=' "$p" && cat "$p"
done
echo SECTION_WLAN0_ADDR
ifconfig wlan0 2>/dev/null || true
echo SECTION_HOSTAPD
ps w 2>/dev/null | grep -E 'hostapd|qcsapi|wpa' | grep -v grep || true
echo SECTION_QTN_NATIVE_CONTROL
if [ -r /sys/module/qdrv/parameters/openmitrastar_rf_enable ]; then
    printf 'OMQTN_RF_ENABLE='
    cat /sys/module/qdrv/parameters/openmitrastar_rf_enable
fi
if [ -r /sys/class/net/wifi0/flags ]; then
    flags=$(cat /sys/class/net/wifi0/flags 2>/dev/null || echo 0)
    echo OMQTN_WIFI0_FLAGS="$flags"
    [ "$(( flags & 0x41 ))" -eq 65 ] && echo OMQTN_WIFI0_RUNNING=1 || echo OMQTN_WIFI0_RUNNING=0
fi
if command -v iwconfig-qtn >/dev/null 2>&1 && command -v iwpriv-qtn >/dev/null 2>&1; then
    echo OMQTN_NATIVE_PRESENT
    native_rc=0
    /usr/sbin/iwconfig-qtn wifi0 2>&1 || native_rc=1
    /usr/sbin/iwpriv-qtn wifi0 get_mode 2>&1 || native_rc=1
    /usr/sbin/iwpriv-qtn wifi0 get_vht 2>&1 || native_rc=1
    /usr/sbin/iwpriv-qtn wifi0 get_bwselect 2>&1 || true
    if [ "$native_rc" = 0 ]; then
        echo OMQTN_NATIVE_OK
    else
        echo OMQTN_NATIVE_FAIL rc="$native_rc"
    fi
else
    echo OMQTN_NATIVE_MISSING
fi
if command -v hostapd-cli-qtn >/dev/null 2>&1; then
    hapd_qtn=$(/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping 2>&1 || true)
    printf '%s\n' "$hapd_qtn"
    [ "$hapd_qtn" = PONG ] && echo OMQTN_HOSTAPD_QTN_PONG || echo OMQTN_HOSTAPD_QTN_FAIL
else
    echo OMQTN_HOSTAPD_QTN_MISSING
fi
echo SECTION_MODULES
lsmod 2>/dev/null | grep -E 'rtl|qdrv|qtn|cfg80211|mac80211|wlan' || true
echo SECTION_INTERRUPTS
cat /proc/interrupts
echo SECTION_DMESG_RADIO_TAIL
dmesg | grep -E 'OMNETWORK_READY|OMSSH_READY|OMRADIO2|OMRTL|OMQDRV|OMRADIO5|qdrv|wifi0|wlan0|hostapd|br0|Misaligned|Oops|panic' | tail -n 260 || true
echo OMF65_GATE_END
'@

$knownHosts = Join-Path $OutputDir "known_hosts"
$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$sshKeyscan = Join-Path $env:WINDIR "System32\OpenSSH\ssh-keyscan.exe"
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$scanText = & $sshKeyscan -T 5 -t ed25519,rsa $HostAddress 2>&1
$ErrorActionPreference = $previousErrorActionPreference
$scan = @($scanText |
    ForEach-Object { [string]$_ } |
    Where-Object { $_ -and -not $_.StartsWith("#") }
)
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
    $remote
)
$proc = Start-Process -FilePath $ssh -ArgumentList $sshArgs -NoNewWindow -PassThru `
    -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
if (-not $proc.WaitForExit($SshTimeoutSeconds * 1000)) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Write-Result @{
        schema = "openmitrastar.f65-postflash-radio-gate/v1"
        terminal_state = "SSH_TIMEOUT"
        ping = $pingOk
        tcp22 = $tcp22
        ssh = $false
        stdout = $stdoutPath
        stderr = $stderrPath
        two_g_probe = @{
            requested = [bool]$Run2gProbe
            skipped = $true
            reason = "ssh_timeout"
        }
        five_g_probe = @{
            requested = [bool]$Run5gProbe
            skipped = $true
            reason = "ssh_timeout"
        }
        flash = $false
        router_mutations = $false
    }
    exit 1
}

$text = if (Test-Path -LiteralPath $stdoutPath) { Get-Content -LiteralPath $stdoutPath -Raw } else { "" }
$sshTranscriptComplete = $text.Contains("OMF65_GATE_BEGIN") -and $text.Contains("OMF65_GATE_END")
$proc.Refresh()
$sshExitCode = $proc.ExitCode
$sshOk = $sshTranscriptComplete
$br0HasEth0 = $text -match "(?m)^eth0$|br0\s+.*\beth0\b"
$br0HasWlan0 = $text -match "(?m)^wlan0$|br0\s+.*\bwlan0\b"
$fatal = [bool]($text -match "Misaligned|Oops|kernel panic|panic:")
$hostapd = $text -match "hostapd"
$fiveGEvidence = Get-Quantenna5gEvidence $text
$br0HasWifi0 = [bool]$fiveGEvidence.wifi0_in_br0
$wifi0Isolated = [bool]$fiveGEvidence.wifi0_isolated_l3
$qdrv = [bool]$fiveGEvidence.qdrv_loaded

$terminal = if (-not $sshOk) {
    "SSH_COMMAND_FAIL"
} elseif ($fatal) {
    "BOOT_FATAL_MARKER"
} elseif ($fiveGEvidence.state -eq "fatal_marker") {
    "BOOT_FATAL_MARKER"
} elseif ($br0HasWifi0) {
    "FAIL_WIFI0_BRIDGED"
} elseif (-not ($br0HasEth0 -and $br0HasWlan0)) {
    "FAIL_BR0_2G_TOPOLOGY"
} elseif ($Allow5gManualOff -and -not $Run5gProbe -and -not $qdrv) {
    "PASS_MANAGEMENT_AND_TOPOLOGY"
} elseif (-not $wifi0Isolated) {
    "FAIL_WIFI0_ISOLATED_L3"
} else {
    "PASS_MANAGEMENT_AND_TOPOLOGY"
}

$twoGProbe = @{
    requested = [bool]$Run2gProbe
    skipped = $true
    reason = "not_requested"
}
$twoGSummary = @{
    available = $false
    reason = "not_requested"
}
$twoGLowEvidence = $null
$fiveGProbe = @{
    requested = [bool]$Run5gProbe
    skipped = $true
    reason = "not_requested"
}
if ($Run2gProbe -and $terminal -eq "PASS_MANAGEMENT_AND_TOPOLOGY") {
    $probeDir = Join-Path $OutputDir "aelita-2g"
    & python (Join-Path $PSScriptRoot "run_aelita_2g_wpa2_speed_router_probe.py") `
        --router-host $HostAddress `
        --router-user $RouterUser `
        --router-key $RouterKey `
        --oracle-host $OracleHost `
        --oracle-user $OracleUser `
        --controller-url $ControllerUrl `
        --output-dir $probeDir *> (Join-Path $OutputDir "aelita-2g.stdout.log")
    $twoGProbe = @{
        requested = $true
        skipped = $false
        exit_code = $LASTEXITCODE
        output_dir = $probeDir
    }
    $twoGSummary = Read-2gProbeSummary $probeDir
    if ($LASTEXITCODE -ne 0) {
        $terminal = "PASS_TOPOLOGY_2G_PROBE_FAIL"
        $twoGLowEvidence = Invoke-2gLowThroughputEvidence
    } elseif (-not $twoGSummary.meets_min) {
        $terminal = "PASS_TOPOLOGY_2G_THROUGHPUT_LOW"
        $twoGLowEvidence = Invoke-2gLowThroughputEvidence
    } else {
        if (-not $twoGSummary.meets_diagnostic) {
            $twoGLowEvidence = Invoke-2gLowThroughputEvidence
        }
        $terminal = "PASS_TOPOLOGY_AND_2G_SPEED"
    }
} elseif ($Run2gProbe) {
    $twoGProbe = @{
        requested = $true
        skipped = $true
        reason = "topology_not_pass"
    }
    $twoGSummary = @{
        available = $false
        reason = "topology_not_pass"
    }
}

if ($Run5gProbe) {
    if ($terminal -eq "PASS_TOPOLOGY_AND_2G_SPEED") {
        $fiveGProbe = Invoke-5gAelitaProbe
        if ($fiveGProbe.classification -eq "FIVE_G_AELITA_PASS") {
            $terminal = "PASS_TOPOLOGY_2G_SPEED_AND_5G"
        } else {
            $terminal = "PASS_TOPOLOGY_2G_SPEED_5G_PROBE_FAIL"
        }
    } else {
        $fiveGProbe = @{
            requested = $true
            skipped = $true
            reason = "requires_2g_speed_pass"
            blocked_by_terminal_state = $terminal
        }
    }
}

Write-Result @{
    schema = "openmitrastar.f65-postflash-radio-gate/v1"
    terminal_state = $terminal
    ping = $pingOk
    tcp22 = $tcp22
    ssh = $sshOk
    ssh_transport_ok = $sshTranscriptComplete
    ssh_exit_code = $sshExitCode
    br0_has_eth0 = $br0HasEth0
    br0_has_wlan0 = $br0HasWlan0
    br0_has_wifi0 = $br0HasWifi0
    wifi0_isolated_l3 = $wifi0Isolated
    hostapd_seen = $hostapd
    qdrv_seen = $qdrv
    five_g_evidence = $fiveGEvidence
    five_g_manual_off_allowed = [bool]$Allow5gManualOff
    fatal_marker = $fatal
    two_g_probe = $twoGProbe
    two_g_summary = $twoGSummary
    two_g_low_evidence = $twoGLowEvidence
    five_g_probe = $fiveGProbe
    stdout = $stdoutPath
    stderr = $stderrPath
    flash = $false
    router_mutations = $false
}
$passingTerminals = @(
    "PASS_MANAGEMENT_AND_TOPOLOGY",
    "PASS_TOPOLOGY_AND_2G_SPEED",
    "PASS_TOPOLOGY_2G_SPEED_AND_5G"
)
if ($passingTerminals -contains $terminal) { exit 0 }
exit 1
