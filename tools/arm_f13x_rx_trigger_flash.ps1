[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("F133", "F134", "F135")]
    [string]$Profile = "F133",
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [string]$CurrentLiveCrc32 = "",
    [ValidateRange(60, 21600)]
    [int]$TriggerWaitSeconds = 21600,
    [ValidateRange(1, 300)]
    [int]$NoRxAbortSeconds = 180,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [switch]$AllowBlindAutobreak,
    [switch]$KeepExistingTftp
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$profileLower = $Profile.ToLowerInvariant()
$outputDir = Join-Path $root "outputs\flash-watch\f13x-rx-trigger-$profileLower-$stamp"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$triggerStatusPath = Join-Path $outputDir "trigger-status.json"
$triggerLogPath = Join-Path $outputDir "trigger-uart.log"

$profiles = @{
    F133 = @{
        helper = "arm_f133_5g_disable_hr_timer_flash.ps1"
        candidate = "f133-5g-disable-hr-timer-from-f132"
        default_current_crc32 = "d11c5cbd"
        expected_full_slot_crc32 = "e692b50c"
        marker = "OMF133"
    }
    F134 = @{
        helper = "arm_f134_5g_vap_rf_hold_flash.ps1"
        candidate = "f134-5g-vap-rf-hold-from-f133"
        default_current_crc32 = "d11c5cbd"
        expected_full_slot_crc32 = "218cf82a"
        marker = "OMF134"
    }
    F135 = @{
        helper = "arm_f135_5g_core_hold_flash.ps1"
        candidate = "f135-5g-core-hold-from-f133"
        default_current_crc32 = "d11c5cbd"
        expected_full_slot_crc32 = "c12d62b6"
        marker = "OMF135"
    }
}

$profileInfo = $profiles[$Profile]
if (-not $CurrentLiveCrc32) {
    $CurrentLiveCrc32 = $profileInfo.default_current_crc32
}
$blindAtguAfterNoRxSeconds = if ($AllowBlindAutobreak) { 8 } else { 0 }

function Write-TriggerStatus([string]$State, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f13x-rx-trigger/v1"
        state = $State
        updated_at = (Get-Date).ToString("o")
        output_dir = $outputDir
        profile = $Profile
        candidate = $profileInfo.candidate
        port = $Port
        server_ip = $ServerIp
        client_ip = $ClientIp
        host = $HostAddress
        current_live_crc32 = $CurrentLiveCrc32.ToLowerInvariant()
        expected_full_slot_crc32 = $profileInfo.expected_full_slot_crc32
        trigger_wait_seconds = $TriggerWaitSeconds
        no_rx_abort_seconds = $NoRxAbortSeconds
        blind_autobreak = [bool]$AllowBlindAutobreak
        blind_atgu_after_no_rx_seconds = $blindAtguAfterNoRxSeconds
        flashes = $false
        uart_tx_before_rx = $false
        trigger_log = $triggerLogPath
    }
    foreach ($key in $Extra.Keys) { $payload[$key] = $Extra[$key] }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $triggerStatusPath
}

function Wait-FirstUartRx {
    $serial = [IO.Ports.SerialPort]::new(
        $Port, 115200, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
    $serial.Handshake = [IO.Ports.Handshake]::None
    $serial.DtrEnable = $false
    $serial.RtsEnable = $false
    $serial.ReadTimeout = 200
    $serial.WriteTimeout = 200
    $bytes = 0
    $deadline = [DateTime]::UtcNow.AddSeconds($TriggerWaitSeconds)
    try {
        $serial.Open()
        $serial.DiscardInBuffer()
        Write-TriggerStatus "armed_waiting_for_first_rx" @{ flashes = $false }
        while ([DateTime]::UtcNow -lt $deadline) {
            try {
                $chunk = $serial.ReadExisting()
            } catch {
                throw
            }
            if ($chunk) {
                Add-Content -Encoding ascii -LiteralPath $triggerLogPath -Value $chunk
                $bytes += $chunk.Length
                Write-TriggerStatus "first_rx_seen_starting_flash" @{
                    first_rx_bytes = $bytes
                    flashes = $true
                }
                return $bytes
            }
            Start-Sleep -Milliseconds 50
        }
        Write-TriggerStatus "trigger_timeout_no_rx" @{ first_rx_bytes = $bytes }
        return 0
    } finally {
        if ($serial.IsOpen) { $serial.Close() }
        $serial.Dispose()
    }
}

$marker = [string]$profileInfo.marker
Write-Host "$($marker)_RX_TRIGGER_ARMED=1 status=$triggerStatusPath"
Write-Host "$($marker)_RX_TRIGGER_ACTION=power_cycle_router_now"
Write-Host "$($marker)_RX_TRIGGER_NO_UART_TX_BEFORE_RX=1 wait_seconds=$TriggerWaitSeconds"

$rxBytes = Wait-FirstUartRx
if ($rxBytes -le 0) {
    Write-Error "$($marker)_RX_TRIGGER_TIMEOUT_NO_RX status=$triggerStatusPath"
    exit 2
}

$args = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot $profileInfo.helper),
    "-Execute",
    "-Port", $Port,
    "-ServerIp", $ServerIp,
    "-ClientIp", $ClientIp,
    "-HostAddress", $HostAddress,
    "-CurrentLiveCrc32", $CurrentLiveCrc32.ToLowerInvariant(),
    "-BootWaitSeconds", "600",
    "-FlashTimeoutSeconds", "$FlashTimeoutSeconds",
    "-NoRxAbortSeconds", "$NoRxAbortSeconds",
    "-BlindAtguAfterNoRxSeconds", "$blindAtguAfterNoRxSeconds",
    "-OutputDir", $outputDir
)
if ($AllowBlindAutobreak) { $args += "-AllowBlindAutobreak" }
if ($KeepExistingTftp) { $args += "-KeepExistingTftp" }

@{
    executable = "powershell.exe"
    args = $args
    triggered_by_first_rx_bytes = $rxBytes
} | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath (Join-Path $outputDir "flash-command.args.json")

Write-Host "$($marker)_RX_TRIGGER_FLASH_START=1 output_dir=$outputDir first_rx_bytes=$rxBytes"
& powershell.exe @args
$rc = $LASTEXITCODE
if ($rc -eq 0) {
    Write-TriggerStatus "flash_pass" @{ exit_code = $rc; flashes = $true }
    Write-Host "$($marker)_RX_TRIGGER_FLASH_PASS=1 status=$triggerStatusPath"
    exit 0
}
Write-TriggerStatus "flash_failed" @{ exit_code = $rc; flashes = $true }
Write-Error "$($marker)_RX_TRIGGER_FLASH_FAIL rc=$rc status=$triggerStatusPath"
exit $rc
