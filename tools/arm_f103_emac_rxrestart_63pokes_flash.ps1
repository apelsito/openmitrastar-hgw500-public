[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "0c46aec2",
    [ValidateRange(600, 21600)]
    [int]$BootWaitSeconds = 21600,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [ValidateRange(5, 300)]
    [int]$NoRxAbortSeconds = 45,
    [switch]$PulseResetLinesFirst,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$BuildDir = Join-Path $Root "work\mission-state\q3-persistent-composite-f103-emac-rxrestart-63pokes-from-f101\build"
$Base = "openmitrastar-linux510-q3-persistent-f103-emac-rxrestart-63pokes-from-f101-LZMA-OFFLINE-NO-FLASH"
$Ack = "OPENMITRASTAR_Q3_F103_EMAC_RXRESTART_63POKES_FROM_F101_MTD4_FLASH_682484E6"
$ExpectedSha256 = "682484e6bbd8406b8e1b2868622e256303141e0e416a339fec4f480dfb99c453"
$ExpectedBytes = "5614720"

if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\flash-watch\f103-emac-rxrestart-63pokes-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StatusPath = Join-Path $OutputDir "status.json"

function Write-F103Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f103-auto-arm/v1"
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
        Write-F103Status "missing_input" "F103 input missing" @{ missing = $path }
        throw "missing F103 input: $path"
    }
}

$actualSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash.ToLowerInvariant()
$actualBytes = (Get-Item -LiteralPath $candidate).Length
if ($actualSha -ne $ExpectedSha256 -or [string]$actualBytes -ne $ExpectedBytes) {
    Write-F103Status "candidate_mismatch" "F103 candidate hash/size mismatch" @{
        actual_sha256 = $actualSha
        actual_bytes = $actualBytes
    }
    throw "F103 candidate hash/size mismatch"
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
    Write-F103Status "dry_run_failed" "F103 dry-run failed" @{ dry_run_log = $dryLog }
    throw "F103 dry-run failed; see $dryLog"
}

if (-not $Execute) {
    Write-F103Status "dry_run_pass" "F103 dry-run passed; no router writes" @{ dry_run_log = $dryLog }
    Write-Host "OMF103_AUTO_ARM_DRY_RUN_PASS=1 status=$StatusPath"
    exit 0
}

$stdout = Join-Path $OutputDir "flash-watch.stdout.log"
$stderr = Join-Path $OutputDir "flash-watch.stderr.log"
$pulseResetArg = if ($PulseResetLinesFirst) { " -PulseResetLinesFirst" } else { "" }
$flashCommand = @"
$envBlock
& '$Root\tools\q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1' -Execute -Ack '$Ack' -Port '$Port' -ServerIp '$ServerIp' -ClientIp '$ClientIp' -HostAddress '$HostAddress' -CurrentLiveCrc32 '$($CurrentLiveCrc32.ToLowerInvariant())' -BootWaitSeconds $BootWaitSeconds -FlashTimeoutSeconds $FlashTimeoutSeconds -NoRxAbortSeconds $NoRxAbortSeconds -AllowBlindAutobreak -AllowNoRxRebootAssist -SysRqRebootFirst -SysRqRetrySeconds 5 -ConsoleRebootAssist -ConsoleRebootRetrySeconds 5$pulseResetArg
"@
$commandPath = Join-Path $OutputDir "flash-command.ps1"
$flashCommand | Set-Content -Encoding ascii -LiteralPath $commandPath
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($flashCommand))
$proc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden `
    -ArgumentList "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded" `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

Write-F103Status "armed_waiting_bootbase" "F103 flash watcher armed" @{
    dry_run_log = $dryLog
    command = $commandPath
    stdout = $stdout
    stderr = $stderr
    pid = $proc.Id
}
Write-Host "OMF103_AUTO_ARMED=1 pid=$($proc.Id) status=$StatusPath stdout=$stdout"
