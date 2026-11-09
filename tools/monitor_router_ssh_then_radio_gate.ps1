[CmdletBinding(PositionalBinding = $false)]
param(
    [int]$TimeoutSeconds = 21600,
    [int]$PollSeconds = 10,
    [string]$HostAddress = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "/workspace/user-home\Desktop\MitraStar\.codex_tmp\openmitrastar_ramssh_client_ed25519",
    [string]$OracleHost = "192.168.1.63",
    [string]$OracleUser = "AELITA",
    [string]$ControllerUrl = "http://192.168.1.43:8008/speed.bin",
    [double]$Min2gMbps = 5.0,
    [double]$Diag2gMbps = 20.0,
    [switch]$Run2gProbe,
    [switch]$Run5gProbe,
    [ValidateSet("txpath", "v6scheduler")]
    [string]$FiveGProfile = "txpath",
    [ValidateRange(60, 900)]
    [int]$FiveGSeconds = 120,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\router-ssh-radio-monitor-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$statusOut = Join-Path $OutputDir "monitor-status.json"
$logPath = Join-Path $OutputDir "monitor.log"

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutSeconds = 3) {
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

function Write-MonitorStatus([string]$State, [string]$Message, [string]$GateResult = "") {
    [ordered]@{
        schema = "openmitrastar.router-ssh-radio-monitor/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        host = $HostAddress
        run_2g_probe = [bool]$Run2gProbe
        run_5g_probe = [bool]$Run5gProbe
        five_g_profile = $FiveGProfile
        five_g_seconds = $FiveGSeconds
        min_2g_mbps = $Min2gMbps
        diag_2g_mbps = $Diag2gMbps
        gate_result = $GateResult
    } | ConvertTo-Json -Depth 6 | Set-Content -Encoding ascii -LiteralPath $statusOut
}

"ROUTER_SSH_RADIO_MONITOR_START at=$(Get-Date -Format o) output=$OutputDir host=$HostAddress" |
    Add-Content -Encoding ascii -LiteralPath $logPath
Write-MonitorStatus "watching" "waiting for router TCP/22"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    $pingOk = [bool](Test-Connection -ComputerName $HostAddress -Count 1 -Quiet -ErrorAction SilentlyContinue)
    $tcp22 = [bool](Test-TcpPort $HostAddress 22 3)
    "ROUTER_SSH_RADIO_MONITOR_POLL at=$(Get-Date -Format o) ping=$pingOk tcp22=$tcp22" |
        Add-Content -Encoding ascii -LiteralPath $logPath

    if ($tcp22) {
        $gateDir = Join-Path $OutputDir "radio-gate"
        $stdoutPath = Join-Path $OutputDir "radio-gate.stdout.log"
        $stderrPath = Join-Path $OutputDir "radio-gate.stderr.log"
        Write-MonitorStatus "router_ssh_seen" "TCP/22 is reachable; starting radio gate" $gateDir

        $gateArgs = @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $PSScriptRoot "post_flash_f65_radio_gate.ps1"),
            "-HostAddress", $HostAddress,
            "-RouterUser", $RouterUser,
            "-RouterKey", $RouterKey,
            "-OracleHost", $OracleHost,
            "-OracleUser", $OracleUser,
            "-ControllerUrl", $ControllerUrl,
            "-OutputDir", $gateDir,
            "-Min2gMbps", "$Min2gMbps",
            "-Diag2gMbps", "$Diag2gMbps",
            "-FiveGProfile", $FiveGProfile,
            "-FiveGSeconds", "$FiveGSeconds"
        )
        if ($Run2gProbe) { $gateArgs += "-Run2gProbe" }
        if ($Run5gProbe) { $gateArgs += "-Run5gProbe" }
        $proc = Start-Process -FilePath "powershell.exe" `
            -WindowStyle Hidden `
            -ArgumentList $gateArgs `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath `
            -Wait `
            -PassThru
        $rc = [int]$proc.ExitCode
        $resultPath = Join-Path $gateDir "result.json"
        Write-MonitorStatus $(if ($rc -eq 0) { "pass" } else { "gate_failed" }) "radio gate rc=$rc" $resultPath
        exit $rc
    }

    Write-MonitorStatus "watching" "waiting for router TCP/22"
    Start-Sleep -Seconds $PollSeconds
}

Write-MonitorStatus "timeout" "timeout waiting for router TCP/22"
exit 1
