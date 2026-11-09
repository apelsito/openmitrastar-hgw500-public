param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [ValidateRange(60, 21600)]
    [int]$BootWaitSeconds = 600,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [string]$CurrentLiveCrc32 = "ec3dd18b",
    [switch]$SysRqRebootFirst,
    [switch]$SshRebootFirst,
    [ValidateRange(5, 120)]
    [int]$SysRqRetrySeconds = 15,
    [switch]$ConsoleRebootAssist,
    [ValidateRange(5, 120)]
    [int]$ConsoleRebootRetrySeconds = 20,
    [ValidateRange(0, 21600)]
    [int]$NoRxAbortSeconds = 30,
    [switch]$AllowBlindAutobreak,
    [ValidateRange(0, 300)]
    [int]$BlindAtguAfterNoRxSeconds = 0,
    [switch]$AllowNoRxRebootAssist,
    [switch]$PulseResetLinesFirst,
    [switch]$KeepExistingTftp
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RequiredAck = if ($env:OM_Q3_FLASH_ACK) { $env:OM_Q3_FLASH_ACK } else { "OPENMITRASTAR_Q3_F45_RADIO5_POWERSELECT_NONFATAL_OPENLAB_AUTOSTART_MTD4_FLASH_18F114D0" }
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $Root "outputs\uart-live\q3-f45-radio5-powerselect-nonfatal-openlab-autostart-autoboot-atgu-flash-$stamp.log"
New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($logPath)) | Out-Null

if (-not $Execute) {
    throw "Refusing to arm flash without -Execute and exact -Ack. This script is intentionally not a dry-run UART grabber."
}
if ($Ack -ne $RequiredAck) {
    throw "Exact acknowledgement required: $RequiredAck"
}
if ($CurrentLiveCrc32 -notmatch '^[0-9a-fA-F]{8}$') {
    throw "CurrentLiveCrc32 must be 8 hex characters"
}

function Stop-WorkspaceTftpServers {
    if ($KeepExistingTftp) { return }
    $owners = @(Get-NetUDPEndpoint -LocalPort 69 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($pid in $owners) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pid" -ErrorAction SilentlyContinue
        if (-not $proc -or -not $proc.CommandLine) { continue }
        $cmd = [string]$proc.CommandLine
        $isWorkspaceTftp = (
            $cmd -like "*MitraStar*" -and
            ($cmd -like "*tftp_serve_once.py*" -or $cmd -like "*tiny_tftp_server.py*" -or $cmd -like "*work*tftp*omvl*")
        )
        if ($isWorkspaceTftp) {
            Stop-Process -Id $pid -Force -ErrorAction Stop
            Write-Host "OMQ3_F45_AUTOBREAK_TFTP_STOPPED pid=$pid"
        }
    }
}

function Get-PowerShellHostPath {
    $current = (Get-Process -Id $PID -ErrorAction SilentlyContinue).Path
    if ($current) { return $current }
    $cmd = Get-Command pwsh.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return "powershell.exe"
}

function Wait-TopazPrompt {
    $serial = [IO.Ports.SerialPort]::new(
        $Port, 115200, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
    $serial.Handshake = [IO.Ports.Handshake]::None
    $serial.DtrEnable = $false
    $serial.RtsEnable = $false
    $serial.ReadTimeout = 100
    $serial.WriteTimeout = 500
    $writer = [IO.StreamWriter]::new(
        [IO.File]::Open($logPath, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite),
        [Text.UTF8Encoding]::new($false))
    $writer.AutoFlush = $true
    $script:omTail = ""
    $spaceCount = 0
    $atguCount = 0
    $lastProbeAt = [DateTime]::MinValue
    $lastSpaceAt = [DateTime]::MinValue
    $lastBlindSpaceAt = [DateTime]::MinValue
    $script:omLastBlindAtguAt = [DateTime]::MinValue
    $script:omLastSysRqAt = [DateTime]::MinValue
    $script:omLastConsoleRebootAt = [DateTime]::MinValue
    $script:omRxBytes = [int64]0
    $consoleRebootCount = 0
    $openedAt = [DateTime]::MinValue

    function Append-Uart([string]$chunk) {
        if (-not $chunk) { return }
        $script:omRxBytes += [Text.Encoding]::ASCII.GetByteCount($chunk)
        $writer.Write($chunk)
        Write-Host -NoNewline $chunk
        $script:omTail += $chunk
        if ($script:omTail.Length -gt 32768) {
            $script:omTail = $script:omTail.Substring($script:omTail.Length - 32768)
        }
    }

    function Send-SysRqReboot([string]$Reason) {
        $serial.BreakState = $true
        Start-Sleep -Milliseconds 700
        $serial.BreakState = $false
        Start-Sleep -Milliseconds 120
        $serial.Write("b")
        $script:omLastSysRqAt = [DateTime]::UtcNow
        Write-Host "`nOMQ3_F45_AUTOBREAK_SYSRQ_REBOOT_SENT reason=$Reason"
    }

    function Send-SshReboot([string]$Reason) {
        $sshScript = Join-Path $PSScriptRoot "ssh_openmitrastar_510.ps1"
        $keyPath = if ($env:OM_Q3_FLASH_SSH_KEY) { $env:OM_Q3_FLASH_SSH_KEY } else { "$env:USERPROFILE\.ssh\id_ed25519" }
        $command = "& '$sshScript' -HostAddress '$HostAddress' -User root -KeyPath '$keyPath' -KnownHostsPath '.codex_tmp\router_known_hosts_flash' -RemoteCommand 'sync; reboot -f'"
        $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command)
        Start-Process -FilePath (Get-PowerShellHostPath) -WindowStyle Hidden -ArgumentList $args | Out-Null
        Write-Host "`nOMQ3_F45_AUTOBREAK_SSH_REBOOT_SENT reason=$Reason host=$HostAddress"
    }

    function Send-ConsoleRebootProbe([string]$Reason) {
        $serial.Write([string][char]0x03)
        Start-Sleep -Milliseconds 80
        $serial.Write("`r")
        Start-Sleep -Milliseconds 80
        $serial.Write("root`r")
        Start-Sleep -Milliseconds 120
        $serial.Write("echo b > /proc/sysrq-trigger`r")
        Start-Sleep -Milliseconds 120
        $serial.Write("reboot -f`r")
        $script:omLastConsoleRebootAt = [DateTime]::UtcNow
        $script:omTail = ""
        Write-Host "`nOMQ3_F45_AUTOBREAK_CONSOLE_REBOOT_PROBE_SENT reason=$Reason"
    }

    function Exit-ZhalBootExtension {
        $escaped = $false
        for ($attempt = 1; $attempt -le 3 -and -not $escaped; $attempt++) {
            $script:omTail = ""
            $serial.Write([string][char]0x15)
            $serial.Write([string][char]0x08)
            Start-Sleep -Milliseconds 80
            $serial.Write("ATGU`r")
            $atguCount += 1
            Write-Host "`nOMQ3_F45_AUTOBREAK_ATGU_SENT=$atguCount attempt=$attempt"
            $deadline = [DateTime]::UtcNow.AddSeconds(8)
            while ([DateTime]::UtcNow -lt $deadline) {
                Append-Uart $serial.ReadExisting()
                if ($script:omTail -match 'Hit any key to exit') { $escaped = $true; break }
                if ($script:omTail -match 'command not found|Unknown command') { break }
                Start-Sleep -Milliseconds 10
            }
        }
        if (-not $escaped) { throw "ZHAL rejected ATGU after three cleared-line attempts" }

        $serial.Write(" ")
        $spaceCount += 1
        Write-Host "`nOMQ3_F45_AUTOBREAK_SPACE_SENT=$spaceCount stage=exit_bootextension"
        $script:omTail = ""
        $deadline = [DateTime]::UtcNow.AddSeconds(30)
        while ([DateTime]::UtcNow -lt $deadline) {
            Append-Uart $serial.ReadExisting()
            if ($script:omTail -match 'Hit any key to stop autoboot') { break }
            Start-Sleep -Milliseconds 10
        }
        if ($script:omTail -notmatch 'Hit any key to stop autoboot') {
            throw "Timed out waiting for post-BootExtension autoboot countdown"
        }

        $serial.Write(" ")
        $spaceCount += 1
        Write-Host "`nOMQ3_F45_AUTOBREAK_SPACE_SENT=$spaceCount stage=stop_topaz_autoboot"
        $script:omTail = ""
        $deadline = [DateTime]::UtcNow.AddSeconds(45)
        while ([DateTime]::UtcNow -lt $deadline) {
            Append-Uart $serial.ReadExisting()
            if ($script:omTail -match 'topaz>\s*$') {
                Write-Host "`nOMQ3_F45_AUTOBREAK_TOPAZ_READY=1 spaces=$spaceCount atgu=$atguCount log=$logPath"
                return
            }
            Start-Sleep -Milliseconds 10
        }
        throw "Timed out waiting for topaz> after BootExtension exit"
    }

    function Send-BlindAtguSequence {
        $serial.Write(" ")
        $parentSpaceCount = [int](Get-Variable -Name spaceCount -Scope 1).Value + 1
        Set-Variable -Name spaceCount -Scope 1 -Value $parentSpaceCount
        Start-Sleep -Milliseconds 120
        $serial.Write([string][char]0x15)
        $serial.Write([string][char]0x08)
        Start-Sleep -Milliseconds 80
        $serial.Write("ATGU`r")
        $parentAtguCount = [int](Get-Variable -Name atguCount -Scope 1).Value + 1
        Set-Variable -Name atguCount -Scope 1 -Value $parentAtguCount
        Write-Host "`nOMQ3_F45_AUTOBREAK_BLIND_ATGU_SENT=$parentAtguCount no_rx_seconds=$BlindAtguAfterNoRxSeconds"
        Start-Sleep -Milliseconds 250
        $serial.Write(" ")
        $parentSpaceCount += 1
        Set-Variable -Name spaceCount -Scope 1 -Value $parentSpaceCount
        Write-Host "`nOMQ3_F45_AUTOBREAK_BLIND_ATGU_SPACE_SENT=$parentSpaceCount stage=exit_bootextension"
        Start-Sleep -Milliseconds 250
        $serial.Write(" ")
        $parentSpaceCount += 1
        Set-Variable -Name spaceCount -Scope 1 -Value $parentSpaceCount
        Write-Host "`nOMQ3_F45_AUTOBREAK_BLIND_ATGU_SPACE_SENT=$parentSpaceCount stage=stop_topaz_autoboot"
        $script:omTail = ""
        $now = [DateTime]::UtcNow
        Set-Variable -Name lastBlindSpaceAt -Scope 1 -Value $now
        Set-Variable -Name lastSpaceAt -Scope 1 -Value $now
        Set-Variable -Name lastProbeAt -Scope 1 -Value $now
        $script:omLastBlindAtguAt = [DateTime]::UtcNow
    }

    try {
        $serial.Open()
        $openedAt = [DateTime]::UtcNow
        $serial.DiscardInBuffer()
        Write-Host "OMQ3_F45_AUTOBREAK_WAIT_START port=$Port log=$logPath"
        if ($PulseResetLinesFirst) {
            $serial.DtrEnable = $true
            $serial.RtsEnable = $true
            Start-Sleep -Milliseconds 250
            $serial.DtrEnable = $false
            $serial.RtsEnable = $false
            Start-Sleep -Milliseconds 250
            Write-Host "`nOMQ3_F45_AUTOBREAK_UART_RESET_LINES_PULSED=1"
        }
        if ($SysRqRebootFirst -and $AllowNoRxRebootAssist) {
            Send-SysRqReboot "initial"
        }
        if ($SshRebootFirst) {
            Send-SshReboot "initial"
        }
        $deadline = [DateTime]::UtcNow.AddSeconds($BootWaitSeconds)
        while ([DateTime]::UtcNow -lt $deadline) {
            Append-Uart $serial.ReadExisting()

            if ($NoRxAbortSeconds -gt 0 -and
                $script:omRxBytes -eq 0 -and
                ([DateTime]::UtcNow - $openedAt).TotalSeconds -ge $NoRxAbortSeconds) {
                Write-Host "`nOMQ3_F45_AUTOBREAK_UART_RX_SILENT_ZERO_BYTES seconds=$NoRxAbortSeconds log=$logPath"
                throw "UART_RX_SILENT_ZERO_BYTES"
            }

            if ($script:omTail -match 'topaz>\s*$') {
                Write-Host "`nOMQ3_F45_AUTOBREAK_TOPAZ_READY=1 spaces=$spaceCount atgu=$atguCount log=$logPath"
                return
            }

            if ($AllowBlindAutobreak -and
                $BlindAtguAfterNoRxSeconds -gt 0 -and
                $script:omRxBytes -eq 0 -and
                ([DateTime]::UtcNow - $openedAt).TotalSeconds -ge $BlindAtguAfterNoRxSeconds -and
                ([DateTime]::UtcNow - $script:omLastBlindAtguAt).TotalSeconds -ge $BlindAtguAfterNoRxSeconds) {
                Send-BlindAtguSequence
                Start-Sleep -Milliseconds 250
                continue
            }

            $spacePrompt = $script:omTail -match 'Hit any key (to stop autoboot|to exit)'
            $bootbaseSeen = $script:omTail -match 'Bootbase|ZyNOS|ZLD|ZHAL|=>'
            $blindSpaceDue = ([DateTime]::UtcNow - $lastBlindSpaceAt).TotalMilliseconds -ge 250
            if ($AllowBlindAutobreak -and -not $bootbaseSeen -and -not $spacePrompt -and $blindSpaceDue) {
                $serial.Write(" ")
                $lastBlindSpaceAt = [DateTime]::UtcNow
                $spaceCount += 1
                if (($spaceCount % 20) -eq 0) {
                    Write-Host "`nOMQ3_F45_AUTOBREAK_BLIND_SPACE_SENT=$spaceCount"
                }
            }
            if ($ConsoleRebootAssist -and $script:omRxBytes -gt 0 -and -not $bootbaseSeen -and
                ([DateTime]::UtcNow - $script:omLastConsoleRebootAt).TotalSeconds -ge $ConsoleRebootRetrySeconds) {
                $consoleRebootCount += 1
                Send-ConsoleRebootProbe "retry$consoleRebootCount"
                Start-Sleep -Milliseconds 250
                continue
            }
            if ($SysRqRebootFirst -and $script:omRxBytes -gt 0 -and -not $bootbaseSeen -and
                ([DateTime]::UtcNow - $script:omLastSysRqAt).TotalSeconds -ge $SysRqRetrySeconds) {
                Send-SysRqReboot "retry"
                Start-Sleep -Milliseconds 250
                continue
            }
            $spaceDue = ([DateTime]::UtcNow - $lastSpaceAt).TotalMilliseconds -ge 120
            if ($spacePrompt -or ($bootbaseSeen -and $spaceDue)) {
                $serial.Write(" ")
                Start-Sleep -Milliseconds 40
                if ($spacePrompt) {
                    $serial.Write("`r")
                }
                $lastSpaceAt = [DateTime]::UtcNow
                $spaceCount += 1
                Write-Host "`nOMQ3_F45_AUTOBREAK_SPACE_SENT=$spaceCount prompt=$spacePrompt bootbase=$bootbaseSeen"
                if ($spacePrompt) {
                    $script:omTail = ""
                    continue
                }
            }

            if ($script:omTail -match 'ZHAL>\s*$') {
                Exit-ZhalBootExtension
                return
            }

            if (([DateTime]::UtcNow - $lastProbeAt).TotalSeconds -ge 3) {
                $serial.Write("`r")
                $lastProbeAt = [DateTime]::UtcNow
            }
            Start-Sleep -Milliseconds 20
        }
        throw "Timed out waiting for topaz> after $BootWaitSeconds seconds"
    } finally {
        if ($serial.IsOpen) { $serial.Close() }
        $serial.Dispose()
        $writer.Dispose()
    }
}

Stop-WorkspaceTftpServers
Wait-TopazPrompt

$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $CurrentLiveCrc32.ToLowerInvariant()
$flashOutput = & python (Join-Path $Root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py") `
    --execute `
    --ack $RequiredAck `
    --skip-reboot `
    --port $Port `
    --server-ip $ServerIp `
    --client-ip $ClientIp `
    --host $HostAddress `
    --timeout $FlashTimeoutSeconds 2>&1
$flashRc = $LASTEXITCODE
$flashOutput | ForEach-Object { Write-Host $_ }

$effectiveBuildDir = if ($env:OM_Q3_FLASH_BUILD_DIR) {
    [IO.Path]::GetFullPath($env:OM_Q3_FLASH_BUILD_DIR)
} else {
    Join-Path $Root "work\mission-state\q3-f45-radio5-powerselect-nonfatal-openlab-autostart\build"
}
$latest = Get-ChildItem -LiteralPath $effectiveBuildDir -Directory |
    Where-Object { $_.Name -like "flash-one-shot-*" } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if ($latest) {
    $uartLog = Join-Path $latest.FullName "bootbase-flash-uart.log"
    $backendLog = Join-Path $latest.FullName "backend.log"
    Write-Host "OMQ3_F45_FLASH_EVIDENCE_DIR=$($latest.FullName)"
    if (Test-Path -LiteralPath $uartLog) {
        Select-String -LiteralPath $uartLog -Pattern @(
            "OMQ3_F45_RADIO5_POWERSELECT_NONFATAL_OPENLAB_MTD4_PREWRITE_PHYSICAL_RECHECK_PASS",
            "spi_flash erase",
            "spi_flash write",
            "OMQ3_F45_RADIO5_POWERSELECT_NONFATAL_OPENLAB_PROTECTED_PARTITION_CRC_PASS",
            "OMQ3_F45_RADIO5_POWERSELECT_NONFATAL_OPENLAB_MTD4_BOOTBASE_READBACK_PASS",
            "Linux version 5\.10\.260-openmitrastar-radiohw",
            "OMNETWORK_READY",
            "OMSSH_READY",
            "OMQ3_F45_RADIO5_POWERSELECT_NONFATAL_OPENLAB_PRODUCT_READY_OPTIONAL_TIMEOUT",
            "OMQ3_F45_RADIO5_POWERSELECT_NONFATAL_OPENLAB_MTD4_FLASH_AND_READBACK_PASS",
            "Exception:",
            "UART timeout"
        ) | ForEach-Object { Write-Host ("OMQ3_F45_FLASH_MARKER " + $_.Line.Trim()) }
    }
    if ($flashRc -ne 0 -and (Test-Path -LiteralPath $backendLog)) {
        Write-Host "OMQ3_F45_FLASH_BACKEND_TAIL_BEGIN"
        Get-Content -LiteralPath $backendLog -Tail 40 | ForEach-Object { Write-Host $_ }
        Write-Host "OMQ3_F45_FLASH_BACKEND_TAIL_END"
    }
}

exit $flashRc

