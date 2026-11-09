[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "d11c5cbd",
    [ValidateRange(600, 21600)]
    [int]$BootWaitSeconds = 21600,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [ValidateRange(1, 300)]
    [int]$NoRxAbortSeconds = 180,
    [switch]$NoPulseResetLinesFirst,
    [switch]$AllowBlindAutobreak,
    [switch]$KeepExistingTftp
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outputDir = Join-Path $root "outputs\flash-watch\f134-wait-powercycle-$stamp"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$statusPath = Join-Path $outputDir "wait-status.json"
$blindAtguAfterNoRxSeconds = if ($AllowBlindAutobreak) { 8 } else { 0 }

@{
    schema = "openmitrastar.f134-wait-powercycle/v1"
    state = "armed_waiting_for_powercycle_or_bootbase"
    updated_at = (Get-Date).ToString("o")
    output_dir = $outputDir
    candidate = "f134-5g-vap-rf-hold-from-f133"
    current_live_crc32 = $CurrentLiveCrc32.ToLowerInvariant()
    expected_full_slot_crc32 = "218cf82a"
    port = $Port
    server_ip = $ServerIp
    client_ip = $ClientIp
    host = $HostAddress
    boot_wait_seconds = $BootWaitSeconds
    no_rx_abort_seconds = $NoRxAbortSeconds
    blind_autobreak = [bool]$AllowBlindAutobreak
    blind_atgu_after_no_rx_seconds = $blindAtguAfterNoRxSeconds
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding ascii -LiteralPath $statusPath

$args = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot "arm_f134_5g_vap_rf_hold_flash.ps1"),
    "-Execute",
    "-Port", $Port,
    "-ServerIp", $ServerIp,
    "-ClientIp", $ClientIp,
    "-HostAddress", $HostAddress,
    "-CurrentLiveCrc32", $CurrentLiveCrc32.ToLowerInvariant(),
    "-BootWaitSeconds", "$BootWaitSeconds",
    "-FlashTimeoutSeconds", "$FlashTimeoutSeconds",
    "-NoRxAbortSeconds", "$NoRxAbortSeconds",
    "-BlindAtguAfterNoRxSeconds", "$blindAtguAfterNoRxSeconds",
    "-AllowNoRxRebootAssist",
    "-OutputDir", $outputDir
)
if (-not $NoPulseResetLinesFirst) { $args += "-PulseResetLinesFirst" }
if ($AllowBlindAutobreak) { $args += "-AllowBlindAutobreak" }
if ($KeepExistingTftp) { $args += "-KeepExistingTftp" }

@{
    executable = "powershell.exe"
    args = $args
} | ConvertTo-Json -Depth 6 | Set-Content -Encoding ascii -LiteralPath (Join-Path $outputDir "command.args.json")

Write-Host "OMF134_WAIT_POWER_CYCLE_ARMED=1 status=$statusPath"
Write-Host "OMF134_WAIT_POWER_CYCLE_ACTION=power_cycle_router_now"
Write-Host "OMF134_WAIT_POWER_CYCLE_RX_GATE=1 no_rx_abort_seconds=$NoRxAbortSeconds blind_autobreak=$([int]$AllowBlindAutobreak.IsPresent)"
& powershell.exe @args
