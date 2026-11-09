[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "35b28167",
    [ValidateRange(600, 21600)]
    [int]$BootWaitSeconds = 21600,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [switch]$PulseResetLinesFirst,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$BuildDir = Join-Path $Root "work\mission-state\q3-persistent-composite-f102-emac-irq-poll-disabled-from-f101\build"
$Base = "openmitrastar-linux510-q3-persistent-f102-emac-irq-poll-disabled-from-f101-LZMA-OFFLINE-NO-FLASH"
$Ack = "OPENMITRASTAR_Q3_F102_EMAC_IRQ_POLL_DISABLED_FROM_F101_MTD4_FLASH_667EC40C"
$ExpectedSha256 = "667ec40cfe9c9445397357c1d541758ecd176dcc66211e0005484320b33a044b"
$ExpectedBytes = "5615012"

if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\flash-watch\f102-emac-irq-poll-disabled-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StatusPath = Join-Path $OutputDir "status.json"

function Write-F102Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f102-auto-arm/v1"
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
        candidate_sha256 = $ExpectedSha256
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
        Write-F102Status "missing_input" "F102 input missing" @{ missing = $path }
        throw "missing F102 input: $path"
    }
}

$actualSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant()
$actualBytes = (Get-Item -LiteralPath $candidate).Length
if ($actualSha -ne $ExpectedSha256 -or [string]$actualBytes -ne $ExpectedBytes) {
    Write-F102Status "candidate_mismatch" "F102 candidate hash/size mismatch" @{
        actual_sha256 = $actualSha
        actual_bytes = $actualBytes
    }
    throw "F102 candidate hash/size mismatch"
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
    Write-F102Status "dry_run_failed" "F102 dry-run failed" @{ dry_run_log = $dryLog }
    throw "F102 dry-run failed; see $dryLog"
}

if (-not $Execute) {
    Write-F102Status "dry_run_pass" "F102 dry-run passed; no router writes" @{ dry_run_log = $dryLog }
    Write-Host "OMF102_AUTO_ARM_DRY_RUN_PASS=1 status=$StatusPath"
    exit 0
}

$stdout = Join-Path $OutputDir "flash-watch.stdout.log"
$stderr = Join-Path $OutputDir "flash-watch.stderr.log"
$pulseResetArg = if ($PulseResetLinesFirst) { " -PulseResetLinesFirst" } else { "" }
$flashCommand = @"
$envBlock
& '$Root\tools\q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1' -Execute -Ack '$Ack' -Port '$Port' -ServerIp '$ServerIp' -ClientIp '$ClientIp' -HostAddress '$HostAddress' -CurrentLiveCrc32 '$($CurrentLiveCrc32.ToLowerInvariant())' -BootWaitSeconds $BootWaitSeconds -FlashTimeoutSeconds $FlashTimeoutSeconds -NoRxAbortSeconds 0 -AllowBlindAutobreak -AllowNoRxRebootAssist -SysRqRebootFirst -SysRqRetrySeconds 5 -ConsoleRebootAssist -ConsoleRebootRetrySeconds 5$pulseResetArg
"@
$commandPath = Join-Path $OutputDir "flash-command.ps1"
$flashCommand | Set-Content -Encoding ascii -LiteralPath $commandPath
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($flashCommand))
$proc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden `
    -ArgumentList "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded" `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

$monitorDir = Join-Path $Root ("outputs\postflash\f102-flash-then-2g-emac-gate-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Force -Path $monitorDir | Out-Null
$monitorCommand = @"
& '$Root\tools\monitor_f102_flash_then_2g_emac_gate.ps1' -ArmStatusPath '$StatusPath' -TimeoutSeconds $BootWaitSeconds -PollSeconds 10 -HostAddress '$HostAddress' -OutputDir '$monitorDir'
"@
$monitorCommandPath = Join-Path $OutputDir "monitor-command.ps1"
$monitorCommand | Set-Content -Encoding ascii -LiteralPath $monitorCommandPath
$monitorEncoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($monitorCommand))
$monitorProc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden `
    -ArgumentList "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $monitorEncoded" `
    -RedirectStandardOutput (Join-Path $monitorDir "stdout.log") `
    -RedirectStandardError (Join-Path $monitorDir "stderr.log") `
    -PassThru

Write-F102Status "armed_waiting_bootbase" "F102 flash watcher and postflash 2.4 EMAC gate armed" @{
    dry_run_log = $dryLog
    command = $commandPath
    stdout = $stdout
    stderr = $stderr
    pid = $proc.Id
    monitor_command = $monitorCommandPath
    monitor_dir = $monitorDir
    monitor_pid = $monitorProc.Id
}
Write-Host "OMF102_AUTO_ARMED=1 pid=$($proc.Id) monitor_pid=$($monitorProc.Id) status=$StatusPath stdout=$stdout monitor=$monitorDir"
