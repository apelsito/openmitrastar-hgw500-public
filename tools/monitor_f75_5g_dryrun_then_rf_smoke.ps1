[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$DryRunStatusPath = "/workspace/user-home\Desktop\MitraStar\outputs\postflash\f75-2g-pass-then-5g-dryrun-20260826-172243\status.json",
    [int]$TimeoutSeconds = 21600,
    [int]$PollSeconds = 10,
    [string]$HostAddress = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "/workspace/user-home\Desktop\MitraStar\.codex_tmp\openmitrastar_ramssh_client_ed25519",
    [ValidateRange(5, 120)]
    [int]$RfSeconds = 20,
    [int]$SshTimeoutSeconds = 240,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f75-5g-dryrun-pass-then-rf-smoke-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$statusOut = Join-Path $OutputDir "status.json"
$logPath = Join-Path $OutputDir "monitor.log"
$sshOut = Join-Path $OutputDir "five-g-rf-smoke.stdout.log"
$sshErr = Join-Path $OutputDir "five-g-rf-smoke.stderr.log"
$resultOut = Join-Path $OutputDir "result.json"

function Write-JsonFile([string]$Path, [hashtable]$Payload) {
    $Payload.updated_at = (Get-Date).ToString("o")
    $Payload.output_dir = $OutputDir
    $Payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $Path
}

function Write-Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = @{
        schema = "openmitrastar.f75-5g-rf-smoke-monitor/v1"
        state = $State
        message = $Message
        dryrun_status_path = $DryRunStatusPath
        host = $HostAddress
        rf_seconds = $RfSeconds
        poll_seconds = $PollSeconds
        timeout_seconds = $TimeoutSeconds
    }
    foreach ($key in $Extra.Keys) {
        $payload[$key] = $Extra[$key]
    }
    Write-JsonFile $statusOut $payload
}

function Read-JsonOrNull([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-ObjectProperty($Object, [string]$Name) {
    if ($null -eq $Object) { return $null }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $null }
    return $prop.Value
}

function Test-TcpQuiet([string]$HostName, [int]$Port, [int]$TimeoutMs = 2000) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Invoke-5gRfSmoke {
    $ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
    $sshKeyscan = Join-Path $env:WINDIR "System32\OpenSSH\ssh-keyscan.exe"
    $knownHosts = Join-Path $OutputDir "known_hosts"

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

    $remote = @'
set -u
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH
echo OMF75_5G_RF_SMOKE_BEGIN
echo SECTION_PRE_TOPOLOGY
ip -br link 2>/dev/null || ifconfig -a
brctl show 2>/dev/null || true
ls -1 /sys/class/net/br0/brif 2>/dev/null || true
echo SECTION_START
/usr/sbin/om-radio5-start
start_rc=$?
echo OMF75_5G_RF_SMOKE_START_RC=$start_rc
echo SECTION_RF_WINDOW
sleep __RF_SECONDS__
echo SECTION_QTN_SNAPSHOT
if command -v iwconfig-qtn >/dev/null 2>&1; then /usr/sbin/iwconfig-qtn wifi0 2>&1 || true; fi
if command -v iwpriv-qtn >/dev/null 2>&1; then
    /usr/sbin/iwpriv-qtn wifi0 get_mode 2>&1 || true
    /usr/sbin/iwpriv-qtn wifi0 get_vht 2>&1 || true
    /usr/sbin/iwpriv-qtn wifi0 get_bwselect 2>&1 || true
fi
if command -v hostapd-cli-qtn >/dev/null 2>&1; then
    /usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping 2>&1 || true
    /usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 status 2>&1 || true
    /usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 all_sta 2>&1 || true
fi
echo SECTION_WIFI0_SYSFS
if [ -e /sys/class/net/wifi0 ]; then
    for p in /sys/class/net/wifi0/operstate /sys/class/net/wifi0/carrier /sys/class/net/wifi0/address /sys/class/net/wifi0/flags; do
        [ -r "$p" ] && printf '%s=' "$p" && cat "$p"
    done
fi
echo SECTION_DMESG_QTN_TAIL
dmesg | grep -E 'OMRADIO5|OMQTN|qdrv|wifi0|hostapd-qtn|MuC|HLINK|EV_TLB|EV_ProtV|Oops|BUG|panic' | tail -n 260 || true
echo SECTION_STOP
/usr/sbin/om-radio5-stop f75-rf-smoke
stop_rc=$?
echo OMF75_5G_RF_SMOKE_STOP_RC=$stop_rc
echo SECTION_POST_TOPOLOGY
ip -br addr 2>/dev/null || ifconfig -a
brctl show 2>/dev/null || true
ls -1 /sys/class/net/br0/brif 2>/dev/null || true
echo OMF75_5G_RF_SMOKE_END
exit $start_rc
'@
    $remote = $remote.Replace("__RF_SECONDS__", [string]$RfSeconds)

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
        -RedirectStandardOutput $sshOut -RedirectStandardError $sshErr
    if (-not $proc.WaitForExit($SshTimeoutSeconds * 1000)) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        return @{
            terminal_state = "FIVE_G_RF_SMOKE_SSH_TIMEOUT"
            ssh_exit_code = 124
            stdout = $sshOut
            stderr = $sshErr
            management_tcp22_after = Test-TcpQuiet $HostAddress 22
        }
    }

    $proc.Refresh()
    $text = if (Test-Path -LiteralPath $sshOut) { Get-Content -LiteralPath $sshOut -Raw } else { "" }
    $complete = $text.Contains("OMF75_5G_RF_SMOKE_BEGIN") -and $text.Contains("OMF75_5G_RF_SMOKE_END")
    $ready = [bool]($text -match "OMRADIO5_READY")
    $startRc = $null
    $stopRc = $null
    if ($text -match "OMF75_5G_RF_SMOKE_START_RC=(\d+)") { $startRc = [int]$Matches[1] }
    if ($text -match "OMF75_5G_RF_SMOKE_STOP_RC=(\d+)") { $stopRc = [int]$Matches[1] }
    $fatal = [bool]($text -match "MuC exception|HLINK MSG timed out|EV_TLB|EV_ProtV|Oops|BUG|kernel panic|panic:")
    $wifi0InBr0 = [bool]($text -match "(?m)^wifi0$")
    $hostapdPong = [bool]($text -match "(?m)^PONG$")
    $carrierOne = [bool]($text -match "/sys/class/net/wifi0/carrier=1")
    $tcp22After = Test-TcpQuiet $HostAddress 22

    $terminal = if (-not $complete) {
        "FIVE_G_RF_SMOKE_INCOMPLETE"
    } elseif ($fatal) {
        "FIVE_G_RF_SMOKE_FATAL_MARKER"
    } elseif ($wifi0InBr0) {
        "FIVE_G_RF_SMOKE_WIFI0_BRIDGED"
    } elseif (-not $tcp22After) {
        "FIVE_G_RF_SMOKE_MANAGEMENT_LOST"
    } elseif ($ready -and $startRc -eq 0 -and $stopRc -eq 0) {
        "PASS_5G_RF_SMOKE"
    } else {
        "FIVE_G_RF_SMOKE_FAIL"
    }

    return @{
        terminal_state = $terminal
        ssh_exit_code = [int]$proc.ExitCode
        transcript_complete = $complete
        omradio5_ready = $ready
        start_rc = $startRc
        stop_rc = $stopRc
        hostapd_qtn_pong = $hostapdPong
        wifi0_carrier_one = $carrierOne
        wifi0_in_br0 = $wifi0InBr0
        fatal_marker = $fatal
        management_tcp22_after = $tcp22After
        stdout = $sshOut
        stderr = $sshErr
    }
}

"F75_5G_RF_SMOKE_MONITOR_START at=$(Get-Date -Format o) dryrun=$DryRunStatusPath" |
    Add-Content -Encoding ascii -LiteralPath $logPath
Write-Status "watching" "waiting for 5G dry-run PASS"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    $dryStatus = Read-JsonOrNull $DryRunStatusPath
    $dryState = if ($dryStatus) { [string](Get-ObjectProperty $dryStatus "state") } else { "missing" }
    $dryResultPath = if ($dryStatus) { [string](Get-ObjectProperty $dryStatus "result") } else { "" }
    $dryTerminal = if ($dryStatus) { [string](Get-ObjectProperty $dryStatus "five_g_terminal_state") } else { "" }

    "F75_5G_RF_SMOKE_POLL at=$(Get-Date -Format o) dry_state=$dryState dry_terminal=$dryTerminal result=$dryResultPath" |
        Add-Content -Encoding ascii -LiteralPath $logPath

    if ($dryState -eq "pass" -or $dryTerminal -eq "PASS_2G_AND_5G_DRYRUN") {
        Write-Status "running_rf_smoke" "5G dry-run passed; running bounded RF smoke" @{
            dryrun_result = $dryResultPath
            dryrun_terminal_state = $dryTerminal
        }
        $rf = Invoke-5gRfSmoke
        Write-JsonFile $resultOut @{
            schema = "openmitrastar.f75-5g-rf-smoke-result/v1"
            terminal_state = $rf.terminal_state
            dryrun_status_path = $DryRunStatusPath
            dryrun_result = $dryResultPath
            dryrun_terminal_state = $dryTerminal
            five_g_rf_smoke = $rf
            flash = $false
            router_mutations = $true
        }
        Write-Status $(if ($rf.terminal_state -eq "PASS_5G_RF_SMOKE") { "pass" } else { "failed" }) "5G RF smoke completed" @{
            result = $resultOut
            five_g_terminal_state = $rf.terminal_state
        }
        if ($rf.terminal_state -eq "PASS_5G_RF_SMOKE") { exit 0 }
        exit 1
    }

    if ($dryState -in @("failed", "blocked_by_2g_gate", "timeout")) {
        Write-Status "blocked_by_dryrun" "5G dry-run did not pass; RF smoke not started" @{
            dryrun_state = $dryState
            dryrun_terminal_state = $dryTerminal
            dryrun_result = $dryResultPath
        }
        Write-JsonFile $resultOut @{
            schema = "openmitrastar.f75-5g-rf-smoke-result/v1"
            terminal_state = "BLOCKED_BY_5G_DRYRUN"
            dryrun_state = $dryState
            dryrun_terminal_state = $dryTerminal
            dryrun_result = $dryResultPath
            flash = $false
            router_mutations = $false
        }
        exit 1
    }

    Write-Status "watching" "waiting for 5G dry-run PASS" @{
        dryrun_state = $dryState
        dryrun_terminal_state = $dryTerminal
        dryrun_result = $dryResultPath
    }
    Start-Sleep -Seconds $PollSeconds
}

Write-Status "timeout" "timeout waiting for 5G dry-run PASS"
Write-JsonFile $resultOut @{
    schema = "openmitrastar.f75-5g-rf-smoke-result/v1"
    terminal_state = "TIMEOUT_WAITING_5G_DRYRUN"
    dryrun_status_path = $DryRunStatusPath
    flash = $false
    router_mutations = $false
}
exit 1
