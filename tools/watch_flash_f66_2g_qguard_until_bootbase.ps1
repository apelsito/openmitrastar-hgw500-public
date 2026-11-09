[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [int]$Attempts = 18,
    [ValidateRange(60, 1200)]
    [int]$BootWaitSeconds = 1200,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [ValidateRange(5, 300)]
    [int]$NoRxAbortSeconds = 30,
    [switch]$PulseResetLinesFirst,
    [switch]$SysRqRebootFirst,
    [switch]$SshRebootFirst,
    [switch]$ConsoleRebootAssist,
    [switch]$AllowBlindAutobreak,
    [switch]$AllowNoRxRebootAssist,
    [switch]$KeepExistingTftp,
    [string]$CurrentLiveCrc32 = "26523198"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runDir = Join-Path $Root "outputs\flash-watch\f66-2g-autorate-reclaim-$stamp"
$statusPath = Join-Path $runDir "status.json"
$logPath = Join-Path $runDir "watch.log"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

function Write-Status([string]$State, [int]$Attempt, [int]$ExitCode, [string]$Message) {
    [ordered]@{
        schema = "openmitrastar.f66-flash-watch-status/v1"
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
        candidate_sha256 = "021cd4896ee54db95addd3b3c4111eb811b2dcf77a69c87b28b94dd4bec4b341"
        candidate = "f66-2g-autorate-reclaim"
    } | ConvertTo-Json -Depth 5 | Set-Content -Encoding ascii -LiteralPath $statusPath
}

Write-Status "starting" 0 0 "watcher starting"
for ($i = 1; $i -le $Attempts; $i++) {
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "flash_f66_2g_qguard.ps1"),
        "-Port", $Port,
        "-ServerIp", $ServerIp,
        "-ClientIp", $ClientIp,
        "-HostAddress", $HostAddress,
        "-BootWaitSeconds", "$BootWaitSeconds",
        "-CurrentLiveCrc32", $CurrentLiveCrc32,
        "-NoRxAbortSeconds", "$NoRxAbortSeconds",
        "-FlashTimeoutSeconds", "$FlashTimeoutSeconds"
    )
    if ($PulseResetLinesFirst) { $args += "-PulseResetLinesFirst" }
    if ($SysRqRebootFirst) { $args += "-SysRqRebootFirst" }
    if ($SshRebootFirst) { $args += "-SshRebootFirst" }
    if ($ConsoleRebootAssist) { $args += "-ConsoleRebootAssist" }
    if ($AllowBlindAutobreak) { $args += "-AllowBlindAutobreak" }
    if ($AllowNoRxRebootAssist) { $args += "-AllowNoRxRebootAssist" }
    if ($KeepExistingTftp) { $args += "-KeepExistingTftp" }

    Write-Status "attempt_running" $i 0 "launching F66 flash attempt"
    "WATCH_ATTEMPT_START attempt=$i at=$(Get-Date -Format o)" | Add-Content -Encoding ascii -LiteralPath $logPath
    $stdoutPath = Join-Path $runDir ("attempt-{0:00}.stdout.log" -f $i)
    $stderrPath = Join-Path $runDir ("attempt-{0:00}.stderr.log" -f $i)
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
    $flashPass = $attemptText -match "MTD4_FLASH_AND_READBACK_PASS"
    $uartSilent = $attemptText -match "UART_RX_SILENT_ZERO_BYTES"
    if ($uartSilent) {
        "WATCH_BLOCKED_UART_RX_SILENT_ZERO_BYTES attempt=$i at=$(Get-Date -Format o)" | Add-Content -Encoding ascii -LiteralPath $logPath
        Write-Status "blocked_uart_rx_silent_zero_bytes" $i 2 "UART RX silent; not consuming remaining attempts"
        exit 2
    }
    if (-not $flashPass) {
        $rc = if ($rc -eq 0) { 1 } else { $rc }
    }
    "WATCH_ATTEMPT_END attempt=$i rc=$rc at=$(Get-Date -Format o)" | Add-Content -Encoding ascii -LiteralPath $logPath
    if ($rc -eq 0 -and $flashPass) {
        Write-Status "pass" $i $rc "flash completed"
        exit 0
    }
    Write-Status "retry_wait" $i $rc "attempt failed or timed out; retrying"
    Start-Sleep -Seconds 5
}

Write-Status "timeout" $Attempts 1 "all attempts exhausted without completed flash"
exit 1
