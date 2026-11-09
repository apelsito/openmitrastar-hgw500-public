[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$MonitorStatusPath = "/workspace/user-home\Desktop\MitraStar\outputs\postflash\router-ssh-radio-monitor-f75-20260826-171050\monitor-status.json",
    [int]$TimeoutSeconds = 21600,
    [int]$PollSeconds = 10,
    [string]$HostAddress = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "/workspace/user-home\Desktop\MitraStar\.codex_tmp\openmitrastar_ramssh_client_ed25519",
    [int]$SshTimeoutSeconds = 45,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f75-2g-pass-then-5g-dryrun-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$statusOut = Join-Path $OutputDir "status.json"
$logPath = Join-Path $OutputDir "monitor.log"
$sshOut = Join-Path $OutputDir "five-g-dryrun.stdout.log"
$sshErr = Join-Path $OutputDir "five-g-dryrun.stderr.log"
$resultOut = Join-Path $OutputDir "result.json"

function Write-JsonFile([string]$Path, [hashtable]$Payload) {
    $Payload.updated_at = (Get-Date).ToString("o")
    $Payload.output_dir = $OutputDir
    $Payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $Path
}

function Write-Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = @{
        schema = "openmitrastar.f75-2g-then-5g-dryrun-monitor/v1"
        state = $State
        message = $Message
        monitor_status_path = $MonitorStatusPath
        host = $HostAddress
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

function Invoke-5gDryRun {
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
echo OMF75_5G_DRYRUN_BEGIN
echo SECTION_PRE_TOPOLOGY
ip -br link 2>/dev/null || ifconfig -a
brctl show 2>/dev/null || true
ls -1 /sys/class/net/br0/brif 2>/dev/null || true
echo SECTION_QTN_PREP
/usr/sbin/om-qtn-cal-readonly
/usr/sbin/om-qtn-mac-prepare
echo SECTION_OM_RADIO5_DRYRUN
OM_RADIO5_NO_SIDE_EFFECTS=1 /usr/sbin/om-radio5-start
radio5_rc=$?
echo OMF75_OM_RADIO5_DRYRUN_RC="$radio5_rc"
echo SECTION_POST_TOPOLOGY
ip -br addr 2>/dev/null || ifconfig -a
brctl show 2>/dev/null || true
ls -1 /sys/class/net/br0/brif 2>/dev/null || true
if [ -e /sys/class/net/wifi0 ]; then
    for p in /sys/class/net/wifi0/operstate /sys/class/net/wifi0/carrier /sys/class/net/wifi0/address; do
        [ -r "$p" ] && printf '%s=' "$p" && cat "$p"
    done
fi
echo SECTION_DMESG_QTN_TAIL
dmesg | grep -E 'OMRADIO5|OMQTN|qdrv|wifi0|MuC|HLINK|EV_TLB|EV_ProtV|Oops|BUG|panic' | tail -n 180 || true
echo OMF75_5G_DRYRUN_END
'@

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
            terminal_state = "FIVE_G_DRYRUN_SSH_TIMEOUT"
            ssh_exit_code = 124
            stdout = $sshOut
            stderr = $sshErr
        }
    }
    $proc.Refresh()
    $text = if (Test-Path -LiteralPath $sshOut) { Get-Content -LiteralPath $sshOut -Raw } else { "" }
    $complete = $text.Contains("OMF75_5G_DRYRUN_BEGIN") -and $text.Contains("OMF75_5G_DRYRUN_END")
    $dryrunExitCode = $null
    if ($text -match "OMF75_OM_RADIO5_DRYRUN_RC=([0-9]+)") {
        $dryrunExitCode = [int]$Matches[1]
    }
    $dryPass = [bool](($text -match "OMRADIO5_DRY_RUN_PASS") -or ($null -ne $dryrunExitCode -and $dryrunExitCode -eq 0))
    $isolated = [bool]($text -match "topology=isolated-l3|wifi0[^\r\n]*192\.168\.77\.1")
    $wifi0InBr0 = [bool]($text -match "(?m)^wifi0$")
    $fatal = [bool]($text -match "MuC exception|HLINK MSG timed out|EV_TLB|EV_ProtV|Oops|BUG|kernel panic|panic:")
    $profile = $null
    if ($text -match "qdrv_profile=([^\s]+)") {
        $profile = $Matches[1]
    }
    $terminal = if (-not $complete) {
        "FIVE_G_DRYRUN_INCOMPLETE"
    } elseif ($fatal) {
        "FIVE_G_DRYRUN_FATAL_MARKER"
    } elseif ($wifi0InBr0) {
        "FIVE_G_DRYRUN_WIFI0_BRIDGED"
    } elseif ($dryPass -and $isolated) {
        "PASS_2G_AND_5G_DRYRUN"
    } elseif ($dryPass -and -not $wifi0InBr0) {
        "PASS_2G_AND_5G_DRYRUN"
    } elseif ($dryPass) {
        "FIVE_G_DRYRUN_TOPOLOGY_UNPROVEN"
    } else {
        "FIVE_G_DRYRUN_FAIL"
    }
    return @{
        terminal_state = $terminal
        ssh_exit_code = [int]$proc.ExitCode
        transcript_complete = $complete
        dryrun_pass_marker = $dryPass
        dryrun_exit_code = $dryrunExitCode
        wifi0_isolated_l3 = $isolated
        wifi0_in_br0 = $wifi0InBr0
        fatal_marker = $fatal
        qdrv_profile = $profile
        stdout = $sshOut
        stderr = $sshErr
    }
}

"F75_2G_THEN_5G_DRYRUN_MONITOR_START at=$(Get-Date -Format o) monitor=$MonitorStatusPath" |
    Add-Content -Encoding ascii -LiteralPath $logPath
Write-Status "watching" "waiting for F75 radio gate result"

$passing2gStates = @(
    "PASS_TOPOLOGY_AND_2G_SPEED",
    "PASS_TOPOLOGY_2G_SPEED_AND_5G",
    "PASS_MANAGEMENT_AND_TOPOLOGY"
)
$terminalPendingStates = @("watching", "router_ssh_seen")
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    $monitor = Read-JsonOrNull $MonitorStatusPath
    if ($null -eq $monitor) {
        Write-Status "watching" "monitor status not readable yet"
        Start-Sleep -Seconds $PollSeconds
        continue
    }

    $gateResult = [string](Get-ObjectProperty $monitor "gate_result")
    $monitorState = [string](Get-ObjectProperty $monitor "state")
    "F75_2G_THEN_5G_DRYRUN_POLL at=$(Get-Date -Format o) monitor_state=$monitorState gate=$gateResult" |
        Add-Content -Encoding ascii -LiteralPath $logPath

    $gate = $null
    if ($gateResult -and (Test-Path -LiteralPath $gateResult -PathType Leaf)) {
        $gate = Read-JsonOrNull $gateResult
    }
    if ($null -eq $gate) {
        if ($terminalPendingStates -contains $monitorState) {
            Write-Status "watching" "waiting for radio gate result" @{
                monitor_state = $monitorState
                gate_result = $gateResult
            }
            Start-Sleep -Seconds $PollSeconds
            continue
        }
        Write-Status "blocked_no_gate_result" "monitor is no longer pending but no readable gate result exists" @{
            monitor_state = $monitorState
            gate_result = $gateResult
        }
        Write-JsonFile $resultOut @{
            schema = "openmitrastar.f75-2g-then-5g-dryrun-result/v1"
            terminal_state = "BLOCKED_NO_GATE_RESULT"
            monitor_state = $monitorState
            gate_result = $gateResult
            flash = $false
            router_mutations = $false
        }
        exit 1
    }

    $gateTerminal = [string](Get-ObjectProperty $gate "terminal_state")
    if ($passing2gStates -notcontains $gateTerminal) {
        Write-Status "blocked_by_2g_gate" "2G/topology gate did not pass; 5G dry-run not started" @{
            gate_terminal_state = $gateTerminal
            gate_result = $gateResult
        }
        Write-JsonFile $resultOut @{
            schema = "openmitrastar.f75-2g-then-5g-dryrun-result/v1"
            terminal_state = "BLOCKED_BY_2G_GATE"
            gate_terminal_state = $gateTerminal
            gate_result = $gateResult
            flash = $false
            router_mutations = $false
        }
        exit 1
    }

    Write-Status "running_5g_dryrun" "2G/topology gate passed; running 5G manual dry-run" @{
        gate_terminal_state = $gateTerminal
        gate_result = $gateResult
    }
    $dry = Invoke-5gDryRun
    Write-JsonFile $resultOut @{
        schema = "openmitrastar.f75-2g-then-5g-dryrun-result/v1"
        terminal_state = $dry.terminal_state
        gate_terminal_state = $gateTerminal
        gate_result = $gateResult
        five_g_dryrun = $dry
        flash = $false
        router_mutations = $false
    }
    Write-Status $(if ($dry.terminal_state -eq "PASS_2G_AND_5G_DRYRUN") { "pass" } else { "failed" }) "5G dry-run completed" @{
        result = $resultOut
        five_g_terminal_state = $dry.terminal_state
    }
    if ($dry.terminal_state -eq "PASS_2G_AND_5G_DRYRUN") { exit 0 }
    exit 1
}

Write-Status "timeout" "timeout waiting for 2G gate result"
Write-JsonFile $resultOut @{
    schema = "openmitrastar.f75-2g-then-5g-dryrun-result/v1"
    terminal_state = "TIMEOUT_WAITING_2G_GATE"
    monitor_status_path = $MonitorStatusPath
    flash = $false
    router_mutations = $false
}
exit 1
