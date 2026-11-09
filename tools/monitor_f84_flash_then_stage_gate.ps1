[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$FlashStatusPath = "/workspace/user-home\Desktop\MitraStar\outputs\flash-watch\f84-2g-mcs7-param-fix-5g-post-hostapd-stage-20260826-184854\status.json",
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
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f84-flash-pass-then-stage-gate-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$statusOut = Join-Path $OutputDir "status.json"
$resultOut = Join-Path $OutputDir "result.json"
$logPath = Join-Path $OutputDir "monitor.log"

function Write-JsonFile([string]$Path, [hashtable]$Payload) {
    $Payload.updated_at = (Get-Date).ToString("o")
    $Payload.output_dir = $OutputDir
    $Payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $Path
}

function Write-Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = @{
        schema = "openmitrastar.f84-flash-then-stage-gate-monitor/v1"
        state = $State
        message = $Message
        flash_status_path = $FlashStatusPath
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
    try { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json } catch { return $null }
}

function Get-ObjectProperty($Object, [string]$Name) {
    if ($null -eq $Object) { return $null }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $null }
    return $prop.Value
}

function Test-ProcessAliveById($ProcessId) {
    if ($null -eq $ProcessId) { return $false }
    try {
        $pidValue = [int]$ProcessId
        return $null -ne (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)
    } catch {
        return $false
    }
}

function Test-F84FlashUartRxZero($FlashStatus) {
    $flashOutputDir = Get-ObjectProperty $FlashStatus "output_dir"
    $paths = @()
    if ($flashOutputDir) {
        $paths += Join-Path ([string]$flashOutputDir) "stdout.log"
    }
    $externalStdout = Get-ObjectProperty $FlashStatus "external_stdout_log"
    if ($externalStdout) {
        $paths += [string]$externalStdout
    }
    foreach ($stdoutPath in $paths) {
        if (-not (Test-Path -LiteralPath $stdoutPath -PathType Leaf)) { continue }
        $stdoutText = Get-Content -LiteralPath $stdoutPath -Raw
        if ($stdoutText -match "UART_RX_SILENT_ZERO_BYTES") { return $true }
    }
    return $false
}

"F84_FLASH_THEN_STAGE_GATE_MONITOR_START at=$(Get-Date -Format o) flash=$FlashStatusPath" |
    Add-Content -Encoding ascii -LiteralPath $logPath
Write-Status "watching" "waiting for F84 flash pass"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    $flash = Read-JsonOrNull $FlashStatusPath
    $flashState = if ($flash) { [string](Get-ObjectProperty $flash "state") } else { "missing" }
    "F84_FLASH_THEN_STAGE_GATE_POLL at=$(Get-Date -Format o) flash_state=$flashState" |
        Add-Content -Encoding ascii -LiteralPath $logPath

    if ($flashState -eq "pass") {
        $gateDir = Join-Path $OutputDir "stage-gate"
        Write-Status "running_stage_gate" "F84 flash passed; running 2G and module-stage gate" @{
            flash_state = $flashState
            stage_gate_dir = $gateDir
        }
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "post_flash_f84_stage_gate.ps1") `
            -HostAddress $HostAddress `
            -RouterUser $RouterUser `
            -RouterKey $RouterKey `
            -OracleHost $OracleHost `
            -OracleUser $OracleUser `
            -ControllerUrl $ControllerUrl `
            -Min2gMbps $Min2gMbps `
            -Diag2gMbps $Diag2gMbps `
            -OutputDir $gateDir *> (Join-Path $OutputDir "stage-gate.stdout.log")
        $gateRc = $LASTEXITCODE
        $gateResult = Join-Path $gateDir "result.json"
        $gate = Read-JsonOrNull $gateResult
        $gateTerminal = if ($gate) { [string](Get-ObjectProperty $gate "terminal_state") } else { "missing" }
        $terminal = if ($gateRc -eq 0 -and $gateTerminal -eq "PASS_F84_2G_AND_5G_POST_HOSTAPD_STAGE") {
            "PASS_F84_FLASH_2G_AND_5G_POST_HOSTAPD_STAGE"
        } else {
            "FAIL_F84_STAGE_GATE"
        }
        Write-JsonFile $resultOut @{
            schema = "openmitrastar.f84-flash-then-stage-gate-result/v1"
            terminal_state = $terminal
            flash_status_path = $FlashStatusPath
            flash_state = $flashState
            stage_gate_result = $gateResult
            stage_gate_terminal_state = $gateTerminal
            stage_gate_exit_code = $gateRc
            flash = $false
            router_mutations = $true
        }
        Write-Status $(if ($terminal -like "PASS*") { "pass" } else { "failed" }) "stage gate completed" @{
            result = $resultOut
            terminal_state = $terminal
        }
        if ($terminal -like "PASS*") { exit 0 }
        exit 1
    }

    if ($flashState -in @("failed", "uart_rx_zero", "ack_required", "busy_com3", "preflight_failed", "missing_build", "build_not_pass")) {
        $terminalState = "BLOCKED_BY_FLASH_$($flashState.ToUpperInvariant())"
        $failureReason = $flashState
        if ($flashState -eq "uart_rx_zero" -or ($flashState -eq "failed" -and (Test-F84FlashUartRxZero $flash))) {
            $terminalState = "BLOCKED_BY_FLASH_UART_RX_ZERO"
            $failureReason = "UART_RX_SILENT_ZERO_BYTES"
        }
        Write-JsonFile $resultOut @{
            schema = "openmitrastar.f84-flash-then-stage-gate-result/v1"
            terminal_state = $terminalState
            flash_status_path = $FlashStatusPath
            flash_state = $flashState
            failure_reason = $failureReason
            flash = $false
            router_mutations = $false
        }
        Write-Status "blocked_by_flash" "F84 flash did not pass; stage gate not started" @{
            result = $resultOut
            flash_state = $flashState
            failure_reason = $failureReason
        }
        exit 1
    }

    if ($flashState -in @("running", "running_background", "running_foreground", "background_armed")) {
        $flashPid = Get-ObjectProperty $flash "process_id"
        if (-not $flashPid) {
            $flashPid = Get-ObjectProperty $flash "current_process_id"
        }
        if ($flashPid -and -not (Test-ProcessAliveById $flashPid)) {
            Write-JsonFile $resultOut @{
                schema = "openmitrastar.f84-flash-then-stage-gate-result/v1"
                terminal_state = "BLOCKED_BY_FLASH_STALE_RUNNING_PROCESS_DEAD"
                flash_status_path = $FlashStatusPath
                flash_state = $flashState
                flash_process_id = $flashPid
                flash = $false
                router_mutations = $false
            }
            Write-Status "blocked_by_flash_stale_running" "F84 flash status is still running but its process is dead" @{
                result = $resultOut
                flash_state = $flashState
                flash_process_id = $flashPid
            }
            exit 1
        }
    }

    Write-Status "watching" "waiting for F84 flash pass" @{
        flash_state = $flashState
    }
    Start-Sleep -Seconds $PollSeconds
}

Write-JsonFile $resultOut @{
    schema = "openmitrastar.f84-flash-then-stage-gate-result/v1"
    terminal_state = "TIMEOUT_WAITING_F84_FLASH"
    flash_status_path = $FlashStatusPath
    flash = $false
    router_mutations = $false
}
Write-Status "timeout" "timeout waiting for F84 flash pass" @{
    result = $resultOut
}
exit 1




