param(
    [string]$Port,
    [int]$Seconds = 240,
    [string]$OutputDirectory = "outputs\uart"
)

$ErrorActionPreference = "Stop"

if (-not $Port) {
    $candidates = @(Get-CimInstance Win32_SerialPort |
        Where-Object { $_.DeviceID -ne "COM1" } |
        Select-Object -ExpandProperty DeviceID)
    if ($candidates.Count -ne 1) {
        throw "Expected exactly one USB serial port, found: $($candidates -join ', ')"
    }
    $Port = $candidates[0]
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$rawPath = Join-Path $OutputDirectory "topaz-$stamp.bin"
$textPath = Join-Path $OutputDirectory "topaz-$stamp.log"

$serial = [System.IO.Ports.SerialPort]::new(
    $Port, 115200, [System.IO.Ports.Parity]::None, 8,
    [System.IO.Ports.StopBits]::One)
$serial.Handshake = [System.IO.Ports.Handshake]::None
$serial.ReadTimeout = 200
$serial.WriteTimeout = 200
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$buffer = [byte[]]::new(4096)
$raw = [System.IO.File]::Open(
    $rawPath, [System.IO.FileMode]::Create,
    [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
$text = [System.IO.StreamWriter]::new(
    [System.IO.File]::Open(
        $textPath, [System.IO.FileMode]::Create,
        [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite),
    [System.Text.UTF8Encoding]::new($false))
$text.AutoFlush = $true

try {
    $serial.Open()
    Write-Host "TOPAZ_UART_LISTENING port=$Port baud=115200 mode=8N1 tx=disabled"
    Write-Host "TOPAZ_UART_LIVE_LOG text=$textPath raw=$rawPath"
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $count = $serial.Read($buffer, 0, $buffer.Length)
        } catch [System.TimeoutException] {
            continue
        }
        if ($count -le 0) { continue }
        $raw.Write($buffer, 0, $count)
        $raw.Flush()
        $chunk = [System.Text.Encoding]::ASCII.GetString($buffer, 0, $count)
        $text.Write($chunk)
        Write-Host -NoNewline $chunk
    }
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $text.Dispose()
    $raw.Dispose()
    $serial.Dispose()
}

Write-Host "`nTOPAZ_UART_CAPTURE_COMPLETE raw=$rawPath text=$textPath bytes=$((Get-Item $rawPath).Length)"
