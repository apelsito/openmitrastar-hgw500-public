param(
    [string]$Port = "COM3",
    [int]$TimeoutSeconds = 180,
    [switch]$NoBoot
)

$ErrorActionPreference = "Stop"
$baud = 115200
$logDir = Join-Path $PSScriptRoot "..\outputs\uart-live"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $logDir "recover-oem-safety-$stamp.log"
$serial = [IO.Ports.SerialPort]::new(
    $Port, $baud, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
$serial.Handshake = [IO.Ports.Handshake]::None
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 100
$serial.WriteTimeout = 500
$log = [IO.StreamWriter]::new(
    [IO.File]::Open($logPath, [IO.FileMode]::Create,
        [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite),
    [Text.UTF8Encoding]::new($false))
$log.AutoFlush = $true
$tail = ""

function Read-Uart {
    param([int]$Seconds, [string[]]$Markers)
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $chunk = $serial.ReadExisting()
        if ($chunk) {
            $script:log.Write($chunk)
            Write-Host -NoNewline $chunk
            $script:tail += $chunk
            if ($script:tail.Length -gt 16384) {
                $script:tail = $script:tail.Substring($script:tail.Length - 16384)
            }
            foreach ($marker in $Markers) {
                if ($script:tail -match $marker) { return $marker }
            }
        }
        Start-Sleep -Milliseconds 15
    }
    throw "UART timeout waiting for: $($Markers -join ', ')"
}

function Send-Line {
    param([string]$Text, [string[]]$Markers, [int]$Seconds = 20)
    $script:tail = ""
    $serial.Write($Text + "`r")
    return Read-Uart -Seconds $Seconds -Markers $Markers
}

function Get-AtenPassword {
    param([string]$Seed)
    if ($Seed -notmatch '^[0-9A-Fa-f]{12}$') { throw "Invalid ATSE seed: $Seed" }
    $base = [Convert]::ToUInt32($Seed.Substring(0, 6), 16) -band 0x00ffffff
    $macLast = [Convert]::ToUInt32($Seed.Substring(10, 2), 16)
    # BootExtension loads (MAC & 7)+1 into LP_COUNT; ARC executes one fewer loop.
    $rotate = $macLast -band 7
    if ($rotate -eq 0) { $rotate = 8 }
    $sum = [uint32](($base + 0x10f0a563L) -band 0xffffffffL)
    $rotated = [uint32](($sum -shr $rotate) -bor
        (($sum -shl (32 - $rotate)) -band 0xffffffffL))
    return ('{0:X8}' -f ([uint32]($rotated -bxor $base)))
}

try {
    $serial.Open()
    Write-Host "RECOVERY_UART_OPEN port=$Port log=$logPath"
    $serial.Write("`r")
    $state = $null
    try {
        $state = Read-Uart -Seconds 5 -Markers @('topaz>\s*$', 'ZHAL>\s*$')
    } catch {
        $state = $null
        $tail = ""
    }
    if (-not $state) {
        Write-Host "RECOVERY_WAITING_FOR_AUTOBOOT_BREAK=1"
        $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
        while ([DateTime]::UtcNow -lt $deadline) {
            $chunk = $serial.ReadExisting()
            if ($chunk) {
                $log.Write($chunk); Write-Host -NoNewline $chunk; $tail += $chunk
                if ($tail -match 'Hit any key to stop autoboot') {
                    $serial.Write(" ")
                    $tail = ""
                }
                if ($tail -match 'topaz>\s*$') { $state = 'topaz>'; break }
                if ($tail -match 'ZHAL>\s*$') { $state = 'ZHAL>'; break }
                if ($tail.Length -gt 16384) { $tail = $tail.Substring($tail.Length - 16384) }
            }
            Start-Sleep -Milliseconds 15
        }
    }

    # Classify the prompt from a fresh response, not from buffered boot text.
    $tail = ""
    $serial.Write("help`r")
    [void](Read-Uart -Seconds 20 -Markers @('topaz>\s*$', 'ZHAL>\s*$'))
    if ($tail -match '(?m)^ATEN\s' -or $tail -match '(?m)^ATGU\s') {
        $state = 'ZHAL>'
    } elseif ($tail -match 'topaz>\s*$') {
        $state = 'topaz>'
    } else {
        throw "Could not classify current bootloader prompt"
    }

    if ($state -eq 'ZHAL>') {
        # ATEN rewrites the 128 KiB bootloader sector. Try the already-enabled
        # engineering path first and only calculate/write the flag if denied.
        Send-Line -Text 'ATGU' -Markers @('ZHAL>\s*$', 'Hit any key to exit') | Out-Null
        if ($tail -match 'Permission denied') {
            Send-Line -Text 'ATSE MSTC' -Markers @('ZHAL>\s*$') | Out-Null
            $seedMatch = [regex]::Match($tail, '(?m)^([0-9A-Fa-f]{12})\r?$')
            if (-not $seedMatch.Success) { throw "ATSE seed not found" }
            $password = Get-AtenPassword -Seed $seedMatch.Groups[1].Value
            Send-Line -Text "ATEN 1,$password" -Markers @('ZHAL>\s*$') | Out-Null
            if ($tail -notmatch '(?m)^OK\r?$') { throw "ATEN unlock rejected" }
            $serial.Write("ATGU`r")
        }
        if ($tail -notmatch 'Hit any key to exit') {
            [void](Read-Uart -Seconds 30 -Markers @('Hit any key to exit'))
        }
        $serial.Write(" `r")
        [void](Read-Uart -Seconds 20 -Markers @('topaz>\s*$'))
    }

    Send-Line -Text 'setenv bootcmd bootselect' -Markers @('topaz>\s*$') | Out-Null
    Send-Line -Text 'setenv bootselect 1' -Markers @('topaz>\s*$') | Out-Null
    Send-Line -Text 'saveenv' -Markers @('topaz>\s*$') -Seconds 45 | Out-Null
    Send-Line -Text 'printenv bootselect' -Markers @('topaz>\s*$') | Out-Null
    if ($tail -notmatch 'bootselect=1') { throw "bootselect readback mismatch" }
    Write-Host "RECOVERY_ENV_PASS bootcmd=bootselect bootselect=1"
    if ($NoBoot) { exit 0 }
    $serial.Write("reset`r")
    [void](Read-Uart -Seconds $TimeoutSeconds -Markers @('Linux version 2\.6\.35\.12'))
    Write-Host "RECOVERY_OEM_KERNEL_PASS=1"
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
    $log.Dispose()
}
