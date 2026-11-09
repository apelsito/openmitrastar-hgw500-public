param(
    [string]$Port = "COM3",
    [int]$TimeoutSeconds = 240,
    [string]$LogPath = "outputs\uart-live\oem-safety-ram-boot.log",
    [switch]$StopAtTopaz
)

$ErrorActionPreference = "Stop"
$log = [IO.Path]::GetFullPath((Join-Path (Get-Location) $LogPath))
New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($log)) | Out-Null
$writer = [IO.StreamWriter]::new($log, $false, [Text.UTF8Encoding]::new($false))
$writer.AutoFlush = $true
$serial = [IO.Ports.SerialPort]::new($Port, 115200, 'None', 8, 'One')
$serial.Handshake = 'None'
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 100
$serial.WriteTimeout = 1000
$tail = ''
$stage = 0

function Send-Line([string]$Line) {
    $serial.Write($Line + "`r")
    Write-Output "OEM_SAFETY_UART_TX=$Line"
}

try {
    $serial.Open()
    $serial.Write("`r")
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $chunk = $serial.ReadExisting()
        if ($chunk) {
            $writer.Write($chunk)
            Write-Host -NoNewline $chunk
            $tail += $chunk
            if ($tail.Length -gt 32768) { $tail = $tail.Substring($tail.Length - 32768) }
        }
        switch ($stage) {
            0 {
                if ($tail -match 'topaz>\s*$') {
                    if ($StopAtTopaz) {
                        Write-Output "TOPAZ_PROMPT_PASS=1 log=$log"
                        exit 0
                    }
                    Send-Line 'spi_flash read 0x00040000 0x83000000 0x007a0000'
                    $stage = 2; $tail = ''
                } elseif ($tail -match 'Hit any key to exit') {
                    $serial.Write("`r")
                    $stage = 1; $tail = ''
                } elseif ($tail -match 'Hit any key to stop autoboot|ZHAL>') {
                    $serial.Write("`r")
                    Start-Sleep -Milliseconds 120
                    Send-Line 'ATGU'
                    $stage = 1; $tail = ''
                }
            }
            1 {
                if ($tail -match 'Hit any key to exit') {
                    $serial.Write("`r")
                    $tail = ''
                }
                if ($tail -match 'Hit any key to stop autoboot') {
                    $serial.Write("`r")
                    $tail = ''
                }
                if ($tail -match 'topaz>\s*$') {
                    if ($StopAtTopaz) {
                        Write-Output "TOPAZ_PROMPT_PASS=1 log=$log"
                        exit 0
                    }
                    Send-Line 'spi_flash read 0x00040000 0x83000000 0x007a0000'
                    $stage = 2; $tail = ''
                }
            }
            2 {
                if ($tail -match 'topaz>\s*$') {
                    if ($tail -notmatch 'ret_size=7995392|ret_size=0x7a0000') {
                        throw 'Safety slot read did not return exactly 0x7a0000 bytes'
                    }
                    Send-Line 'iminfo 0x83000000'
                    $stage = 3; $tail = ''
                }
            }
            3 {
                if ($tail -match 'topaz>\s*$') {
                    if ($tail -notmatch 'Verifying Checksum\s+\.\.\.\s+OK') {
                        throw 'Safety image checksum was not accepted'
                    }
                    Send-Line 'bootm 0x83000000'
                    $stage = 4; $tail = ''
                }
            }
            4 {
                if ($tail -match 'Linux version 2\.6\.35|init started: BusyBox|Please press Enter to activate this console') {
                    Write-Output "OEM_SAFETY_RAM_BOOT_PASS=1 log=$log"
                    exit 0
                }
                if ($tail -match 'EV_TLB|Kernel panic|Bad Magic Number|ERROR:') {
                    throw 'Safety image failed after bootm'
                }
            }
        }
        Start-Sleep -Milliseconds 20
    }
    throw "Timed out at OEM safety RAM boot stage $stage"
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
    $writer.Dispose()
}
