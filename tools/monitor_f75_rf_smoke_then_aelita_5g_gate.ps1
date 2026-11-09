[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RfSmokeStatusPath = "/workspace/user-home\Desktop\MitraStar\outputs\postflash\f75-5g-dryrun-pass-then-rf-smoke-20260826-172506\status.json",
    [int]$TimeoutSeconds = 21600,
    [int]$PollSeconds = 10,
    [ValidateRange(60, 900)]
    [int]$Seconds = 90,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f75-rf-smoke-pass-then-aelita-5g-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$statusOut = Join-Path $OutputDir "status.json"
$logPath = Join-Path $OutputDir "monitor.log"
$gateOut = Join-Path $OutputDir "aelita-5g.stdout.log"
$gateErr = Join-Path $OutputDir "aelita-5g.stderr.log"
$resultOut = Join-Path $OutputDir "result.json"

function Write-JsonFile([string]$Path, [hashtable]$Payload) {
    $Payload.updated_at = (Get-Date).ToString("o")
    $Payload.output_dir = $OutputDir
    $Payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $Path
}

function Write-Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = @{
        schema = "openmitrastar.f75-aelita-5g-installed-monitor/v1"
        state = $State
        message = $Message
        rf_smoke_status_path = $RfSmokeStatusPath
        seconds = $Seconds
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

function Invoke-AelitaInstalled5gGate {
    $gateDir = Join-Path $OutputDir "installed-only-gate"
    New-Item -ItemType Directory -Force -Path $gateDir | Out-Null
    $args = @(
        (Join-Path $Root "tools\run_qtn_5g_aelita_installed_only.py"),
        "--execute",
        "--ack", "OPENMITRASTAR_QTN_5G_AELITA_INSTALLED_ONLY",
        "--stable-ack", "OPENMITRASTAR_F75_2G_5G_DRYRUN_RF_SMOKE_PASS",
        "--router-host", "192.168.1.90",
        "--oracle-host", "192.168.1.63",
        "--oracle-user", "AELITA",
        "--restore-ssid", "MOVISTAR-WIFI6-A348",
        "--seconds", "$Seconds",
        "--output-dir", $gateDir
    )
    $proc = Start-Process -FilePath "python" -ArgumentList $args -NoNewWindow -PassThru `
        -RedirectStandardOutput $gateOut -RedirectStandardError $gateErr
    $timeoutMs = [Math]::Max(300000, ($Seconds + 900) * 1000)
    if (-not $proc.WaitForExit($timeoutMs)) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        return @{
            terminal_state = "AELITA_5G_INSTALLED_GATE_TIMEOUT"
            exit_code = 124
            output_dir = $gateDir
            stdout = $gateOut
            stderr = $gateErr
        }
    }
    $proc.Refresh()
    $stdoutText = if (Test-Path -LiteralPath $gateOut) { Get-Content -LiteralPath $gateOut -Raw } else { "" }
    $resultPath = ""
    if ($stdoutText -match "OMQTN5G_AELITA_INSTALLED_ONLY_PASS=1 result=([^\r\n ]+)") {
        $resultPath = $Matches[1].Trim()
    }
    return @{
        terminal_state = if ($proc.ExitCode -eq 0 -and $resultPath) { "PASS_AELITA_5G_INSTALLED_GATE" } else { "AELITA_5G_INSTALLED_GATE_FAIL" }
        exit_code = [int]$proc.ExitCode
        output_dir = $gateDir
        stdout = $gateOut
        stderr = $gateErr
        result = $resultPath
    }
}

"F75_AELITA_5G_INSTALLED_MONITOR_START at=$(Get-Date -Format o) rf=$RfSmokeStatusPath" |
    Add-Content -Encoding ascii -LiteralPath $logPath
Write-Status "watching" "waiting for 5G RF smoke PASS"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    $rfStatus = Read-JsonOrNull $RfSmokeStatusPath
    $rfState = if ($rfStatus) { [string](Get-ObjectProperty $rfStatus "state") } else { "missing" }
    $rfResult = if ($rfStatus) { [string](Get-ObjectProperty $rfStatus "result") } else { "" }
    $rfTerminal = if ($rfStatus) { [string](Get-ObjectProperty $rfStatus "five_g_terminal_state") } else { "" }

    "F75_AELITA_5G_INSTALLED_POLL at=$(Get-Date -Format o) rf_state=$rfState rf_terminal=$rfTerminal result=$rfResult" |
        Add-Content -Encoding ascii -LiteralPath $logPath

    if ($rfState -eq "pass" -or $rfTerminal -eq "PASS_5G_RF_SMOKE") {
        Write-Status "running_aelita_5g_gate" "5G RF smoke passed; running installed-only AELITA 5G gate" @{
            rf_result = $rfResult
            rf_terminal_state = $rfTerminal
        }
        $gate = Invoke-AelitaInstalled5gGate
        Write-JsonFile $resultOut @{
            schema = "openmitrastar.f75-aelita-5g-installed-result/v1"
            terminal_state = $gate.terminal_state
            rf_smoke_status_path = $RfSmokeStatusPath
            rf_result = $rfResult
            rf_terminal_state = $rfTerminal
            aelita_5g_gate = $gate
            flash = $false
            router_overlay = $false
            router_mutations = $true
        }
        Write-Status $(if ($gate.terminal_state -eq "PASS_AELITA_5G_INSTALLED_GATE") { "pass" } else { "failed" }) "AELITA 5G installed-only gate completed" @{
            result = $resultOut
            five_g_terminal_state = $gate.terminal_state
        }
        if ($gate.terminal_state -eq "PASS_AELITA_5G_INSTALLED_GATE") { exit 0 }
        exit 1
    }

    if ($rfState -in @("failed", "blocked_by_dryrun", "timeout")) {
        Write-Status "blocked_by_rf_smoke" "5G RF smoke did not pass; AELITA 5G gate not started" @{
            rf_state = $rfState
            rf_terminal_state = $rfTerminal
            rf_result = $rfResult
        }
        Write-JsonFile $resultOut @{
            schema = "openmitrastar.f75-aelita-5g-installed-result/v1"
            terminal_state = "BLOCKED_BY_5G_RF_SMOKE"
            rf_state = $rfState
            rf_terminal_state = $rfTerminal
            rf_result = $rfResult
            flash = $false
            router_overlay = $false
            router_mutations = $false
        }
        exit 1
    }

    Write-Status "watching" "waiting for 5G RF smoke PASS" @{
        rf_state = $rfState
        rf_terminal_state = $rfTerminal
        rf_result = $rfResult
    }
    Start-Sleep -Seconds $PollSeconds
}

Write-Status "timeout" "timeout waiting for 5G RF smoke PASS"
Write-JsonFile $resultOut @{
    schema = "openmitrastar.f75-aelita-5g-installed-result/v1"
    terminal_state = "TIMEOUT_WAITING_5G_RF_SMOKE"
    rf_smoke_status_path = $RfSmokeStatusPath
    flash = $false
    router_overlay = $false
    router_mutations = $false
}
exit 1
