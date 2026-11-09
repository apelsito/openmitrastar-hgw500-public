param(
    [switch]$Execute,
    [string]$Ack = "OPENMITRASTAR_Q3_F70_RESTORE_MTD4_FLASH_36BE6A2C",
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
    [int]$BootWaitSeconds = 21600,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [ValidateRange(0, 21600)]
    [int]$NoRxAbortSeconds = 0,
    [ValidateRange(60, 21600)]
    [int]$PostFlashTimeoutSeconds = 1800,
    [ValidateRange(2, 60)]
    [int]$PollSeconds = 5,
    [string]$CurrentLiveCrc32 = "1a3f9be6",
    [switch]$AllowBlindAutobreak,
    [switch]$KeepExistingTftp,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f70-restore-postgate-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$statusPath = Join-Path $OutputDir "f70-restore-postgate-status.json"
$logPath = Join-Path $OutputDir "f70-restore-postgate.log"

$Build = Join-Path $Root "work\mission-state\q3-persistent-composite-f70-2g-mcs15-qguard64r-nosplit\build"
$Base = "openmitrastar-linux510-q3-persistent-f70-2g-mcs15-qguard64r-nosplit-LZMA-OFFLINE-NO-FLASH"
$Candidate = Join-Path $Build "$Base.webformat.bin"
$ResultPath = Join-Path $Build "build-result.json"
$RequiredAck = "OPENMITRASTAR_Q3_F70_RESTORE_MTD4_FLASH_36BE6A2C"

function Write-Status([string]$State, [string]$Message, [int]$ExitCode = 0) {
    [ordered]@{
        schema = "openmitrastar.f70-restore-postgate/v1"
        state = $State
        message = $Message
        exit_code = $ExitCode
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        host = $HostAddress
        port = $Port
        current_live_crc32 = $CurrentLiveCrc32
        target_full_slot_crc32 = "9e4e61cb"
        min_2g_mbps = $Min2gMbps
        run_2g_probe = [bool]$Run2gProbe
        run_5g_probe = [bool]$Run5gProbe
    } | ConvertTo-Json -Depth 6 | Set-Content -Encoding ascii -LiteralPath $statusPath
}

function Add-Log([string]$Message) {
    "F70_RESTORE_POSTGATE at=$(Get-Date -Format o) $Message" |
        Add-Content -Encoding ascii -LiteralPath $logPath
}

function Get-Sha256Hex([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    try {
        $sha = [Security.Cryptography.SHA256]::Create()
        try {
            return -join ($sha.ComputeHash($stream) | ForEach-Object { $_.ToString("x2") })
        } finally {
            $sha.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

function Require-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing required file: $Path" }
}

Write-Status "starting" "validating F70 restore preflight"
Add-Log "start output=$OutputDir execute=$([bool]$Execute)"

Require-File $ResultPath
Require-File $Candidate
$result = Get-Content -LiteralPath $ResultPath -Raw | ConvertFrom-Json
if ($result.status -ne "PASS") { throw "F70 build-result is not PASS" }
if ($result.candidate_sha256 -ne "36be6a2c1da2d260a2812f0e52f846b2d03da064d7fc17166500e231c7e9f483") { throw "F70 candidate SHA drift" }
if ([long]$result.candidate_bytes -ne 5613010) { throw "F70 candidate size drift" }
if ($result.candidate_crc32 -ne "ed42ae93") { throw "F70 candidate CRC drift" }
if ($result.full_slot_crc32 -ne "9e4e61cb") { throw "F70 full-slot CRC drift" }
if ($result.full_slot_sha256 -ne "3a90cb33b1d71a83119f29ff9afbc4eab2f30711fde9fb562bf8993996f991bf") { throw "F70 full-slot SHA drift" }
if ((Get-Sha256Hex $Candidate) -ne $result.candidate_sha256) { throw "F70 candidate file hash mismatch" }

$env:OM_Q3_FLASH_BUILD_DIR = $Build
$env:OM_Q3_FLASH_CANDIDATE = $Candidate
$env:OM_Q3_FLASH_BOOTBASE_CONTRACT = Join-Path $Build "bootbase-contract.json"
$env:OM_Q3_FLASH_MANIFEST = Join-Path $Build "manifest.json"
$env:OM_Q3_FLASH_INITRAMFS = Join-Path $Build "$Base.decompressed.bin"
$env:OM_Q3_FLASH_KCONFIG = Join-Path $Build "$Base.config"
$env:OM_Q3_FLASH_EXPECTED_SHA256 = $result.candidate_sha256
$env:OM_Q3_FLASH_EXPECTED_BYTES = [string]$result.candidate_bytes
$env:OM_Q3_FLASH_ACK = $RequiredAck
$env:OM_Q3_FLASH_SSH_KEY = Join-Path $Root ".codex_tmp\openmitrastar_ramssh_client_ed25519"
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $CurrentLiveCrc32.ToLowerInvariant()
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = "7b333b5e26b87ad55f048dd9021b34ff9f66983cff44a3bc30391260e0db03a7"

if (-not $Execute) {
    Write-Host "OMF70_RESTORE_READY=1"
    Write-Host "candidate=$Candidate"
    Write-Host "candidate_sha256=$($result.candidate_sha256)"
    Write-Host "current_live_crc32_expected=$CurrentLiveCrc32"
    Write-Host "flash=0 reason=missing_-Execute"
    Write-Status "dry_run_pass" "F70 restore dry-run ready"
    exit 0
}
if ($Ack -ne $RequiredAck) { throw "Exact acknowledgement required: $RequiredAck" }

Write-Status "flashing" "waiting for Bootbase and restoring F70 if UART appears"
$flashLog = Join-Path $OutputDir "f70-restore.stdout.log"
$flashRc = 0
$flashScript = Join-Path $Root "tools\q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1"
try {
    $common = @{
        Execute = $true
        Ack = $RequiredAck
        Port = $Port
        ServerIp = $ServerIp
        ClientIp = $ClientIp
        HostAddress = $HostAddress
        CurrentLiveCrc32 = $CurrentLiveCrc32
        BootWaitSeconds = $BootWaitSeconds
        FlashTimeoutSeconds = $FlashTimeoutSeconds
        NoRxAbortSeconds = $NoRxAbortSeconds
        AllowNoRxRebootAssist = $true
    }
    if ($AllowBlindAutobreak) { $common.AllowBlindAutobreak = $true }
    if ($KeepExistingTftp) { $common.KeepExistingTftp = $true }
    & $flashScript @common *> $flashLog
    $flashRc = $LASTEXITCODE
} catch {
    $_ | Out-String | Add-Content -Encoding ascii -LiteralPath $flashLog
    $flashRc = 1
}
Add-Log "flash_rc=$flashRc"
if ($flashRc -ne 0) {
    Write-Status "restore_failed" "F70 restore/flash did not complete; no postgate launched" $flashRc
    exit $flashRc
}

Write-Status "postflash_wait" "F70 restored; waiting for SSH and running radio gate"
$monitorLog = Join-Path $OutputDir "postflash-monitor.stdout.log"
$monitorRc = 0
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
