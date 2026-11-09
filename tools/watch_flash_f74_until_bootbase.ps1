[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [int]$Attempts = 18,
    [ValidateRange(60, 21600)]
    [int]$BootWaitSeconds = 1200,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [ValidateRange(60, 21600)]
    [int]$PostFlashTimeoutSeconds = 1800,
    [ValidateRange(0, 300)]
    [int]$NoRxAbortSeconds = 30,
    [switch]$PulseResetLinesFirst,
    [switch]$SysRqRebootFirst,
    [switch]$SshRebootFirst,
    [switch]$ConsoleRebootAssist,
    [switch]$AllowBlindAutobreak,
    [switch]$KeepExistingTftp,
    [switch]$Run2gProbe,
    [switch]$Run5gProbe,
    [string]$CurrentLiveCrc32 = "484fd8c6"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runDir = Join-Path $Root "outputs\flash-watch\f74-rf-before-l3-$stamp"
$statusPath = Join-Path $runDir "status.json"
$logPath = Join-Path $runDir "watch.log"
$ack = "OPENMITRASTAR_Q3_F74_RADIO5_RF_BEFORE_L3_MTD4_FLASH_56962C97"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

function Write-Status([string]$State, [int]$Attempt, [int]$ExitCode, [string]$Message) {
    [ordered]@{
        schema = "openmitrastar.f74-flash-watch-status/v1"
        state = $State
        attempt = $Attempt
        attempts = $Attempts
        exit_code = $ExitCode
        message = $Message
        updated_at = (Get-Date).ToString("o")
        run_dir = $runDir
        log = $logPath
        watcher_pid = $PID
        port = $Port
        server_ip = $ServerIp
        client_ip = $ClientIp
        host = $HostAddress
        current_live_crc32 = $CurrentLiveCrc32
        candidate_sha256 = "56962c97dbb59b136f0a2cc71a4be7d32c40b345f15b34bac0c99c23ee5ee009"
        candidate_crc32 = "33b885e7"
        full_slot_crc32 = "67228a88"
        candidate = "f74-5g-rf-before-l3"
    } | ConvertTo-Json -Depth 5 | Set-Content -Encoding ascii -LiteralPath $statusPath
}

Write-Status "starting" 0 0 "watcher starting"
for ($i = 1; $i -le $Attempts; $i++) {
    $attemptOut = Join-Path $runDir ("attempt-{0:00}" -f $i)
    New-Item -ItemType Directory -Force -Path $attemptOut | Out-Null
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "recover_flash_f74_then_postgate.ps1"),
        "-Execute",
        "-Ack", $ack,
        "-Port", $Port,
        "-ServerIp", $ServerIp,
        "-ClientIp", $ClientIp,
        "-HostAddress", $HostAddress,
        "-BootWaitSeconds", "$BootWaitSeconds",
        "-CurrentLiveCrc32", $CurrentLiveCrc32,
        "-NoRxAbortSeconds", "$NoRxAbortSeconds",
        "-FlashTimeoutSeconds", "$FlashTimeoutSeconds",
        "-PostFlashTimeoutSeconds", "$PostFlashTimeoutSeconds",
        "-OutputDir", (Join-Path $attemptOut "postgate")
    )
    if ($PulseResetLinesFirst) { $args += "-PulseResetLinesFirst" }
    if ($SysRqRebootFirst) { $args += "-SysRqRebootFirst" }
    if ($SshRebootFirst) { $args += "-SshRebootFirst" }
    if ($ConsoleRebootAssist) { $args += "-ConsoleRebootAssist" }
    if ($AllowBlindAutobreak) { $args += "-AllowBlindAutobreak" }
    if ($KeepExistingTftp) { $args += "-KeepExistingTftp" }
    if ($Run2gProbe) { $args += "-Run2gProbe" }
    if ($Run5gProbe) { $args += "-Run5gProbe" }

    Write-Status "attempt_running" $i 0 "launching F74 flash/postgate attempt"
    "WATCH_ATTEMPT_START attempt=$i at=$(Get-Date -Format o)" | Add-Content -Encoding ascii -LiteralPath $logPath
    $stdoutPath = Join-Path $attemptOut "stdout.log"
    $stderrPath = Join-Path $attemptOut "stderr.log"
    $proc = Start-Process -FilePath "powershell.exe" `
        -WindowStyle Hidden `
        -ArgumentList $args `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -Wait `
        -PassThru
    $rc = [int]$proc.ExitCode
    if (Test-Path -LiteralPath $stdoutPath) {
        Get-Content -LiteralPath $stdoutPath | Add-Content -Encoding ascii -LiteralPath $logPath
    }
    if (Test-Path -LiteralPath $stderrPath) {
        Get-Content -LiteralPath $stderrPath | Add-Content -Encoding ascii -LiteralPath $logPath
    }
    $attemptText = @(
        if (Test-Path -LiteralPath $stdoutPath) { Get-Content -LiteralPath $stdoutPath -Raw }
        if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw }
    ) -join "`n"
    $statusFile = Join-Path $attemptOut "postgate\f74-recovery-postgate-status.json"
    $postgateState = ""
    if (Test-Path -LiteralPath $statusFile -PathType Leaf) {
        try {
            $postgateStatus = Get-Content -LiteralPath $statusFile -Raw | ConvertFrom-Json
            $postgateState = [string]$postgateStatus.state
        } catch {
            $postgateState = "status-json-unreadable"
        }
    }
    $uartSilent = $attemptText -match "UART_RX_SILENT_ZERO_BYTES"
    if ($uartSilent) {
        "WATCH_BLOCKED_UART_RX_SILENT_ZERO_BYTES attempt=$i at=$(Get-Date -Format o)" | Add-Content -Encoding ascii -LiteralPath $logPath
        Write-Status "blocked_uart_rx_silent_zero_bytes" $i 2 "UART RX silent; physical power-cycle/reset required"
        exit 2
    }
    "WATCH_ATTEMPT_END attempt=$i rc=$rc postgate_state=$postgateState at=$(Get-Date -Format o)" |
        Add-Content -Encoding ascii -LiteralPath $logPath
    if ($rc -eq 0 -and $postgateState -eq "pass") {
        Write-Status "pass" $i $rc "F74 flash and postgate completed"
        exit 0
    }
    if ($rc -eq 0 -and -not $postgateState) {
        Write-Status "pass_unclassified" $i $rc "F74 wrapper rc=0 but postgate status not found"
        exit 0
    }
    Write-Status "retry_wait" $i $rc "attempt failed or timed out; retrying"
    Start-Sleep -Seconds 5
}

Write-Status "timeout" $Attempts 1 "all attempts exhausted without completed F74 flash/postgate"
exit 1
