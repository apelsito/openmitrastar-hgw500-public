param(
    [string]$Port = "COM3",
    [string]$ExpectedPnpDeviceId = "",
    [string]$LogPath = "outputs\uart-live\sysrq-to-topaz.log",
    [int]$TimeoutSeconds = 180,
    [switch]$NoReboot,
    [switch]$PulseResetLinesFirst
)

$ErrorActionPreference = "Stop"
if ($ExpectedPnpDeviceId) {
    # FTDI can be present in PnP Ports while Win32_SerialPort is empty.
    # Use the same pinned enumeration as the parent guard; never infer identity
    # from an available COM name alone. This helper does not acquire ownership.
    . (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
    [void](Get-F319SerialDevice -Port $Port -ExpectedPnpDeviceId $ExpectedPnpDeviceId)
}
$absoluteLog = if ([IO.Path]::IsPathRooted($LogPath)) {
    [IO.Path]::GetFullPath($LogPath)
} else {
    [IO.Path]::GetFullPath((Join-Path (Get-Location) $LogPath))
}
New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($absoluteLog)) | Out-Null

$serial = [IO.Ports.SerialPort]::new(
    $Port, 115200, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
$serial.Handshake = [IO.Ports.Handshake]::None
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 100
$serial.WriteTimeout = 1000
$log = [IO.StreamWriter]::new(
    [IO.File]::Open($absoluteLog, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite),
    [Text.UTF8Encoding]::new($false))
$log.AutoFlush = $true
$tail = ""
$autobootBreakCount = 0
$lastAutobootBreakAt = [DateTime]::MinValue
$interruptUntil = [DateTime]::MinValue
$zhalEscaped = $false

function Read-Uart {
    $chunk = $serial.ReadExisting()
    if ($chunk) {
        $log.Write($chunk)
        Write-Host -NoNewline $chunk
        $script:tail += $chunk
        if ($script:tail.Length -gt 32768) {
            $script:tail = $script:tail.Substring($script:tail.Length - 32768)
        }
    }
}

function Send-Line([string]$Text) {
    $serial.Write($Text + "`r")
}

try {
    $serial.Open()
    $serial.DiscardInBuffer()
    if ($PulseResetLinesFirst) {
        $serial.DtrEnable = $true
        $serial.RtsEnable = $true
        Start-Sleep -Milliseconds 250
        $serial.DtrEnable = $false
        $serial.RtsEnable = $false
        Start-Sleep -Milliseconds 250
        Write-Host "OMUART_RESET_LINES_PULSED=1"
    }
    if ($NoReboot) {
        Write-Host "OMUART_TO_TOPAZ_ATTACH_START port=$Port log=$absoluteLog"
        $interruptUntil = [DateTime]::UtcNow.AddSeconds(12)
    } else {
        Write-Host "OMSYSRQ_TO_TOPAZ_START port=$Port log=$absoluteLog"
        $serial.BreakState = $true
        Start-Sleep -Milliseconds 600
        $serial.BreakState = $false
        Start-Sleep -Milliseconds 150
        $serial.Write("b")
        Write-Host "OMSYSRQ_REBOOT_SENT=1"
    }

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        Read-Uart
        if ($tail -match 'Hit any key (to stop autoboot|to exit)') {
            $now = [DateTime]::UtcNow
            if (($now - $lastAutobootBreakAt).TotalMilliseconds -gt 800) {
                $serial.Write(" ")
                Start-Sleep -Milliseconds 50
                $serial.Write("`r")
                $autobootBreakCount += 1
                $lastAutobootBreakAt = $now
                $interruptUntil = $now.AddSeconds(6)
                Write-Host "`nOMBOOT_AUTOBOOT_BREAK_SENT=$autobootBreakCount"
            }
            $tail = ""
        }
        if ($tail -match 'ZHAL>\s*$' -and -not $zhalEscaped) {
            $serial.Write([string][char]0x15)
            $serial.Write([string][char]0x08)
            Start-Sleep -Milliseconds 80
            Send-Line 'ATGU'
            $zhalEscaped = $true
            $interruptUntil = [DateTime]::UtcNow.AddSeconds(10)
            $tail = ""
            Write-Host "`nOMZHAL_ATGU_SENT=1"
        }
        if ([DateTime]::UtcNow -lt $interruptUntil) {
            $serial.Write(" ")
            Start-Sleep -Milliseconds 40
            $serial.Write("`r")
            Start-Sleep -Milliseconds 60
        }
        if ($tail -match 'topaz>\s*$') {
            Write-Host "`nOMTOPAZ_PROMPT_READY=1 log=$absoluteLog"
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
