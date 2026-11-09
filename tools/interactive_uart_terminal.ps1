param(
    [string]$Port = "COM3",
    [int]$Baud = 115200,
    [string]$LogPath = "outputs\uart-live\interactive-uart.log",
    [string]$QueuePath = "outputs\uart-live\uart-command-queue"
)

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$absoluteLog = [IO.Path]::GetFullPath((Join-Path $root $LogPath))
$absoluteQueue = [IO.Path]::GetFullPath((Join-Path $root $QueuePath))
New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($absoluteLog)) | Out-Null
New-Item -ItemType Directory -Force -Path $absoluteQueue | Out-Null

$serial = [IO.Ports.SerialPort]::new(
    $Port, $Baud, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
$serial.Handshake = [IO.Ports.Handshake]::None
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 50
$serial.WriteTimeout = 500
$serial.NewLine = "`r"
$log = [IO.StreamWriter]::new(
    [IO.File]::Open($absoluteLog, [IO.FileMode]::Append,
        [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite),
    [Text.UTF8Encoding]::new($false))
$log.AutoFlush = $true

try {
    $Host.UI.RawUI.WindowTitle = "OpenMitraStar UART - $Port $Baud 8N1"
    Clear-Host
    Write-Host "OpenMitraStar UART terminal"
    Write-Host "$Port @ $Baud 8N1, no flow control, VCC disconnected"
    Write-Host "Power-cycle the router and press SPACE at the autoboot countdown."
    Write-Host "Ctrl+C closes this terminal. Log: $absoluteLog"
    Write-Host "Shared command queue: $absoluteQueue"
    Write-Host ""
    $serial.Open()
    while ($true) {
        $incoming = $serial.ReadExisting()
        if ($incoming) {
            [Console]::Write($incoming)
            $log.Write($incoming)
        }

        while ([Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)
            if (($key.Modifiers -band [ConsoleModifiers]::Control) -and
                $key.Key -eq [ConsoleKey]::C) {
                throw [OperationCanceledException]::new("Closed by user")
            }
            switch ($key.Key) {
                Enter     { $serial.Write("`r") }
                Backspace { $serial.Write([string][char]8) }
                Escape    { $serial.Write([string][char]27) }
                default {
                    if ($key.KeyChar -ne [char]0) {
                        $serial.Write([string]$key.KeyChar)
                    }
                }
            }
        }

        $queued = Get-ChildItem -LiteralPath $absoluteQueue -Filter '*.uart' -File |
            Sort-Object Name |
            Select-Object -First 1
        if ($queued) {
            $command = (Get-Content -LiteralPath $queued.FullName -Raw).TrimEnd("`r", "`n")
            Remove-Item -LiteralPath $queued.FullName -Force
            if ($command) {
                $visibleCommand = if ($command -match '^seed_') {
                    'seed_<redacted>'
                } else {
                    $command
                }
                $visible = "`r`n[Codex -> UART] $visibleCommand`r`n"
                [Console]::Write($visible)
                $log.Write($visible)
                $serial.Write($command + "`r")
            }
        }
        Start-Sleep -Milliseconds 5
    }
} catch [OperationCanceledException] {
    Write-Host "`nUART terminal closed."
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
    $log.Dispose()
}
