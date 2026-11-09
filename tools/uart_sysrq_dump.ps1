param(
    [string]$Port = 'COM3',
    [int]$ReadSeconds = 8,
    [string]$LogPath = 'outputs\uart-live\uart-sysrq-dump.log'
)

$ErrorActionPreference = 'Stop'
$serial = [IO.Ports.SerialPort]::new(
    $Port, 115200, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
$serial.Handshake = [IO.Ports.Handshake]::None
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 100
$serial.WriteTimeout = 500
$output = [Text.StringBuilder]::new()

function Read-Uart([int]$Seconds) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $chunk = $serial.ReadExisting()
        if ($chunk) {
            [void]$output.Append($chunk)
            Write-Host -NoNewline $chunk
        }
        Start-Sleep -Milliseconds 20
    }
}

function Send-SysRq([char]$Key) {
    $serial.BreakState = $true
    Start-Sleep -Milliseconds 600
    $serial.BreakState = $false
    Start-Sleep -Milliseconds 150
    $serial.Write([string]$Key)
    Write-Host "UART_SYSRQ_SENT key=$Key"
    Read-Uart $ReadSeconds
}

try {
    $serial.Open()
    Send-SysRq 'w'
    Send-SysRq 'l'
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
    $directory = Split-Path -Parent $LogPath
    if ($directory) { New-Item -ItemType Directory -Force -Path $directory | Out-Null }
    [IO.File]::WriteAllText(
        [IO.Path]::GetFullPath($LogPath), $output.ToString(),
        [Text.UTF8Encoding]::new($false))
}

Write-Host "UART_SYSRQ_DUMP_COMPLETE log=$LogPath bytes=$($output.Length)"
