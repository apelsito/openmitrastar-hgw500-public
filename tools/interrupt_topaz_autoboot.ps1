param(
    [string]$Port = "COM3",
    [string]$LogPath = "outputs\uart-live\topaz-autoboot-break.log",
    [int]$TimeoutSeconds = 150
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
$log = [IO.StreamWriter]::new(
    [IO.File]::Open($absoluteLog, [IO.FileMode]::Create,
        [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite),
    [Text.UTF8Encoding]::new($false))
$log.AutoFlush = $true
$tail = ""
$breakSent = $false

try {
    $serial.Open()
    Write-Host "TOPAZ_AUTOBOOT_LISTENER_READY port=$Port log=$absoluteLog"
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $chunk = $serial.ReadExisting()
        if ($chunk) {
            $log.Write($chunk)
            Write-Host -NoNewline $chunk
            $tail += $chunk
            if ($tail.Length -gt 4096) {
                $tail = $tail.Substring($tail.Length - 4096)
            }
        }

        if (-not $breakSent -and $tail -match "Hit any key to stop autoboot") {
            $serial.Write(" ")
            $breakSent = $true
            Write-Host "`nTOPAZ_AUTOBOOT_BREAK_SENT=1"
        }

        if ($breakSent -and $tail -match "(?:topaz|ZHAL)>") {
            Write-Host "`nTOPAZ_PROMPT_ACQUIRED=1 prompt=$($Matches[0]) log=$absoluteLog"
            exit 0
        }
        Start-Sleep -Milliseconds 20
    }
    throw "Timed out before acquiring topaz>"
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
    $log.Dispose()
}
