param(
    [string]$Port = "COM3",
    [Parameter(Mandatory = $true)]
    [string]$Pattern,
    [int]$TimeoutSeconds = 120,
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$rawPath = Join-Path $OutputDirectory "topaz-marker.bin"
$textPath = Join-Path $OutputDirectory "topaz-marker.log"

$serial = [IO.Ports.SerialPort]::new(
    $Port, 115200, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
$serial.Handshake = [IO.Ports.Handshake]::None
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 200
$serial.WriteTimeout = 200
$buffer = [byte[]]::new(4096)
$raw = [IO.File]::Open(
    $rawPath, [IO.FileMode]::Create, [IO.FileAccess]::Write,
    [IO.FileShare]::ReadWrite)
$text = [IO.StreamWriter]::new(
    [IO.File]::Open(
        $textPath, [IO.FileMode]::Create, [IO.FileAccess]::Write,
        [IO.FileShare]::ReadWrite),
    [Text.UTF8Encoding]::new($false))
$text.AutoFlush = $true
$tail = ""
$matched = $false

try {
    $serial.Open()
    Write-Host "TOPAZ_UART_MARKER_LISTENING port=$Port pattern=$Pattern"
    Write-Host "TOPAZ_UART_MARKER_LOG text=$textPath raw=$rawPath"
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $count = $serial.Read($buffer, 0, $buffer.Length)
        } catch [TimeoutException] {
            continue
        }
        if ($count -le 0) { continue }
        $raw.Write($buffer, 0, $count)
        $raw.Flush()
        $chunk = [Text.Encoding]::ASCII.GetString($buffer, 0, $count)
        $text.Write($chunk)
        Write-Host -NoNewline $chunk
        $tail += $chunk
        if ([Text.RegularExpressions.Regex]::IsMatch($tail, $Pattern)) {
            $matched = $true
            break
        }
        if ($tail.Length -gt 32768) {
            $tail = $tail.Substring($tail.Length - 32768)
        }
    }
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $text.Dispose()
    $raw.Dispose()
    $serial.Dispose()
}

if (-not $matched) {
    throw "UART marker not observed: $Pattern"
}
Write-Host "`nTOPAZ_UART_MARKER_PASS pattern=$Pattern"
