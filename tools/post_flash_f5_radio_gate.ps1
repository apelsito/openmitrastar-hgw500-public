[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$HostAddress = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "$env:USERPROFILE\.ssh\id_ed25519",
    [string]$OracleHost = "192.168.1.63",
    [string]$OracleUser = "AELITA",
    [string]$ControllerUrl = "http://192.168.1.43:8008/speed.bin",
    [switch]$Run2gProbe,
    [double]$Min2gMbps = 5.0,
    [int]$PingCount = 3,
    [int]$SshTimeoutSeconds = 15,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f5-radio-gate-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$resultPath = Join-Path $OutputDir "result.json"
$sshOut = Join-Path $OutputDir "ssh-smoke.stdout.log"
$sshErr = Join-Path $OutputDir "ssh-smoke.stderr.log"
$twoGLowOut = Join-Path $OutputDir "two-g-low-throughput.stdout.log"
$twoGLowErr = Join-Path $OutputDir "two-g-low-throughput.stderr.log"

function Write-JsonResult([hashtable]$Result) {
    $Result.updated_at = (Get-Date).ToString("o")
    $Result.output_dir = $OutputDir
    $Result | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $resultPath
}

function Invoke-PingGate {
    $ok = Test-Connection -ComputerName $HostAddress -Count $PingCount -Quiet
    return @{
        ok = [bool]$ok
        host = $HostAddress
        count = $PingCount
    }
}

function Invoke-SshGate {
    $remote = @'
echo OMPOST_FLASH_SSH_OK
echo SECTION_UNAME
uname -r
echo SECTION_UPTIME
cat /proc/uptime
echo SECTION_NETDEV
cat /proc/net/dev
echo SECTION_INTERRUPTS
cat /proc/interrupts
echo SECTION_LINKS
ip -br link 2>/dev/null || ifconfig -a
echo SECTION_RADIO_MODULES
lsmod 2>/dev/null | grep -E 'rtl|qdrv|qtn|cfg80211|mac80211' || true
echo SECTION_HOSTAPD
ps w 2>/dev/null | grep -E 'hostapd|qcsapi|wpa' | grep -v grep || true
echo SECTION_DMESG_EMAC_TAIL
dmesg | tail -n 160 | grep -E 'OMEMAC|qtn-topaz-emac|OMNETWORK_READY|OMSSH_READY|rtl8192ee|qdrv|wifi0|wlan0' || true
echo OMPOST_FLASH_DONE
'@
    $ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
    $sshKeygen = Join-Path $env:WINDIR "System32\OpenSSH\ssh-keygen.exe"
    $sshKeyscan = Join-Path $env:WINDIR "System32\OpenSSH\ssh-keyscan.exe"
    $knownHosts = Join-Path $OutputDir "known_hosts"
    if (Test-Path -LiteralPath $knownHosts) {
        & $sshKeygen -R $HostAddress -f $knownHosts *> $null
    }
    $scan = & $sshKeyscan -T 5 -t ed25519,rsa $HostAddress 2>$null |
        Where-Object { $_ -and -not $_.StartsWith("#") }
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
    $proc = Start-Process -FilePath $ssh -ArgumentList $sshArgs -NoNewWindow -PassThru -RedirectStandardOutput $sshOut -RedirectStandardError $sshErr
    if (-not $proc.WaitForExit($SshTimeoutSeconds * 1000)) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        return @{ ok = $false; exit_code = 124; classification = "SSH_TIMEOUT"; stdout = $sshOut; stderr = $sshErr }
    }
    $text = ""
    if (Test-Path -LiteralPath $sshOut) {
        $text = Get-Content -LiteralPath $sshOut -Raw
    }
    return @{
        ok = ($proc.ExitCode -eq 0 -and $text.Contains("OMPOST_FLASH_SSH_OK") -and $text.Contains("OMPOST_FLASH_DONE"))
        exit_code = $proc.ExitCode
        classification = if ($proc.ExitCode -eq 0) { "SSH_OK" } else { "SSH_FAIL" }
        stdout = $sshOut
        stderr = $sshErr
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
dmesg | grep -E 'OMRTLBE|OMRTLQGUARD|OMRTLRA|OMRTLMGMT|rtl8192ee|wlan0|BE_QUEUE|TXBD' | tail -n 260 || true
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
    $proc = Start-Process -FilePath $ssh -ArgumentList $sshArgs -NoNewWindow -PassThru -RedirectStandardOutput $twoGLowOut -RedirectStandardError $twoGLowErr
    if (-not $proc.WaitForExit($SshTimeoutSeconds * 1000)) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        return @{ ok = $false; exit_code = 124; classification = "LOW_2G_EVIDENCE_TIMEOUT"; stdout = $twoGLowOut; stderr = $twoGLowErr }
    }
    $text = ""
    if (Test-Path -LiteralPath $twoGLowOut) {
        $text = Get-Content -LiteralPath $twoGLowOut -Raw
    }
    return @{
        ok = ($proc.ExitCode -eq 0 -and $text.Contains("OM2G_LOW_EVIDENCE_BEGIN") -and $text.Contains("OM2G_LOW_EVIDENCE_END"))
        exit_code = $proc.ExitCode
        classification = if ($proc.ExitCode -eq 0) { "LOW_2G_EVIDENCE_OK" } else { "LOW_2G_EVIDENCE_FAIL" }
        stdout = $twoGLowOut
        stderr = $twoGLowErr
    }
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
    $download = $summary.controller_download
    if (-not $download -and $payload) {
        $download = $payload.test.controller_download
    }
    $speedBps = $null
    $speedMbps = $null
    if ($download -and $null -ne $download.speed_Bps) {
        $speedBps = [int]$download.speed_Bps
        $speedMbps = [Math]::Round(($speedBps * 8.0) / 1000000.0, 2)
    }
    $throughputClass = if ($null -eq $speedBps) {
        "NO_DOWNLOAD"
    } elseif ($speedBps -lt 125000) {
        "DEGRADED_LT_1MBPS"
    } elseif ($speedBps -lt 1250000) {
        "USABLE_LT_10MBPS"
    } else {
        "PASS_GE_10MBPS"
    }
    return @{
        available = $true
        summary = $summaryPath
        aelita_result_path = $summary.aelita_result_path
        aelita_rc = $summary.aelita_rc
        effective_aelita_rc = $summary.effective_aelita_rc
        connected = [bool]($payload -and $payload.test.connected)
        ping_ok = [bool]($payload -and $payload.test.router_ping.pass)
        download_ok = [bool]($download -and $download.pass)
        speed_Bps = $speedBps
        speed_Mbps = $speedMbps
        min_Mbps = $Min2gMbps
        meets_min = [bool]($null -ne $speedMbps -and $speedMbps -ge $Min2gMbps)
        throughput_class = $throughputClass
        irq28_delta = $summary.irq28_delta
        first_station = $summary.first_station
        last_station = $summary.last_station
    }
}

$result = [ordered]@{
    schema = "openmitrastar.f5-postflash-radio-gate/v1"
    host = $HostAddress
    flash = $false
    reboot = $false
    router_mutations = $false
    ping = $null
    ssh = $null
    diagnose = $null
    two_g_probe = $null
    two_g_summary = $null
    two_g_low_evidence = $null
    terminal_state = "STARTED"
}

try {
    $result.ping = Invoke-PingGate

    $diagStamp = Split-Path -Leaf $OutputDir
    $diagDir = Join-Path $Root "outputs\recovery\ssh-management\$diagStamp"
    & python (Join-Path $PSScriptRoot "diagnose_hgw500_ssh_management.py") --host $HostAddress --output-dir $diagDir *> (Join-Path $OutputDir "diagnose.stdout.log")
    $result.diagnose = @{
        exit_code = $LASTEXITCODE
        output_dir = $diagDir
    }

    if ($result.ping.ok) {
        $result.ssh = Invoke-SshGate
    } else {
        $result.ssh = @{ ok = $false; exit_code = $null; classification = "PING_FAIL_SKIPPED"; stdout = $sshOut; stderr = $sshErr }
    }

    if ($Run2gProbe -and $result.ssh.ok) {
        $probeDir = Join-Path $OutputDir "aelita-2g"
        & python (Join-Path $PSScriptRoot "run_aelita_2g_wpa2_speed_router_probe.py") `
            --router-host $HostAddress `
            --router-user $RouterUser `
            --router-key $RouterKey `
            --oracle-host $OracleHost `
            --oracle-user $OracleUser `
            --controller-url $ControllerUrl `
            --output-dir $probeDir *> (Join-Path $OutputDir "aelita-2g.stdout.log")
        $result.two_g_probe = @{
            requested = $true
            exit_code = $LASTEXITCODE
            output_dir = $probeDir
        }
        $result.two_g_summary = Read-2gProbeSummary $probeDir
    } else {
        $result.two_g_probe = @{
            requested = [bool]$Run2gProbe
            skipped = $true
            reason = if ($Run2gProbe) { "ssh_not_ready" } else { "not_requested" }
        }
        $result.two_g_summary = @{
            available = $false
            reason = $result.two_g_probe.reason
        }
    }

    if ($Run2gProbe -and $result.ssh.ok -and
        ($result.two_g_probe.exit_code -ne 0 -or
         ($result.two_g_summary.available -and -not $result.two_g_summary.meets_min))) {
        $result.two_g_low_evidence = Invoke-2gLowThroughputEvidence
    }

    if ($result.ssh.ok) {
        $result.terminal_state = "PASS_SSH_READY"
        if ($Run2gProbe -and $result.two_g_probe.exit_code -eq 0 -and
            $result.two_g_summary.meets_min) {
            $result.terminal_state = "PASS_SSH_AND_2G_PROBE"
        } elseif ($Run2gProbe -and $result.two_g_probe.exit_code -eq 0) {
            $result.terminal_state = "SSH_READY_2G_THROUGHPUT_LOW"
        } elseif ($Run2gProbe) {
            $result.terminal_state = "SSH_READY_2G_PROBE_FAIL"
        }
    } elseif ($result.ping.ok) {
        $result.terminal_state = "PING_ONLY_SSH_NOT_READY"
    } else {
        $result.terminal_state = "NO_MANAGEMENT"
    }

    Write-JsonResult $result
    Get-Content -LiteralPath $resultPath -Raw
    if ($result.terminal_state -like "PASS*") { exit 0 }
    exit 1
} catch {
    $result.terminal_state = "ERROR"
    $result.error = $_.Exception.Message
    Write-JsonResult $result
    Get-Content -LiteralPath $resultPath -Raw
    exit 1
}
