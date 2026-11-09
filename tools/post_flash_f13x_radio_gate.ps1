[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("F133", "F134", "F135", "F136", "F137", "F138", "F139", "F140", "F141", "F142", "F143", "F144", "F145", "F146", "F147", "F148", "F149", "F150", "F151", "F152", "F153", "F154", "F155", "F156", "F157", "F158", "F159", "F160", "F161", "F162", "F163")]
    [string]$Profile = "F133",
    [string]$HostAddress = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "$env:USERPROFILE\.ssh\id_ed25519",
    [ValidateRange(0, 21600)]
    [int]$WaitSeconds = 0,
    [ValidateRange(1, 60)]
    [int]$PollSeconds = 5,
    [ValidateRange(30, 600)]
    [int]$RemoteTimeoutSeconds = 180,
    [switch]$RunRadio5Start,
    [switch]$StopRadio5First,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f13x-radio-gate-$($Profile.ToLowerInvariant())-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StatusPath = Join-Path $OutputDir "status.json"

function Write-Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f13x-radio-gate/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        profile = $Profile
        host = $HostAddress
        wait_seconds = $WaitSeconds
        poll_seconds = $PollSeconds
        remote_timeout_seconds = $RemoteTimeoutSeconds
        run_radio5_start = [bool]$RunRadio5Start
        stop_radio5_first = [bool]$StopRadio5First
        flashes = $false
        touches_uart = $false
    }
    foreach ($key in $Extra.Keys) { $payload[$key] = $Extra[$key] }
    $payload | ConvertTo-Json -Depth 10 | Set-Content -Encoding ascii -LiteralPath $StatusPath
}

function Test-TcpQuick([string]$HostName, [int]$PortNumber, [int]$TimeoutMs = 900) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $PortNumber, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Wait-Ssh() {
    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    $attempt = 0
    while ($true) {
        $attempt += 1
        if (Test-TcpQuick $HostAddress 22) {
            return [ordered]@{ tcp22 = $true; attempts = $attempt }
        }
        if ($WaitSeconds -le 0 -or (Get-Date) -ge $deadline) {
            return [ordered]@{ tcp22 = $false; attempts = $attempt }
        }
        Write-Status "waiting_ssh" "waiting for router SSH" @{ attempts = $attempt }
        Start-Sleep -Seconds $PollSeconds
    }
}

function Invoke-RouterSsh([string]$Remote, [string]$StdoutPath, [string]$StderrPath) {
    $ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
    $knownHosts = Join-Path $OutputDir "known_hosts"
    $remoteScript = Join-Path $OutputDir "router-probe.remote.sh"
    [IO.File]::WriteAllText(
        $remoteScript,
        (($Remote -replace "`r`n", "`n") -replace "`r", "`n"),
        [Text.Encoding]::ASCII
    )
    $args = @(
        "-i", $RouterKey,
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=$knownHosts",
        "-o", "HostKeyAlgorithms=+ssh-rsa",
        "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa",
        "-o", "LogLevel=ERROR",
        "$RouterUser@$HostAddress",
        "sh",
        "-s"
    )
    $proc = Start-Process -FilePath $ssh -ArgumentList $args -NoNewWindow -PassThru `
        -RedirectStandardInput $remoteScript -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath
    if (-not $proc.WaitForExit($RemoteTimeoutSeconds * 1000)) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        return 124
    }
    $proc.Refresh()
    return [int]$proc.ExitCode
}

$remote = @"
set -u
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH
echo OMF13X_GATE_BEGIN profile=$Profile
echo SECTION_SYSTEM
uname -a
cat /proc/uptime 2>/dev/null || true
echo SECTION_MTD
cat /proc/mtd 2>/dev/null || true
echo SECTION_NET
ifconfig eth0 2>&1 || true
ifconfig br0 2>&1 || true
ifconfig wlan0 2>&1 || true
ifconfig wifi0 2>&1 || true
brctl show 2>&1 || true
ls -1 /sys/class/net/br0/brif 2>/dev/null || true
if [ -e /sys/class/net/br0/brif/wifi0 ]; then echo OMF13X_BR0_WIFI0=1; else echo OMF13X_BR0_WIFI0=0; fi
wifi0_ipv4=`$(ifconfig wifi0 2>/dev/null | sed -n 's/.*inet addr:\([0-9.]*\).*/\1/p' | head -n 1)
[ -n "`$wifi0_ipv4" ] || wifi0_ipv4=none
echo OMF13X_WIFI0_IPV4=`$wifi0_ipv4
echo SECTION_RADIO2G
/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status 2>&1 || true
iwconfig wlan0 2>&1 || true
echo SECTION_RADIO5_PRE
cat /run/openmitrastar/radio5g/state 2>/dev/null || true
cat /run/openmitrastar/radio5g/ready 2>/dev/null || true
cat /run/openmitrastar/radio5g/last-refusal 2>/dev/null || true
tail -n 160 /run/openmitrastar/radio5g/hostapd.log 2>/dev/null || true
cat /run/openmitrastar/radio5g/vap-create-diag.log 2>/dev/null || true
for f in /run/openmitrastar/radio5g/visibility-*.log /run/openmitrastar/radio5g/assoc-window-*.dmesg; do
    if [ -r "`$f" ]; then
        echo FILE "`$f"
        tail -n 120 "`$f"
    fi
done
"@

if ($StopRadio5First) {
    $remote += "`n"
    $remote += @'
echo SECTION_RADIO5_STOP
/usr/sbin/om-radio5-stop f13x-radio-gate-prestart 2>&1 || true
'@
}
if ($RunRadio5Start) {
    $remote += "`n"
    $remote += @'
echo SECTION_RADIO5_START
/usr/sbin/om-radio5-start
radio5_rc=$?
echo OMF13X_RADIO5_START_RC=$radio5_rc
'@
}

$remote += "`n"
$remote += @'
echo SECTION_RADIO5_POST
cat /run/openmitrastar/radio5g/state 2>/dev/null || true
cat /run/openmitrastar/radio5g/ready 2>/dev/null || true
cat /run/openmitrastar/radio5g/last-refusal 2>/dev/null || true
cat /etc/openmitrastar/features/q3-radio5-autostart 2>/dev/null || true
cat /usr/share/openmitrastar/radio5g/q3-radio5-autostart.feature 2>/dev/null || true
cat /etc/openmitrastar/features/q3-radio5-open-lab 2>/dev/null || true
sha256sum /lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko 2>/dev/null || true
sha256sum /lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/wlan.ko 2>/dev/null || true
sha256sum /usr/sbin/om-radio5-start 2>/dev/null || true
sha256sum /usr/sbin/om-radio-modules 2>/dev/null || true
sha256sum /lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl_pci.ko 2>/dev/null || true
sha256sum /lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/switch_tqe.ko 2>/dev/null || true
cat /sys/class/net/tqe/dbg 2>/dev/null || true
printf 'hgw500_tx_queue_guard='; cat /sys/module/rtl_pci/parameters/hgw500_tx_queue_guard 2>/dev/null || true
printf 'hgw500_tx_queue_guard_high='; cat /sys/module/rtl_pci/parameters/hgw500_tx_queue_guard_high 2>/dev/null || true
printf 'hgw500_tx_queue_guard_low='; cat /sys/module/rtl_pci/parameters/hgw500_tx_queue_guard_low 2>/dev/null || true
printf 'hgw500_tx_reclaim_poll='; cat /sys/module/rtl_pci/parameters/hgw500_tx_reclaim_poll 2>/dev/null || true
printf 'hgw500_be_tx_summary='; cat /sys/module/rtl_pci/parameters/hgw500_be_tx_summary 2>/dev/null || true
printf 'hgw500_oem_tx_report='; cat /sys/module/rtl8192ee/parameters/hgw500_oem_tx_report 2>/dev/null || true
ifconfig wifi0 2>&1 || true
/usr/sbin/iwconfig-qtn wifi0 2>&1 || true
/usr/sbin/iwpriv-qtn wifi0 getparam 402 2>&1 || true
/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 status 2>&1 || true
/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 get_config 2>&1 || true
echo SECTION_HOSTAPD_POST
tail -n 160 /run/openmitrastar/radio5g/hostapd.log 2>/dev/null || true
echo SECTION_DMESG
dmesg 2>/dev/null | grep -E 'OMRADIO5|OMQDRV|OMQTN|RAM_INSMOD|qdrv|wifi0|MuC|HLINK|EV_TLB|EV_ProtV|Oops:|BUG:|panic|OMEMAC|OMRTL' | tail -n 260 || true
echo OMF13X_GATE_END
'@

Write-Status "starting" "post-flash F13x gate starting"
$wait = Wait-Ssh
if (-not $wait.tcp22) {
    Write-Status "no_ssh" "router SSH is not reachable" @{ wait = $wait }
    Get-Content -Raw -LiteralPath $StatusPath
    exit 1
}

$stdout = Join-Path $OutputDir "router-probe.stdout.log"
$stderr = Join-Path $OutputDir "router-probe.stderr.log"
$rc = Invoke-RouterSsh $remote $stdout $stderr
$tcpAfter = Test-TcpQuick $HostAddress 22
$text = if (Test-Path -LiteralPath $stdout -PathType Leaf) {
    Get-Content -Raw -LiteralPath $stdout
} else {
    ""
}

$complete = $text.Contains("OMF13X_GATE_BEGIN") -and $text.Contains("OMF13X_GATE_END")
$radio5Rc = $null
if ($text -match "OMF13X_RADIO5_START_RC=([0-9]+)") { $radio5Rc = [int]$Matches[1] }
$fatal = [bool]($text -match "MuC exception|MuC has halted|HLINK MSG timed out|EV_TLB|EV_ProtV|Oops:|BUG:|Kernel panic|panic:")
$twoGEnabled = [bool]($text -match "(?m)^state=ENABLED$")
$rfHold = [bool]($text -match "OMRADIO5_RF_HOLD_AFTER_VAP|rf-hold-after-vap")
$coreHold = [bool]($text -match "OMRADIO5_CORE_HOLD_BEFORE_VAP|core-hold-before-vap")
$ready5 = [bool]($text -match "OMRADIO5_READY|(?m)^ready$")
$txPowerZero = [bool]($text -match "visibility-txpower-zero|Tx-Power:0 dBm")
$visibilityProbe = [bool]($text -match "OMRADIO5_VISIBILITY_PROBE|(?m)^carrier-pending$")
$hostapdRawFallback = [bool]($text -match "OMHAPD raw-probe-socket ifname=wifi0 source=bss")
$hostapdRawEnodev = [bool]($text -match "l2_packet_init: ioctl\[SIOCGIFINDEX\]: No such device")
$wlanTxPowerDefault = [bool]($text -match "OMQTNTXPWR stage=default-limit half_dbm=100 dbm=50")
$txPower21 = [bool]($text -match "Tx-Power[:=]21 dBm")
$qdrvF143 = [bool]($text -match "db498a534bf388f2e0ddf75e6802c99fb868e9dc6e9a4e3a56f5ab69f785a8e9")
$qdrvF144 = [bool]($text -match "89139dbf883e254b8b74ad57a61d8b35ed5bb85b4654cf73787910134016c684")
$qdrvF145 = [bool]($text -match "5efe71b0431b5867f172a1abebe0b99534e07f7db9f6c5c1dcb89bc6c1c79341")
$qdrvF146 = [bool]($text -match "f92761b610eb715d5811275d00935391f9e9fbfb50e213949f3d019f276273c4")
$qdrvF147 = [bool]($text -match "ed2a1ce601089bb2cbb6b52d0d4444839da927dd6443124d11856cddc900f387")
$qdrvF148 = [bool]($text -match "600a6f98bb3151cf80755bd5132b8bc9a7460b86146557d57ba8c97568d5a581")
$wlanF148 = [bool]($text -match "a750b273c0570c2ccfe0fce3f28a311d2e8e3b9f7d7ef9f7cd9ed48046065233")
$startF149 = [bool]($text -match "098a27055d76dafefc84906c35f48a4728bfde1b9d26bbdadb169a51498eaf94")
$startF151 = [bool]($text -match "9e1fe8e392a472b14a9e60d72e99c46c6510de8c992e8f74b0c81255a8be323d")
$wlanF152 = [bool]($text -match "f4f6099b43dd675dd44e7021374f1ea2f4380a4d9d9fd81b1d35ea411984897f")
$startF152 = [bool]($text -match "58961599428deb90fa37cc09547b7ccff6c0294813e9cdb373ad831ff570a7ad")
$qdrvF153 = [bool]($text -match "cc3ca17b10cc3efcdc9a37343ead4e0c28be07e331542663b94dd0b2de0b7a61")
$startF153 = [bool]($text -match "e20a5450c9d58a875df77a834e6374c2a8cc7a8287c8acd115b8c9ce2992af77")
$qdrvF154 = [bool]($text -match "dcc4abaaeb92f0f5435860e206369ade67e7ba6e60d52f651eb1951b423a1443")
$startF154 = [bool]($text -match "81e7a5d119955f321620191683f9f9f0c69e2fb02199d4d2616681222a85900c")
$qdrvF155 = [bool]($text -match "0ef6cac2fe68ba62dcba21c4878b9d4697d8e6560579bf74f3ed9a5ae09c0dff")
$startF155 = [bool]($text -match "d0806f37206b6983319bb6e1bceaaad824e7682dd5e40498f271df5396b84f10")
$startF156 = [bool]($text -match "fca1f044c2d54a817b3e8183ee84e7ba8320aed13a1b341c82a56c4410e2d5bc")
$txBaDisabled = [bool]($text -match "getparam:1")
$startF157 = [bool]($text -match "e96a7563c8b361423b482427e2e1216bee9c550954b8a9ba24d823bc1f07f029")
$wifi0Bridged = [bool]($text -match "OMF13X_BR0_WIFI0=1")
$wifi0NoIpv4 = [bool]($text -match "OMF13X_WIFI0_IPV4=none")
$radioModulesF158 = [bool]($text -match "f0ff6da39a8c16b116754bf39f75e43550354afce2cc06d87568ebd9b97ab7e0")
$twoGGuardOff = [bool]($text -match "hgw500_tx_queue_guard=N")
$twoGReclaimOff = [bool]($text -match "hgw500_tx_reclaim_poll=N")
$twoGGuard64 = [bool]($text -match "hgw500_tx_queue_guard_high=64")
$twoGGuard32 = [bool]($text -match "hgw500_tx_queue_guard_low=32")
$rtlPciF159 = [bool]($text -match "c6e1c2cd8279cfdeea154b96ecda92a105906d2e25fd713834b9318dc8cf2933")
$rtlPciF160 = [bool]($text -match "6f85efa424c6aa5b693982ae074d268d2312a3f9262238e8c6f5eda16199df63")
$radioModulesF160 = [bool]($text -match "e46f56582af0fe34c8cd0cf774c709d5851b8db38e1d7017d5be48e7bee22faf")
$twoGSummaryOn = [bool]($text -match "hgw500_be_tx_summary=Y")
$radioModulesF161 = [bool]($text -match "02c0b49e7534c7fd38cd66a7437afed54b3a381147528d86d8980c37d58b37e2")
$twoGOemTxReportOn = [bool]($text -match "hgw500_oem_tx_report=Y")
$switchTqeF162 = [bool]($text -match "bd5ab1018d293dc6bed655ec2bbc6da64a3969f28a3de578c04fa9c3f4af635f")
$tqeReadonlyV1 = [bool]($text -match "(?m)^version=omtqe-readonly-v1$")
$radio5AutostartEnabled = ([regex]::Matches($text, "Q3_RADIO5_AUTOSTART=1")).Count -ge 2
$radio5OpenLabDisabled = [bool]($text -match "Q3_RADIO5_OPEN_LAB=0")
$wpa2Ready = [bool](($text -match "(?m)^key_mgmt=.*WPA-PSK") -and ($text -match "(?m)^(group_cipher|rsn_pairwise_cipher)=CCMP"))

$terminal = if ($rc -eq 124 -or -not $tcpAfter) {
    "MANAGEMENT_LOST_OR_TIMEOUT"
} elseif (-not $complete) {
    "INCOMPLETE_TRANSCRIPT"
} elseif ($fatal) {
    "FATAL_MARKER"
} elseif ($Profile -eq "F134" -and $RunRadio5Start -and $rfHold) {
    "PASS_F134_RF_HOLD"
} elseif ($Profile -eq "F135" -and $RunRadio5Start -and $coreHold) {
    "PASS_F135_CORE_HOLD"
} elseif ($Profile -eq "F136" -and $RunRadio5Start -and $ready5) {
    "PASS_F136_5G_READY"
} elseif ($Profile -eq "F136" -and $RunRadio5Start -and $txPowerZero) {
    "F136_5G_TXPOWER_ZERO"
} elseif ($Profile -eq "F137" -and $RunRadio5Start -and $ready5) {
    "PASS_F137_5G_READY"
} elseif ($Profile -eq "F137" -and $RunRadio5Start -and $visibilityProbe) {
    "PASS_F137_VISIBILITY_PROBE"
} elseif ($Profile -eq "F137" -and $RunRadio5Start -and $txPowerZero) {
    "F137_5G_TXPOWER_ZERO"
} elseif ($Profile -eq "F138" -and $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and -not $hostapdRawEnodev) {
    "PASS_F138_5G_RAW_SOCKET_READY"
} elseif ($Profile -eq "F138" -and $RunRadio5Start -and $hostapdRawEnodev) {
    "F138_HOSTAPD_RAW_SOCKET_ENODEV"
} elseif ($Profile -eq "F138" -and $RunRadio5Start -and -not $hostapdRawFallback) {
    "F138_HOSTAPD_RAW_SOCKET_MARKER_MISSING"
} elseif ($Profile -eq "F139" -and $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and -not $hostapdRawEnodev) {
    "PASS_F139_5G_TXPOWER_READY"
} elseif ($Profile -eq "F139" -and $RunRadio5Start -and -not $wlanTxPowerDefault) {
    "F139_WLAN_TXPOWER_DEFAULT_MARKER_MISSING"
} elseif ($Profile -eq "F139" -and $RunRadio5Start -and -not $txPower21) {
    "F139_TXPOWER_21_READBACK_MISSING"
} elseif ($Profile -eq "F140" -and $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and -not $hostapdRawEnodev) {
    "PASS_F140_5G_TXPOWER_READY"
} elseif ($Profile -eq "F140" -and $RunRadio5Start -and -not $wlanTxPowerDefault) {
    "F140_WLAN_TXPOWER_DEFAULT_MARKER_MISSING"
} elseif ($Profile -eq "F140" -and $RunRadio5Start -and -not $txPower21) {
    "F140_TXPOWER_21_READBACK_MISSING"
} elseif ($Profile -eq "F141" -and $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and -not $hostapdRawEnodev) {
    "PASS_F141_5G_TXPOWER_READY"
} elseif ($Profile -eq "F141" -and $RunRadio5Start -and -not $wlanTxPowerDefault) {
    "F141_WLAN_TXPOWER_DEFAULT_MARKER_MISSING"
} elseif ($Profile -eq "F141" -and $RunRadio5Start -and -not $txPower21) {
    "F141_TXPOWER_21_READBACK_MISSING"
} elseif ($Profile -eq "F141" -and -not $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and -not $hostapdRawEnodev) {
    "PASS_F141_5G_TXPOWER_READY_READONLY"
} elseif ($Profile -eq "F142" -and $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and -not $hostapdRawEnodev) {
    "PASS_F142_5G_DISASSOC_ATOMIC_READY"
} elseif ($Profile -eq "F142" -and -not $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and -not $hostapdRawEnodev) {
    "PASS_F142_5G_DISASSOC_ATOMIC_READY_READONLY"
} elseif ($Profile -eq "F143" -and $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and $qdrvF143 -and -not $hostapdRawEnodev) {
    "PASS_F143_5G_DEFERRED_DMA_FREE_READY"
} elseif ($Profile -eq "F143" -and -not $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and $qdrvF143 -and -not $hostapdRawEnodev) {
    "PASS_F143_5G_DEFERRED_DMA_FREE_READY_READONLY"
} elseif ($Profile -eq "F144" -and $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and $qdrvF144 -and -not $hostapdRawEnodev) {
    "PASS_F144_5G_QDISC_BINDING_READY"
} elseif ($Profile -eq "F144" -and -not $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and $qdrvF144 -and -not $hostapdRawEnodev) {
    "PASS_F144_5G_QDISC_BINDING_READY_READONLY"
} elseif ($Profile -eq "F145" -and $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and $qdrvF145 -and -not $hostapdRawEnodev) {
    "PASS_F145_5G_NODE_SCHEDULER_TRACE_READY"
} elseif ($Profile -eq "F145" -and -not $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and $qdrvF145 -and -not $hostapdRawEnodev) {
    "PASS_F145_5G_NODE_SCHEDULER_TRACE_READY_READONLY"
} elseif ($Profile -eq "F146" -and $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and $qdrvF146 -and -not $hostapdRawEnodev) {
    "PASS_F146_5G_AUC_SUBMIT_TRACE_READY"
} elseif ($Profile -eq "F146" -and -not $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and $qdrvF146 -and -not $hostapdRawEnodev) {
    "PASS_F146_5G_AUC_SUBMIT_TRACE_READY_READONLY"
} elseif ($Profile -eq "F147" -and $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and $qdrvF147 -and -not $hostapdRawEnodev) {
    "PASS_F147_5G_READONLY_GET_READY"
} elseif ($Profile -eq "F147" -and -not $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and $qdrvF147 -and -not $hostapdRawEnodev) {
    "PASS_F147_5G_READONLY_GET_READY_READONLY"
} elseif ($Profile -eq "F148" -and $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and $qdrvF148 -and $wlanF148 -and -not $hostapdRawEnodev) {
    "PASS_F148_5G_SUBPORT_MAP_PAIR_READY"
} elseif ($Profile -eq "F148" -and -not $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and $qdrvF148 -and $wlanF148 -and -not $hostapdRawEnodev) {
    "PASS_F148_5G_SUBPORT_MAP_PAIR_READY_READONLY"
} elseif ($Profile -eq "F149" -and $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and $qdrvF148 -and $wlanF148 -and $startF149 -and -not $hostapdRawEnodev) {
    "PASS_F149_5G_PERSISTENT_WLAN_CONTRACT_READY"
} elseif ($Profile -eq "F149" -and -not $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $wlanTxPowerDefault -and $txPower21 -and $qdrvF148 -and $wlanF148 -and $startF149 -and -not $hostapdRawEnodev) {
    "PASS_F149_5G_PERSISTENT_WLAN_CONTRACT_READY_READONLY"
} elseif ($Profile -eq "F150" -and -not $RunRadio5Start -and $ready5 -and $hostapdRawFallback -and $txPower21 -and $qdrvF148 -and $wlanF148 -and $startF149 -and $radio5AutostartEnabled -and -not $hostapdRawEnodev) {
    "PASS_F150_5G_AUTOSTART_READY_READONLY"
} elseif ($Profile -eq "F151" -and -not $RunRadio5Start -and $ready5 -and $txPower21 -and $qdrvF148 -and $wlanF148 -and $startF151 -and $radio5AutostartEnabled -and $radio5OpenLabDisabled -and $wpa2Ready -and -not $hostapdRawEnodev) {
    "PASS_F151_5G_WPA2_READY_READONLY"
} elseif ($Profile -eq "F152" -and -not $RunRadio5Start -and $ready5 -and $txPower21 -and $qdrvF148 -and $wlanF152 -and $startF152 -and $radio5AutostartEnabled -and $radio5OpenLabDisabled -and $wpa2Ready -and -not $hostapdRawEnodev) {
    "PASS_F152_5G_INACTIVITY_TRACE_READY_READONLY"
} elseif ($Profile -eq "F153" -and -not $RunRadio5Start -and $ready5 -and $txPower21 -and $qdrvF153 -and $wlanF152 -and $startF153 -and $radio5AutostartEnabled -and $radio5OpenLabDisabled -and $wpa2Ready -and -not $hostapdRawEnodev) {
    "PASS_F153_5G_RX_INACTIVITY_REFRESH_READY_READONLY"
} elseif ($Profile -eq "F154" -and -not $RunRadio5Start -and $ready5 -and $txPower21 -and $qdrvF154 -and $wlanF152 -and $startF154 -and $radio5AutostartEnabled -and $radio5OpenLabDisabled -and $wpa2Ready -and -not $hostapdRawEnodev) {
    "PASS_F154_5G_GSO_SEGMENT_READY_READONLY"
} elseif ($Profile -eq "F155" -and -not $RunRadio5Start -and $ready5 -and $txPower21 -and $qdrvF155 -and $wlanF152 -and $startF155 -and $radio5AutostartEnabled -and $radio5OpenLabDisabled -and $wpa2Ready -and -not $hostapdRawEnodev) {
    "PASS_F155_5G_TXPOOL_TRACE_READY_READONLY"
} elseif ($Profile -eq "F156" -and -not $RunRadio5Start -and $ready5 -and $txPower21 -and $qdrvF155 -and $wlanF152 -and $startF156 -and $txBaDisabled -and $radio5AutostartEnabled -and $radio5OpenLabDisabled -and $wpa2Ready -and -not $hostapdRawEnodev) {
    "PASS_F156_5G_TXBA_STABLE_READY_READONLY"
} elseif ($Profile -eq "F157" -and -not $RunRadio5Start -and $ready5 -and $txPower21 -and $qdrvF155 -and $wlanF152 -and $startF157 -and $txBaDisabled -and $wifi0Bridged -and $wifi0NoIpv4 -and $radio5AutostartEnabled -and $radio5OpenLabDisabled -and $wpa2Ready -and -not $hostapdRawEnodev) {
    "PASS_F157_5G_PERSISTENT_BRIDGE_READY_READONLY"
} elseif ($Profile -eq "F158" -and -not $RunRadio5Start -and $ready5 -and $txPower21 -and $qdrvF155 -and $wlanF152 -and $startF157 -and $txBaDisabled -and $wifi0Bridged -and $wifi0NoIpv4 -and $radioModulesF158 -and $twoGGuardOff -and $twoGReclaimOff -and $twoGGuard64 -and $twoGGuard32 -and $radio5AutostartEnabled -and $radio5OpenLabDisabled -and $wpa2Ready -and -not $hostapdRawEnodev) {
    "PASS_F158_DUAL_RADIO_POLICY_READY_READONLY"
} elseif ($Profile -eq "F159" -and -not $RunRadio5Start -and $ready5 -and $txPower21 -and $qdrvF155 -and $wlanF152 -and $startF157 -and $txBaDisabled -and $wifi0Bridged -and $wifi0NoIpv4 -and $radioModulesF158 -and $rtlPciF159 -and $twoGGuardOff -and $twoGReclaimOff -and $twoGGuard64 -and $twoGGuard32 -and $radio5AutostartEnabled -and $radio5OpenLabDisabled -and $wpa2Ready -and -not $hostapdRawEnodev) {
    "PASS_F159_DUAL_RADIO_HISTORICAL_RTLPCI_READY_READONLY"
} elseif ($Profile -eq "F160" -and -not $RunRadio5Start -and $ready5 -and $txPower21 -and $qdrvF155 -and $wlanF152 -and $startF157 -and $txBaDisabled -and $wifi0Bridged -and $wifi0NoIpv4 -and $radioModulesF160 -and $rtlPciF160 -and $twoGGuardOff -and $twoGReclaimOff -and $twoGGuard64 -and $twoGGuard32 -and $twoGSummaryOn -and $radio5AutostartEnabled -and $radio5OpenLabDisabled -and $wpa2Ready -and -not $hostapdRawEnodev) {
    "PASS_F160_DUAL_RADIO_2G_BE_SUMMARY_READY_READONLY"
} elseif ($Profile -eq "F161" -and -not $RunRadio5Start -and $ready5 -and $txPower21 -and $qdrvF155 -and $wlanF152 -and $startF157 -and $txBaDisabled -and $wifi0Bridged -and $wifi0NoIpv4 -and $radioModulesF161 -and $rtlPciF160 -and $twoGGuardOff -and $twoGReclaimOff -and $twoGGuard64 -and $twoGGuard32 -and $twoGSummaryOn -and $twoGOemTxReportOn -and $radio5AutostartEnabled -and $radio5OpenLabDisabled -and $wpa2Ready -and -not $hostapdRawEnodev) {
    "PASS_F161_DUAL_RADIO_2G_OEM_TX_REPORT_READY_READONLY"
} elseif ($Profile -eq "F162" -and -not $RunRadio5Start -and $ready5 -and $txPower21 -and $qdrvF155 -and $wlanF152 -and $startF157 -and $txBaDisabled -and $wifi0Bridged -and $wifi0NoIpv4 -and $switchTqeF162 -and $tqeReadonlyV1 -and $radio5AutostartEnabled -and $radio5OpenLabDisabled -and $wpa2Ready -and -not $hostapdRawEnodev) {
    "PASS_F162_DUAL_RADIO_TQE_READONLY_READY"
} elseif ($Profile -eq "F163" -and -not $RunRadio5Start -and $ready5 -and $txPower21 -and $qdrvF155 -and $wlanF152 -and $startF157 -and $txBaDisabled -and $wifi0Bridged -and $wifi0NoIpv4 -and $switchTqeF162 -and $tqeReadonlyV1 -and $radio5AutostartEnabled -and $radio5OpenLabDisabled -and $wpa2Ready -and -not $hostapdRawEnodev) {
    "PASS_F163_DUAL_RADIO_EMAC_RXRESTART16_READY"
} elseif ($RunRadio5Start -and $Profile -eq "F133" -and $ready5) {
    "PASS_F133_5G_READY"
} elseif ($RunRadio5Start -and $Profile -eq "F133" -and $txPowerZero) {
    "F133_5G_TXPOWER_ZERO"
} elseif (-not $RunRadio5Start -and $twoGEnabled) {
    "PASS_READ_ONLY_BASELINE"
} else {
    "OBSERVED_NEEDS_REVIEW"
}

Write-Status $terminal "post-flash F13x gate completed" @{
    wait = $wait
    ssh_rc = $rc
    tcp22_after = $tcpAfter
    transcript_complete = $complete
    radio5_start_rc = $radio5Rc
    fatal_marker = $fatal
    radio2g_enabled_marker = $twoGEnabled
    f134_rf_hold_marker = $rfHold
    f135_core_hold_marker = $coreHold
    f133_ready_marker = $ready5
    txpower_zero_marker = $txPowerZero
    visibility_probe_marker = $visibilityProbe
    hostapd_raw_fallback_marker = $hostapdRawFallback
    hostapd_raw_enodev_marker = $hostapdRawEnodev
    wlan_txpower_default_marker = $wlanTxPowerDefault
    txpower_21_marker = $txPower21
    f143_qdrv_hash_marker = $qdrvF143
    f144_qdrv_hash_marker = $qdrvF144
    f145_qdrv_hash_marker = $qdrvF145
    f146_qdrv_hash_marker = $qdrvF146
    f147_qdrv_hash_marker = $qdrvF147
    f148_qdrv_hash_marker = $qdrvF148
    f148_wlan_hash_marker = $wlanF148
    f149_start_hash_marker = $startF149
    f151_start_hash_marker = $startF151
    f152_wlan_hash_marker = $wlanF152
    f152_start_hash_marker = $startF152
    f153_qdrv_hash_marker = $qdrvF153
    f153_start_hash_marker = $startF153
    f154_qdrv_hash_marker = $qdrvF154
    f154_start_hash_marker = $startF154
    f155_qdrv_hash_marker = $qdrvF155
    f155_start_hash_marker = $startF155
    f156_start_hash_marker = $startF156
    tx_ba_disabled_marker = $txBaDisabled
    f157_start_hash_marker = $startF157
    wifi0_bridged_marker = $wifi0Bridged
    wifi0_no_ipv4_marker = $wifi0NoIpv4
    f158_radio_modules_hash_marker = $radioModulesF158
    radio2g_guard_off_marker = $twoGGuardOff
    radio2g_reclaim_off_marker = $twoGReclaimOff
    radio2g_guard_high64_marker = $twoGGuard64
    radio2g_guard_low32_marker = $twoGGuard32
    f159_rtl_pci_hash_marker = $rtlPciF159
    f160_rtl_pci_hash_marker = $rtlPciF160
    f160_radio_modules_hash_marker = $radioModulesF160
    radio2g_be_summary_on_marker = $twoGSummaryOn
    f161_radio_modules_hash_marker = $radioModulesF161
    radio2g_oem_tx_report_on_marker = $twoGOemTxReportOn
    f162_switch_tqe_hash_marker = $switchTqeF162
    tqe_readonly_v1_marker = $tqeReadonlyV1
    radio5_autostart_enabled_marker = $radio5AutostartEnabled
    radio5_open_lab_disabled_marker = $radio5OpenLabDisabled
    wpa2_ready_marker = $wpa2Ready
    stdout = $stdout
    stderr = $stderr
}
Get-Content -Raw -LiteralPath $StatusPath

if ($terminal -like "PASS_*") { exit 0 }
exit 1
