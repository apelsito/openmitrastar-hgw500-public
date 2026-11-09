[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Port = "COM3",
    [ValidateRange(30, 300)][int]$TimeoutSeconds = 180,
    [string]$LogPath = "outputs\uart-live\recover-topaz-tftp-loop-boot-live.log"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$absoluteLog = [IO.Path]::GetFullPath((Join-Path (Get-Location) $LogPath))
New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($absoluteLog)) | Out-Null
$serial = [IO.Ports.SerialPort]::new($Port, 115200, 'None', 8, 'One')
$serial.Handshake = 'None'; $serial.DtrEnable = $false; $serial.RtsEnable = $false
$serial.ReadTimeout = 100; $serial.WriteTimeout = 1000
$writer = [IO.StreamWriter]::new($absoluteLog, $false, [Text.UTF8Encoding]::new($false))
$writer.AutoFlush = $true
$tail = ''

function Read-Uart {
    $chunk = $serial.ReadExisting()
    if ($chunk) {
        $writer.Write($chunk); Write-Host -NoNewline $chunk
        $script:tail += $chunk
        if ($script:tail.Length -gt 32768) { $script:tail = $script:tail.Substring($script:tail.Length - 32768) }
    }
}
function Wait-For([string]$Pattern, [string]$Stage, [int]$Seconds) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        Read-Uart
        if ($script:tail -match $Pattern) { return }
        Start-Sleep -Milliseconds 20
    }
    throw "UART timeout during $Stage"
}
function Send-Line([string]$Line) {
    $serial.Write($Line + "`r")
    Write-Host "`nOMLYOKO_UART_TX=$Line"
}

try {
    $serial.Open()
    $serial.Write([string][char]0x03)
    Start-Sleep -Milliseconds 100
    $serial.Write("`r")
    Wait-For '(?:topaz|ZHAL)>\s*$' 'leave TFTP loop' 30
    if ($tail -match 'ZHAL>\s*$') {
        $tail = ''
        $serial.Write([string][char]0x15)
        $serial.Write([string][char]0x08)
        Send-Line 'ATGU'
        Wait-For 'Hit any key to exit' 'leave ZHAL' 10
        $serial.Write(" ")
        Wait-For 'Hit any key to stop autoboot' 'stop Topaz autoboot' 15
        $serial.Write(" ")
        Wait-For 'topaz>\s*$' 'acquire Topaz prompt' 15
    }
    $tail = ''
    Send-Line 'printenv bootcmd; printenv bootselect'
    Wait-For 'topaz>\s*$' 'read boot selector' 20
    if ($tail -notmatch '(?m)^bootcmd=bootselect\r?$' -or $tail -notmatch '(?m)^bootselect=0\r?$') {
        throw 'boot selector is not the preserved live-slot contract'
    }
    $tail = ''
    Send-Line 'bootselect'
    Wait-For 'Linux version 5\.10\.260-openmitrastar-radiohw' 'boot F164 kernel' 180
    Wait-For 'OMSSH_READY port=22 auth=ed25519-key-only forwarding=disabled' 'boot F164 SSH' 120
    Write-Output "OMLYOKO_TFTP_LOOP_RECOVERY_PASS=1 boot=mtd4-live flash_writes=0 env_writes=0 log=$absoluteLog"
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose(); $writer.Dispose()
}
