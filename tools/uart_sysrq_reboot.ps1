param(
    [string]$Port = "COM3",
    [int]$WaitSeconds = 30
)

$ErrorActionPreference = "Stop"
$serial = [IO.Ports.SerialPort]::new(
    $Port, 115200, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
$serial.Handshake = [IO.Ports.Handshake]::None
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 100
$serial.WriteTimeout = 500

try {
    $serial.Open()
    $serial.BreakState = $true
    Start-Sleep -Milliseconds 600
    $serial.BreakState = $false
    Start-Sleep -Milliseconds 150
    $serial.Write("b")
    Write-Host "UART_SYSRQ_REBOOT_SENT port=$Port"
    $deadline = [DateTime]::UtcNow.AddSeconds($WaitSeconds)
    $tail = ""
    while ([DateTime]::UtcNow -lt $deadline) {
        $chunk = $serial.ReadExisting()
        if ($chunk) {
            Write-Host -NoNewline $chunk
            $tail += $chunk
            if ($tail -match 'Boot reached stage 13|Quantenna U-Boot') {
                Write-Host "`nUART_SYSRQ_REBOOT_CONFIRMED=1"
                exit 0
            }
            if ($tail.Length -gt 8192) {
                $tail = $tail.Substring($tail.Length - 8192)
            }
        }
        Start-Sleep -Milliseconds 20
    }
    throw "No reboot signature received after serial SysRq"
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
}
