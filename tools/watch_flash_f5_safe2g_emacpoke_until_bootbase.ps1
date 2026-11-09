[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "05674ac6",
    [int]$Attempts = 12,
    [int]$BootWaitSeconds = 1200,
    [int]$FlashTimeoutSeconds = 900,
    [switch]$PulseResetLinesFirst,
    [switch]$SysRqRebootFirst
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runDir = Join-Path $Root "outputs\flash-watch\f5-safe2g-emacpoke-$stamp"
$statusPath = Join-Path $runDir "status.json"
$logPath = Join-Path $runDir "watch.log"
$ack = "OPENMITRASTAR_F5_SAFE2G_EMACPOKE_MTD4_FLASH_BA1AC359"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

function Write-Status([string]$State, [int]$Attempt, [int]$ExitCode, [string]$Message) {
    [ordered]@{
        state = $State
        attempt = $Attempt
        exit_code = $ExitCode
        message = $Message
        updated_at = (Get-Date).ToString("o")
        run_dir = $runDir
        port = $Port
        host = $HostAddress
        current_live_crc32 = $CurrentLiveCrc32
    } | ConvertTo-Json -Depth 4 | Set-Content -Encoding ascii -LiteralPath $statusPath
}

Write-Status "starting" 0 0 "watcher starting"
for ($i = 1; $i -le $Attempts; $i++) {
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "flash_openmitrastar_f5_safe2g_emacpoke_auto.ps1"),
        "-Execute",
        "-Ack", $ack,
        "-Port", $Port,
        "-ServerIp", $ServerIp,
        "-ClientIp", $ClientIp,
        "-HostAddress", $HostAddress,
        "-BootWaitSeconds", "$BootWaitSeconds",
        "-FlashTimeoutSeconds", "$FlashTimeoutSeconds",
        "-CurrentLiveCrc32", $CurrentLiveCrc32
    )
    if ($PulseResetLinesFirst) { $args += "-PulseResetLinesFirst" }
    if ($SysRqRebootFirst) { $args += "-SysRqRebootFirst" }

    Write-Status "attempt_running" $i 0 "launching flash attempt"
    "WATCH_ATTEMPT_START attempt=$i at=$(Get-Date -Format o)" | Add-Content -Encoding ascii -LiteralPath $logPath
    & pwsh.exe @args *>> $logPath
    $rc = $LASTEXITCODE
    "WATCH_ATTEMPT_END attempt=$i rc=$rc at=$(Get-Date -Format o)" | Add-Content -Encoding ascii -LiteralPath $logPath
    if ($rc -eq 0) {
        Write-Status "pass" $i $rc "flash completed"
        exit 0
    }
    Write-Status "retry_wait" $i $rc "attempt failed or timed out; retrying"
    Start-Sleep -Seconds 5
}

Write-Status "timeout" $Attempts 1 "all attempts exhausted without completed flash"
exit 1
