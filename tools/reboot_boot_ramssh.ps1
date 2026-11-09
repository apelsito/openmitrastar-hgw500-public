param(
    [string]$Port = "COM3",
    [string]$Filename = "linux510-ssh-txfix-webformat.bin",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.200",
    [string]$SshHost = "",
    [string]$LoadAddress = "0x83000000",
    [int]$TimeoutSeconds = 420,
    [string]$EntropyPromptPattern = '(?s)(RAMSSH|OMPRODUCT)_ENTR.{0,4096}OPY_SEED_REQUIRE.{0,4096}D',
    [string]$EntropyOkPattern = '(RAMSSH_SERIAL_ENTROPY_OK|OMPRODUCT_SERIAL_ENTROPY_OK) bits=256',
    [switch]$AutonomousEntropy,
    [string]$AutonomousEntropyPattern = 'OMPRODUCT_ENTROPY_LOCAL_OK source=jitterentropy_rng credited_bits=256 crng=ready',
    [string]$ReadyPattern = '(RAMSSH_SSH_EXEC|OMPRODUCT_READY state=(ready|degraded))',
    [int]$ReadyUartWaitSeconds = 15,
    [int]$AutobootWaitSeconds = 90,
    [switch]$UseSshReboot,
    [switch]$SkipReboot
)

$ErrorActionPreference = "Stop"

function Assert-IPv4Literal([string]$Name, [string]$Value) {
    $Parsed = [Net.IPAddress]::None
    if (-not [Net.IPAddress]::TryParse($Value, [ref]$Parsed) -or
        $Parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or
        $Parsed.ToString() -cne $Value) {
        throw "$Name must be a canonical IPv4 literal"
    }
}

if ($Port -notmatch '^COM[0-9]{1,3}$') {
    throw 'Port must be a COM port name such as COM3'
}
if ($Filename -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$' -or
    [IO.Path]::GetFileName($Filename) -cne $Filename) {
    throw 'Filename must be one safe basename'
}
Assert-IPv4Literal 'ServerIp' $ServerIp
Assert-IPv4Literal 'ClientIp' $ClientIp
if ($SshHost -notmatch '^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$') {
    throw 'SshHost contains unsafe characters'
}
if ($LoadAddress -notmatch '^0x[0-9A-Fa-f]{1,8}$') {
    throw 'LoadAddress must be a 32-bit hexadecimal literal'
}

$SshHost = if ([string]::IsNullOrWhiteSpace($SshHost)) { $ClientIp } else { $SshHost }
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$image = Join-Path $root "work\tftp\omvl\$Filename"
if (-not (Test-Path -LiteralPath $image -PathType Leaf)) {
    throw "Missing TFTP image: $image"
}
$imageSize = (Get-Item -LiteralPath $image).Length
if ($imageSize -le 0 -or $imageSize -gt 0x7a0000) {
    throw "Image outside one slot: $imageSize bytes"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $root "outputs\uart-live\ramssh-cycle-$stamp.log"
function New-UartPort {
    $instance = [IO.Ports.SerialPort]::new(
        $Port, 115200, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
    $instance.Handshake = [IO.Ports.Handshake]::None
    $instance.DtrEnable = $false
    $instance.RtsEnable = $false
    $instance.ReadTimeout = 100
    $instance.WriteTimeout = 500
    return $instance
}

$serial = New-UartPort
$writer = [IO.StreamWriter]::new(
    [IO.File]::Open($logPath, [IO.FileMode]::Create,
        [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite),
    [Text.UTF8Encoding]::new($false))
$writer.AutoFlush = $true
$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$tail = ""
$uartReconnects = 0

function Reopen-Uart {
    try {
        if ($script:serial -and $script:serial.IsOpen) { $script:serial.Close() }
    } catch {}
    try { if ($script:serial) { $script:serial.Dispose() } } catch {}

    $announced = $false
    while ([DateTime]::UtcNow -lt $script:deadline) {
        if (-not $announced) {
            Write-Host "`nRAMSSH_UART_RECONNECT_WAIT port=$Port"
            $script:writer.Write("`r`nRAMSSH_UART_RECONNECT_WAIT port=$Port`r`n")
            $announced = $true
        }
        if ([IO.Ports.SerialPort]::GetPortNames() -contains $Port) {
            try {
                $script:serial = New-UartPort
                $script:serial.Open()
                $script:uartReconnects++
                Write-Host "RAMSSH_UART_RECONNECTED port=$Port count=$script:uartReconnects"
                $script:writer.Write("RAMSSH_UART_RECONNECTED port=$Port count=$script:uartReconnects`r`n")
                return
            } catch {
                try { $script:serial.Dispose() } catch {}
            }
        }
        Start-Sleep -Milliseconds 100
    }
    throw "UART $Port did not re-enumerate before timeout"
}

function Read-Uart {
    try {
        if (-not $script:serial.IsOpen) { Reopen-Uart }
        $chunk = $script:serial.ReadExisting()
    } catch [System.InvalidOperationException], [System.IO.IOException], [System.UnauthorizedAccessException] {
        Reopen-Uart
        return ""
    }
    if ($chunk) {
        $script:writer.Write($chunk)
        Write-Host -NoNewline $chunk
        $script:tail += $chunk
        if ($script:tail.Length -gt 262144) {
            $script:tail = $script:tail.Substring($script:tail.Length - 262144)
        }
    }
    return $chunk
}

function Wait-Uart([string]$Pattern, [string]$Stage, [int]$Seconds = 60) {
    $localDeadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $localDeadline -and
           [DateTime]::UtcNow -lt $script:deadline) {
        [void](Read-Uart)
        if ($script:tail -match $Pattern) {
            Write-Host "`nRAMSSH_CYCLE_STAGE_PASS=$Stage"
            return
        }
        Start-Sleep -Milliseconds 10
    }
    throw "Timeout waiting for $Stage ($Pattern)"
}

function Send-Uart([string]$Command) {
    $visibleCommand = if ($Command -match '^seed_') {
        'seed_<redacted>'
    } else {
        $Command
    }
    Write-Host "`n[Codex -> UART] $visibleCommand"
    $script:writer.Write("`r`n[Codex -> UART] $visibleCommand`r`n")
    $script:serial.Write($Command + "`r")
}

function Wait-Prompt([string]$Stage, [int]$Seconds = 60) {
    Wait-Uart 'topaz>\s*$' $Stage $Seconds
}

function Send-AutobootStopBurst {
    # Console ownership changes around BootExtension/U-Boot can lose one byte.
    # A short whitespace burst is harmless at the prompt and reliably stops
    # the HGW500 A2 countdown.
    foreach ($attempt in 1..4) {
        $script:serial.Write(" ")
        Start-Sleep -Milliseconds 40
    }
}

function Exit-ZhalBootExtension {
    $escaped = $false
    for ($attempt = 1; $attempt -le 3 -and -not $escaped; $attempt++) {
        $script:tail = ""
        $script:serial.Write([string][char]0x15) # Ctrl-U clears pending input.
        $script:serial.Write([string][char]0x08) # Remove the autoboot stop key.
        Start-Sleep -Milliseconds 80
        Send-Uart 'ATGU'
        $deadline = [DateTime]::UtcNow.AddSeconds(8)
        while ([DateTime]::UtcNow -lt $deadline) {
            [void](Read-Uart)
            if ($script:tail -match 'Hit any key to exit') {
                $escaped = $true
                break
            }
            if ($script:tail -match 'command not found') { break }
            Start-Sleep -Milliseconds 10
        }
    }
    if (-not $escaped) {
        throw "ZHAL rejected ATGU after three cleared-line attempts"
    }
    Write-Host "`nRAMSSH_CYCLE_STAGE_PASS=bootextension_exit"

    # Exact BootExtension sequence: ATGU, first space exits the extension,
    # second space stops the fresh U-Boot autoboot countdown.
    Send-AutobootStopBurst
    $script:tail = ""
    Wait-Uart 'Hit any key to stop autoboot' 'post_bootextension_autoboot' 30
    Send-AutobootStopBurst
    $script:tail = ""
    Wait-Prompt 'topaz_after_atgu' 30
}

try {
    try {
        $serial.Open()
    } catch [System.IO.IOException], [System.UnauthorizedAccessException], [System.InvalidOperationException] {
        Reopen-Uart
    }
    Write-Host "RAMSSH_CYCLE_START image=$Filename bytes=$imageSize log=$logPath"

    # A previous recovery attempt can leave BootExtension already waiting at
    # ZHAL>. Detect that state before sending BREAK/SysRq or waiting for a
    # countdown that will never appear.
    $promptReady = $false
    # Prompts are not periodically reprinted. Clear any partial command left
    # by an earlier autoboot stop (for example `b `), then press Enter so an
    # already-open ZHAL/topaz shell emits its prompt for this new capture.
    $serial.Write([string][char]0x15) # Ctrl-U
    $serial.Write("`r")
    Start-Sleep -Milliseconds 120
    $preflightDeadline = [DateTime]::UtcNow.AddSeconds(2)
    while ([DateTime]::UtcNow -lt $preflightDeadline) {
        [void](Read-Uart)
        if ($tail -match 'topaz>\s*$') {
            $promptReady = $true
            break
        }
        if ($tail -match 'ZHAL>\s*$') {
            Exit-ZhalBootExtension
            $promptReady = $true
            break
        }
        Start-Sleep -Milliseconds 10
    }

    if (-not $promptReady -and -not $SkipReboot) {
        if ($UseSshReboot) {
            $execTool = Join-Path $PSScriptRoot 'ramssh_exec.py'
            # The Windows PowerShell/.NET runtime on the lab host does not
            # expose ProcessStartInfo.ArgumentList.  The remote command forks
            # reboot before SSH closes, so a short synchronous launcher is both
            # compatible and deterministic here.
            & python.exe $execTool `
                'sync; (sleep 1; reboot -f) >/dev/null 2>&1 &' `
                '--host' $SshHost '--timeout' '10'
            if ($LASTEXITCODE -ne 0) {
                throw "SSH reboot request failed for $SshHost"
            }
            Write-Host "RAMSSH_SSH_REBOOT_REQUESTED host=$SshHost"
        } else {
            # Linux serial SysRq: BREAK followed by b. This is RAM-only and
            # does not alter the boot environment or flash contents.
            $serial.BreakState = $true
            Start-Sleep -Milliseconds 600
            $serial.BreakState = $false
            Start-Sleep -Milliseconds 150
            $serial.Write("b")
        }
    }
    if (-not $promptReady) {
        Wait-Uart 'Hit any key to stop autoboot' 'autoboot_countdown' $AutobootWaitSeconds
        Send-AutobootStopBurst

        # Engineering BootExtension may interpose ZHAL before the U-Boot prompt.
        $zhalDeadline = [DateTime]::UtcNow.AddSeconds(30)
        while ([DateTime]::UtcNow -lt $zhalDeadline) {
            [void](Read-Uart)
            if ($tail -match 'topaz>\s*$') { break }
            if ($tail -match 'ZHAL>\s*$') {
            # The space used to stop autoboot can survive as pending ZHAL
            # input. Clear that line before ATGU and retry only on an explicit
            # parser rejection; otherwise a leading space becomes a false
            # "command not found" and wastes the recovery window.
            $zhalEscaped = $false
            for ($attempt = 1; $attempt -le 3 -and -not $zhalEscaped; $attempt++) {
                $tail = ""
                $serial.Write([string][char]0x15) # Ctrl-U: clear input line
                $serial.Write([string][char]0x08) # Backspace: remove stop key
                Start-Sleep -Milliseconds 80
                Send-Uart 'ATGU'
                $atguDeadline = [DateTime]::UtcNow.AddSeconds(8)
                while ([DateTime]::UtcNow -lt $atguDeadline) {
                    [void](Read-Uart)
                    if ($tail -match 'Hit any key to exit') {
                        $zhalEscaped = $true
                        break
                    }
                    if ($tail -match 'command not found') { break }
                    Start-Sleep -Milliseconds 10
                }
            }
            if (-not $zhalEscaped) {
                throw "ZHAL rejected ATGU after three cleared-line attempts"
            }
            Write-Host "`nRAMSSH_CYCLE_STAGE_PASS=bootextension_exit"
            Send-AutobootStopBurst
            $tail = ""
            Wait-Uart 'Hit any key to stop autoboot' `
                'post_bootextension_autoboot' 30
            $serial.Write(" ")
                break
            }
            Start-Sleep -Milliseconds 10
        }
    }
    Wait-Prompt 'topaz_prompt' 45

    foreach ($command in @(
        "setenv ipaddr $ClientIp",
        "setenv serverip $ServerIp"
    )) {
        $tail = ""
        Send-Uart $command
        Wait-Prompt $command 20
    }

    $tail = ""
    Send-Uart "tftpboot $LoadAddress $Filename"
    Wait-Uart "Bytes transferred = $imageSize" 'tftp_size' 180
    Wait-Prompt 'tftp_complete' 30

    $tail = ""
    Send-Uart "iminfo $LoadAddress"
    Wait-Uart 'Verifying Checksum \.\.\. OK' 'iminfo_crc' 45
    Wait-Prompt 'iminfo_complete' 20

    if (-not $AutonomousEntropy) {
        # Prepare fresh host entropy before bootm so no human or post-prompt
        # generation latency is involved. The seed value is never written to
        # the transcript; only the 256-bit readiness marker is emitted.
        $seed = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
            (Join-Path $PSScriptRoot 'new_ramssh_seed.ps1')
        if ($seed -notmatch '^seed_[0-9a-f]{64}$') {
            throw "Invalid generated entropy seed"
        }
        Write-Host "RAMSSH_HOST_ENTROPY_PREPARED bits=256"
    }

    $tail = ""
    Send-Uart "bootm $LoadAddress"
    # Kernel printk and userspace console writes can interleave at byte level.
    # Accept the unique marker even when bounded OMEMAC text splits it.
    if ($AutonomousEntropy) {
        Wait-Uart $AutonomousEntropyPattern 'autonomous_entropy' 180
        Write-Host "`nRAMSSH_CYCLE_STAGE_PASS=autonomous_entropy"
    } else {
        Wait-Uart $EntropyPromptPattern 'entropy_prompt' 120
        Send-Uart $seed
        Wait-Uart $EntropyOkPattern 'entropy_added' 30
    }
    try {
        Wait-Uart $ReadyPattern 'userspace_ready_uart' $ReadyUartWaitSeconds
        Write-Host "`nRAMSSH_CYCLE_UART_READY_PASS=1"
    } catch {
        # S90-ready can have written /run/openmitrastar/boot-state while
        # /dev/console is unavailable or no longer routed to UART.  Do not
        # confuse a missing presentation marker with a failed product boot;
        # the authenticated SSH/product-state gate below is authoritative.
        Write-Host "`nRAMSSH_CYCLE_UART_READY_FALLBACK=ssh-product-state"
    }
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
    $writer.Dispose()
}

Start-Sleep -Seconds 2
& python (Join-Path $PSScriptRoot 'verify_ramssh.py') --host $SshHost --timeout 45
if ($LASTEXITCODE -ne 0) {
    throw "RAMSSH authenticated SSH gate failed"
}
Write-Host "RAMSSH_CYCLE_SSH_PASS=1"

& python (Join-Path $PSScriptRoot 'verify_product_ready.py') `
    --host $SshHost --timeout 45
if ($LASTEXITCODE -ne 0) {
    throw "Authenticated product-state gate failed"
}
Write-Host "RAMSSH_CYCLE_PRODUCT_STATE_PASS=1"
Write-Host "RAMSSH_CYCLE_BOOT_PASS=1"
