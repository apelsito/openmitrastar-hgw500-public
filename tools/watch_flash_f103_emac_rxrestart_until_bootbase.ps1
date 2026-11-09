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
    [ValidateRange(0, 300)]
    [int]$NoRxAbortSeconds = 45,
    [switch]$PulseResetLinesFirst,
    [switch]$SysRqRebootFirst,
    [switch]$SshRebootFirst,
    [ValidateRange(5, 120)]
    [int]$SysRqRetrySeconds = 15,
    [switch]$ConsoleRebootAssist,
    [ValidateRange(5, 120)]
    [int]$ConsoleRebootRetrySeconds = 20,
    [switch]$AllowBlindAutobreak,
    [switch]$AllowNoRxRebootAssist,
    [switch]$KeepExistingTftp,
    [string]$CurrentLiveCrc32 = "0c46aec2",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
if ($OutputDir) {
    $runDir = [IO.Path]::GetFullPath($OutputDir)
} else {
    $runDir = Join-Path $Root "outputs\flash-watch\f103-emac-rxrestart-63pokes-watch-$stamp"
}
$statusPath = Join-Path $runDir "status.json"
$logPath = Join-Path $runDir "watch.log"
$buildDir = Join-Path $Root "work\mission-state\q3-persistent-composite-f103-emac-rxrestart-63pokes-from-f101\build"
$base = "openmitrastar-linux510-q3-persistent-f103-emac-rxrestart-63pokes-from-f101-LZMA-OFFLINE-NO-FLASH"
$ack = "OPENMITRASTAR_Q3_F103_EMAC_RXRESTART_63POKES_FROM_F101_MTD4_FLASH_682484E6"
$expectedSha256 = "682484e6bbd8406b8e1b2868622e256303141e0e416a339fec4f480dfb99c453"
$expectedBytes = 5614720
$candidate = Join-Path $buildDir ($base + ".webformat.bin")
$contract = Join-Path $buildDir "bootbase-contract.json"
$manifest = Join-Path $buildDir "manifest.json"
$initramfs = Join-Path $buildDir ($base + ".decompressed.bin")
$kconfig = Join-Path $buildDir ($base + ".config")

New-Item -ItemType Directory -Force -Path $runDir | Out-Null

function Write-Status([string]$State, [int]$Attempt, [int]$ExitCode, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f103-flash-watch-status/v1"
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
        current_live_crc32 = $CurrentLiveCrc32.ToLowerInvariant()
        candidate_sha256 = $expectedSha256
        candidate = "f103-emac-rxrestart-63pokes"
        no_rx_abort_seconds = $NoRxAbortSeconds
    }
    foreach ($key in $Extra.Keys) { $payload[$key] = $Extra[$key] }
    $payload | ConvertTo-Json -Depth 6 | Set-Content -Encoding ascii -LiteralPath $statusPath
}

function Get-Sha256Hex([string]$Path) {
    $sha = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "").ToLowerInvariant()
    } finally {
        $stream.Dispose()
        $sha.Dispose()
    }
}

function Assert-Inputs() {
    foreach ($path in @($candidate, $contract, $manifest, $initramfs, $kconfig)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            Write-Status "missing_input" 0 1 "F103 input missing" @{ missing = $path }
            throw "missing F103 input: $path"
        }
    }
    $actualSha = Get-Sha256Hex $candidate
    $actualBytes = (Get-Item -LiteralPath $candidate).Length
    if ($actualSha -ne $expectedSha256 -or $actualBytes -ne $expectedBytes) {
        Write-Status "candidate_mismatch" 0 1 "F103 candidate hash/size mismatch" @{
            actual_sha256 = $actualSha
            actual_bytes = $actualBytes
        }
        throw "F103 candidate hash/size mismatch"
    }
}

function Set-F103FlashEnvironment() {
    $env:OM_Q3_FLASH_ACK = $ack
    $env:OM_Q3_FLASH_BUILD_DIR = $buildDir
    $env:OM_Q3_FLASH_CANDIDATE = $candidate
    $env:OM_Q3_FLASH_BOOTBASE_CONTRACT = $contract
    $env:OM_Q3_FLASH_MANIFEST = $manifest
    $env:OM_Q3_FLASH_INITRAMFS = $initramfs
    $env:OM_Q3_FLASH_KCONFIG = $kconfig
    $env:OM_Q3_FLASH_EXPECTED_SHA256 = $expectedSha256
    $env:OM_Q3_FLASH_EXPECTED_BYTES = [string]$expectedBytes
    $env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $CurrentLiveCrc32.ToLowerInvariant()
}

Assert-Inputs
Set-F103FlashEnvironment
Write-Status "starting" 0 0 "F103 watcher starting"

for ($i = 1; $i -le $Attempts; $i++) {
    $attemptOut = Join-Path $runDir ("attempt-{0:00}" -f $i)
    New-Item -ItemType Directory -Force -Path $attemptOut | Out-Null
    $stdoutPath = Join-Path $attemptOut "stdout.log"
    $stderrPath = Join-Path $attemptOut "stderr.log"
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1"),
        "-Execute",
        "-Ack", $ack,
        "-Port", $Port,
        "-ServerIp", $ServerIp,
        "-ClientIp", $ClientIp,
        "-HostAddress", $HostAddress,
        "-CurrentLiveCrc32", $CurrentLiveCrc32.ToLowerInvariant(),
        "-BootWaitSeconds", "$BootWaitSeconds",
        "-FlashTimeoutSeconds", "$FlashTimeoutSeconds",
        "-NoRxAbortSeconds", "$NoRxAbortSeconds"
    )
    if ($PulseResetLinesFirst) { $args += "-PulseResetLinesFirst" }
    if ($SysRqRebootFirst) { $args += "-SysRqRebootFirst" }
    if ($SshRebootFirst) { $args += "-SshRebootFirst" }
    if ($SysRqRebootFirst) {
        $args += "-SysRqRetrySeconds"
        $args += "$SysRqRetrySeconds"
    }
    if ($ConsoleRebootAssist) { $args += "-ConsoleRebootAssist" }
    if ($ConsoleRebootAssist) {
        $args += "-ConsoleRebootRetrySeconds"
        $args += "$ConsoleRebootRetrySeconds"
    }
    if ($AllowBlindAutobreak) { $args += "-AllowBlindAutobreak" }
    if ($AllowNoRxRebootAssist) { $args += "-AllowNoRxRebootAssist" }
    if ($KeepExistingTftp) { $args += "-KeepExistingTftp" }

    Write-Status "attempt_running" $i 0 "launching F103 Bootbase flash attempt" @{
        stdout = $stdoutPath
        stderr = $stderrPath
    }
    "WATCH_ATTEMPT_START attempt=$i at=$(Get-Date -Format o)" | Add-Content -Encoding ascii -LiteralPath $logPath
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
        Write-Status "blocked_uart_rx_silent_zero_bytes" $i 2 "UART RX silent; power-cycle target or check router TX to adapter RX" @{
            stdout = $stdoutPath
            stderr = $stderrPath
        }
        exit 2
    }
    if (-not $flashPass) {
        $rc = if ($rc -eq 0) { 1 } else { $rc }
    }
    "WATCH_ATTEMPT_END attempt=$i rc=$rc flash_pass=$flashPass at=$(Get-Date -Format o)" |
        Add-Content -Encoding ascii -LiteralPath $logPath
    if ($rc -eq 0 -and $flashPass) {
        Write-Status "pass" $i $rc "F103 flash/readback completed" @{
            stdout = $stdoutPath
            stderr = $stderrPath
        }
        exit 0
    }
    Write-Status "retry_wait" $i $rc "attempt failed or timed out; retrying" @{
        stdout = $stdoutPath
        stderr = $stderrPath
    }
    Start-Sleep -Seconds 5
}

Write-Status "timeout" $Attempts 1 "all attempts exhausted without completed F103 flash"
exit 1
