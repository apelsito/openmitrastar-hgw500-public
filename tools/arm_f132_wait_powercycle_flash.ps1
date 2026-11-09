[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
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
$outputDir = Join-Path $root "outputs\flash-watch\f132-wait-powercycle-$stamp"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$statusPath = Join-Path $outputDir "wait-status.json"
$blindAtguAfterNoRxSeconds = if ($AllowBlindAutobreak) { 8 } else { 0 }

@{
    schema = "openmitrastar.f132-wait-powercycle/v1"
    state = "armed_waiting_for_powercycle_or_bootbase"
    updated_at = (Get-Date).ToString("o")
    output_dir = $outputDir
    candidate = "f132-5g-hrflags-skip-epilogue-from-f129"
    current_live_crc32 = "b168f55e"
    expected_full_slot_crc32 = "d11c5cbd"
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
    "-File", (Join-Path $PSScriptRoot "arm_f132_5g_hrflags_skip_epilogue_flash.ps1"),
    "-Execute",
    "-Port", $Port,
    "-ServerIp", $ServerIp,
    "-ClientIp", $ClientIp,
    "-HostAddress", $HostAddress,
    "-CurrentLiveCrc32", "b168f55e",
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

Write-Host "OMF132_WAIT_POWER_CYCLE_ARMED=1 status=$statusPath"
Write-Host "OMF132_WAIT_POWER_CYCLE_ACTION=power_cycle_router_now"
Write-Host "OMF132_WAIT_POWER_CYCLE_RX_GATE=1 no_rx_abort_seconds=$NoRxAbortSeconds blind_autobreak=$([int]$AllowBlindAutobreak.IsPresent)"
& powershell.exe @args
