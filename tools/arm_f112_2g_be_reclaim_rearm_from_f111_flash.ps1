[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "572d536c",
    [ValidateRange(600, 21600)]
    [int]$BootWaitSeconds = 21600,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [ValidateRange(0, 300)]
    [int]$NoRxAbortSeconds = 45,
    [switch]$PulseResetLinesFirst,
    [switch]$SysRqRebootFirst,
    [switch]$SshRebootFirst,
    [switch]$ConsoleRebootAssist,
    [switch]$AllowBlindAutobreak,
    [switch]$AllowNoRxRebootAssist,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$BuildDir = Join-Path $Root "work\mission-state\q3-persistent-composite-f112-2g-be-reclaim-rearm-from-f111\build"
$Base = "openmitrastar-linux510-q3-persistent-f112-2g-be-reclaim-rearm-from-f111-LZMA-OFFLINE-NO-FLASH"
$Ack = "OPENMITRASTAR_Q3_F112_2G_BE_RECLAIM_REARM_FROM_F111_MTD4_FLASH_6F5084AA"
$ExpectedSha256 = "6f5084aa6db0938adfd15c0cb1faadef2eacae033f7ced838331a8125b8edb61"
$ExpectedBytes = "4370785"
$ExpectedCandidateCrc32 = "8ff3fab8"
$ExpectedFullSlotCrc32 = "d8002f97"

if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\flash-watch\f112-2g-be-reclaim-rearm-from-f111-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StatusPath = Join-Path $OutputDir "status.json"

function Write-F112Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f112-auto-arm/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        execute = [bool]$Execute
        port = $Port
        server_ip = $ServerIp
        client_ip = $ClientIp
        host = $HostAddress
        current_live_crc32 = $CurrentLiveCrc32.ToLowerInvariant()
        ack = $Ack
        candidate = "f112-2g-be-reclaim-rearm-from-f111"
        candidate_sha256 = $ExpectedSha256
        candidate_crc32 = $ExpectedCandidateCrc32
        expected_full_slot_crc32 = $ExpectedFullSlotCrc32
        no_rx_abort_seconds = $NoRxAbortSeconds
    }
    foreach ($key in $Extra.Keys) { $payload[$key] = $Extra[$key] }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $StatusPath
}

$candidate = Join-Path $BuildDir ($Base + ".webformat.bin")
$contract = Join-Path $BuildDir "bootbase-contract.json"
$manifest = Join-Path $BuildDir "manifest.json"
$initramfs = Join-Path $BuildDir ($Base + ".decompressed.bin")
$kconfig = Join-Path $BuildDir ($Base + ".config")
foreach ($path in @($candidate, $contract, $manifest, $initramfs, $kconfig)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Write-F112Status "missing_input" "F112 input missing" @{ missing = $path }
        throw "missing F112 input: $path"
    }
}

$actualSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant()
$actualBytes = (Get-Item -LiteralPath $candidate).Length
if ($actualSha -ne $ExpectedSha256 -or [string]$actualBytes -ne $ExpectedBytes) {
    Write-F112Status "candidate_mismatch" "F112 candidate hash/size mismatch" @{
        actual_sha256 = $actualSha
        actual_bytes = $actualBytes
    }
    throw "F112 candidate hash/size mismatch"
}

$contractJson = Get-Content -Raw -LiteralPath $contract | ConvertFrom-Json
if ($contractJson.result -ne "PASS") {
    Write-F112Status "bootbase_contract_failed" "F112 Bootbase contract is not PASS" @{ bootbase_result = $contractJson.result }
    throw "F112 Bootbase contract is not PASS"
}

$envBlock = @"
`$env:OM_Q3_FLASH_ACK='$Ack'
`$env:OM_Q3_FLASH_BUILD_DIR='$BuildDir'
`$env:OM_Q3_FLASH_CANDIDATE='$candidate'
`$env:OM_Q3_FLASH_BOOTBASE_CONTRACT='$contract'
`$env:OM_Q3_FLASH_MANIFEST='$manifest'
`$env:OM_Q3_FLASH_INITRAMFS='$initramfs'
`$env:OM_Q3_FLASH_KCONFIG='$kconfig'
`$env:OM_Q3_FLASH_EXPECTED_SHA256='$ExpectedSha256'
`$env:OM_Q3_FLASH_EXPECTED_BYTES='$ExpectedBytes'
`$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32='$($CurrentLiveCrc32.ToLowerInvariant())'
"@

$dryCommand = @"
$envBlock
python '$Root\tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py' --port '$Port' --server-ip '$ServerIp' --client-ip '$ClientIp' --host '$HostAddress' --timeout $FlashTimeoutSeconds
"@
$dryLog = Join-Path $OutputDir "dry-run.log"
$dry = powershell.exe -NoProfile -ExecutionPolicy Bypass -Command $dryCommand 2>&1
$dry | Set-Content -Encoding utf8 -LiteralPath $dryLog
if ($LASTEXITCODE -ne 0 -or (($dry -join "`n") -notmatch "MTD4_FLASH_ONE_SHOT_DRY_RUN_PASS=1")) {
    Write-F112Status "dry_run_failed" "F112 dry-run failed" @{ dry_run_log = $dryLog }
    throw "F112 dry-run failed; see $dryLog"
}

if (-not $Execute) {
    Write-F112Status "dry_run_pass" "F112 dry-run passed; no router writes" @{ dry_run_log = $dryLog }
    Write-Host "OMF112_AUTO_ARM_DRY_RUN_PASS=1 status=$StatusPath"
    exit 0
}

$stdout = Join-Path $OutputDir "flash-watch.stdout.log"
$stderr = Join-Path $OutputDir "flash-watch.stderr.log"
$args = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $Root "tools\q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1"),
    "-Execute",
    "-Ack", $Ack,
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
if ($SysRqRebootFirst) {
    $args += "-SysRqRebootFirst"
    $args += "-SysRqRetrySeconds"
    $args += "5"
}
if ($SshRebootFirst) { $args += "-SshRebootFirst" }
if ($ConsoleRebootAssist) {
    $args += "-ConsoleRebootAssist"
    $args += "-ConsoleRebootRetrySeconds"
    $args += "5"
}
if ($AllowBlindAutobreak) { $args += "-AllowBlindAutobreak" }
if ($AllowNoRxRebootAssist) { $args += "-AllowNoRxRebootAssist" }

$commandPath = Join-Path $OutputDir "flash-command.args.json"
@{
    executable = "powershell.exe"
    args = $args
    env = @{
        OM_Q3_FLASH_ACK = $Ack
        OM_Q3_FLASH_BUILD_DIR = $BuildDir
        OM_Q3_FLASH_CANDIDATE = $candidate
        OM_Q3_FLASH_BOOTBASE_CONTRACT = $contract
        OM_Q3_FLASH_MANIFEST = $manifest
        OM_Q3_FLASH_INITRAMFS = $initramfs
        OM_Q3_FLASH_KCONFIG = $kconfig
        OM_Q3_FLASH_EXPECTED_SHA256 = $ExpectedSha256
        OM_Q3_FLASH_EXPECTED_BYTES = $ExpectedBytes
        OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $CurrentLiveCrc32.ToLowerInvariant()
    }
} | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $commandPath

$env:OM_Q3_FLASH_ACK = $Ack
$env:OM_Q3_FLASH_BUILD_DIR = $BuildDir
$env:OM_Q3_FLASH_CANDIDATE = $candidate
$env:OM_Q3_FLASH_BOOTBASE_CONTRACT = $contract
$env:OM_Q3_FLASH_MANIFEST = $manifest
$env:OM_Q3_FLASH_INITRAMFS = $initramfs
$env:OM_Q3_FLASH_KCONFIG = $kconfig
$env:OM_Q3_FLASH_EXPECTED_SHA256 = $ExpectedSha256
$env:OM_Q3_FLASH_EXPECTED_BYTES = $ExpectedBytes
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $CurrentLiveCrc32.ToLowerInvariant()

$proc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden `
    -ArgumentList $args `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

Write-F112Status "armed_waiting_bootbase" "F112 flash helper armed" @{
    dry_run_log = $dryLog
    command = $commandPath
    stdout = $stdout
    stderr = $stderr
    pid = $proc.Id
}
Write-Host "OMF112_AUTO_ARMED=1 pid=$($proc.Id) status=$StatusPath stdout=$stdout"
