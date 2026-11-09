param(
    [Parameter(Mandatory = $true)]
    [string]$Command,
    [string]$Port = "COM3",
    [string]$LogPath = "outputs\uart-live\topaz-command.log",
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"
$absoluteLog = [IO.Path]::GetFullPath((Join-Path (Get-Location) $LogPath))
New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($absoluteLog)) | Out-Null
$serial = [IO.Ports.SerialPort]::new(
    $Port, 115200, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
$serial.Handshake = [IO.Ports.Handshake]::None
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 100
$serial.WriteTimeout = 500
$log = [IO.StreamWriter]::new($absoluteLog, $false, [Text.UTF8Encoding]::new($false))
$log.AutoFlush = $true
$output = [Text.StringBuilder]::new()

try {
    $serial.Open()
    $serial.DiscardInBuffer()
    $serial.Write($Command + "`r")
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $chunk = $serial.ReadExisting()
        if ($chunk) {
            $log.Write($chunk)
            Write-Host -NoNewline $chunk
            [void]$output.Append($chunk)
            if ($output.ToString() -match "(?:topaz|ZHAL)>\s*$") {
                Write-Host "`nTOPAZ_COMMAND_COMPLETE=1 prompt=$($Matches[0].Trim()) command=$Command"
                exit 0
            }
        }
        Start-Sleep -Milliseconds 20
    }
    throw "Timed out waiting for a Topaz/ZHAL prompt after command: $Command"
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
    $log.Dispose()
}
