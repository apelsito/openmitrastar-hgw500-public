param(
    [switch]$Execute,
    [string]$Ack = "OPENMITRASTAR_Q3_F73_QCSAPI_PATH_FIXED_MTD4_FLASH_DD4B4291",
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "/workspace/user-home\Desktop\MitraStar\.codex_tmp\openmitrastar_ramssh_client_ed25519",
    [string]$OracleHost = "192.168.1.63",
    [string]$OracleUser = "AELITA",
    [string]$ControllerUrl = "http://192.168.1.43:8008/speed.bin",
    [double]$Min2gMbps = 5.0,
    [switch]$Run2gProbe,
    [switch]$Run5gProbe,
    [ValidateSet("txpath", "v6scheduler")]
    [string]$FiveGProfile = "txpath",
    [ValidateRange(60, 900)]
    [int]$FiveGSeconds = 120,
    [ValidateRange(60, 21600)]
    [int]$BootWaitSeconds = 900,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [ValidateRange(0, 21600)]
    [int]$NoRxAbortSeconds = 300,
    [ValidateRange(60, 21600)]
    [int]$PostFlashTimeoutSeconds = 1800,
    [ValidateRange(2, 60)]
    [int]$PollSeconds = 5,
    [string]$CurrentLiveCrc32 = "9e4e61cb",
    [switch]$SshRebootFirst,
    [switch]$SysRqRebootFirst,
    [switch]$ConsoleRebootAssist,
    [switch]$PulseResetLinesFirst,
    [switch]$AllowBlindAutobreak,
    [switch]$KeepExistingTftp,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f73-recovery-postgate-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$statusPath = Join-Path $OutputDir "f73-recovery-postgate-status.json"
$logPath = Join-Path $OutputDir "f73-recovery-postgate.log"

function Write-Status([string]$State, [string]$Message, [int]$ExitCode = 0) {
    [ordered]@{
        schema = "openmitrastar.f73-recovery-postgate/v1"
        state = $State
        message = $Message
        exit_code = $ExitCode
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        host = $HostAddress
        port = $Port
        current_live_crc32 = $CurrentLiveCrc32
        target_full_slot_crc32 = "484fd8c6"
        min_2g_mbps = $Min2gMbps
        run_2g_probe = [bool]$Run2gProbe
        run_5g_probe = [bool]$Run5gProbe
    } | ConvertTo-Json -Depth 6 | Set-Content -Encoding ascii -LiteralPath $statusPath
}

function Add-Log([string]$Message) {
    "F73_RECOVERY_POSTGATE at=$(Get-Date -Format o) $Message" |
        Add-Content -Encoding ascii -LiteralPath $logPath
}

Write-Status "starting" "validating F73 recovery preflight"
Add-Log "start output=$OutputDir execute=$([bool]$Execute)"

if (-not $Execute) {
    & (Join-Path $PSScriptRoot "recover_flash_f73_qcsapi_path_fixed.ps1")
    $rc = $LASTEXITCODE
    Write-Status $(if ($rc -eq 0) { "dry_run_pass" } else { "dry_run_failed" }) "recovery dry-run rc=$rc" $rc
    exit $rc
}

Write-Status "flashing" "waiting for Bootbase and flashing F73 if UART appears"
$recoveryArgs = @{
    Execute = $true
    Ack = $Ack
    Port = $Port
    ServerIp = $ServerIp
    ClientIp = $ClientIp
    HostAddress = $HostAddress
    BootWaitSeconds = $BootWaitSeconds
    FlashTimeoutSeconds = $FlashTimeoutSeconds
    NoRxAbortSeconds = $NoRxAbortSeconds
    CurrentLiveCrc32 = $CurrentLiveCrc32
}
if ($SshRebootFirst) { $recoveryArgs.SshRebootFirst = $true }
if ($SysRqRebootFirst) { $recoveryArgs.SysRqRebootFirst = $true }
if ($ConsoleRebootAssist) { $recoveryArgs.ConsoleRebootAssist = $true }
if ($PulseResetLinesFirst) { $recoveryArgs.PulseResetLinesFirst = $true }
if ($AllowBlindAutobreak) { $recoveryArgs.AllowBlindAutobreak = $true }
if ($KeepExistingTftp) { $recoveryArgs.KeepExistingTftp = $true }

$recoveryLog = Join-Path $OutputDir "f73-recovery.stdout.log"
$recoveryRc = 0
try {
    & (Join-Path $PSScriptRoot "recover_flash_f73_qcsapi_path_fixed.ps1") @recoveryArgs *> $recoveryLog
    $recoveryRc = $LASTEXITCODE
} catch {
    $_ | Out-String | Add-Content -Encoding ascii -LiteralPath $recoveryLog
    $recoveryRc = 1
}
Add-Log "recovery_rc=$recoveryRc"
if ($recoveryRc -ne 0) {
    Write-Status "recovery_failed" "F73 recovery/flash did not complete; no postgate launched" $recoveryRc
    exit $recoveryRc
}

Write-Status "postflash_wait" "F73 flash completed; waiting for SSH and running radio gate"
$monitorArgs = @{
    TimeoutSeconds = $PostFlashTimeoutSeconds
    PollSeconds = $PollSeconds
    HostAddress = $HostAddress
    RouterUser = $RouterUser
    RouterKey = $RouterKey
    OracleHost = $OracleHost
    OracleUser = $OracleUser
    ControllerUrl = $ControllerUrl
    Min2gMbps = $Min2gMbps
    FiveGProfile = $FiveGProfile
    FiveGSeconds = $FiveGSeconds
    OutputDir = (Join-Path $OutputDir "postflash-monitor")
}
if ($Run2gProbe) { $monitorArgs.Run2gProbe = $true }
if ($Run5gProbe) { $monitorArgs.Run5gProbe = $true }

$monitorLog = Join-Path $OutputDir "postflash-monitor.stdout.log"
$monitorRc = 0
try {
    & (Join-Path $PSScriptRoot "monitor_router_ssh_then_radio_gate.ps1") @monitorArgs *> $monitorLog
    $monitorRc = $LASTEXITCODE
} catch {
    $_ | Out-String | Add-Content -Encoding ascii -LiteralPath $monitorLog
    $monitorRc = 1
}
Add-Log "monitor_rc=$monitorRc"
Write-Status $(if ($monitorRc -eq 0) { "pass" } else { "postgate_failed" }) "post-flash monitor/gate rc=$monitorRc" $monitorRc
exit $monitorRc
