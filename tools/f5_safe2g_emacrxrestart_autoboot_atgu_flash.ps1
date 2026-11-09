param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [ValidateRange(60, 1200)]
    [int]$BootWaitSeconds = 600,
    [ValidateRange(600, 1800)]
    [int]$FlashTimeoutSeconds = 900,
    [string]$CurrentLiveCrc32 = "05674ac6",
    [switch]$SysRqRebootFirst,
    [ValidateRange(5, 120)]
    [int]$SysRqRetrySeconds = 15,
    [switch]$ConsoleRebootAssist,
    [ValidateRange(5, 120)]
    [int]$ConsoleRebootRetrySeconds = 20,
    [switch]$PulseResetLinesFirst,
    [switch]$KeepExistingTftp
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RequiredAck = "OPENMITRASTAR_F5_SAFE2G_EMACRXRESTART_MTD4_FLASH_F38F5B74"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $Root "outputs\uart-live\f5-safe2g-emacrxrestart-autoboot-atgu-flash-$stamp.log"
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
            Write-Host "OMF5_AUTOBREAK_TFTP_STOPPED pid=$pid"
        }
    }
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
    $script:omLastSysRqAt = [DateTime]::MinValue
    $script:omLastConsoleRebootAt = [DateTime]::MinValue
    $consoleRebootCount = 0

    function Append-Uart([string]$chunk) {
        if (-not $chunk) { return }
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
        Write-Host "`nOMF5_AUTOBREAK_SYSRQ_REBOOT_SENT reason=$Reason"
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
        Write-Host "`nOMF5_AUTOBREAK_CONSOLE_REBOOT_PROBE_SENT reason=$Reason"
    }

    try {
        $serial.Open()
        $serial.DiscardInBuffer()
        Write-Host "OMF5_AUTOBREAK_WAIT_START port=$Port log=$logPath"
        if ($PulseResetLinesFirst) {
            $serial.DtrEnable = $true
            $serial.RtsEnable = $true
            Start-Sleep -Milliseconds 250
            $serial.DtrEnable = $false
            $serial.RtsEnable = $false
            Start-Sleep -Milliseconds 250
            Write-Host "`nOMF5_AUTOBREAK_UART_RESET_LINES_PULSED=1"
        }
        if ($SysRqRebootFirst) {
            Send-SysRqReboot "initial"
        }
        $deadline = [DateTime]::UtcNow.AddSeconds($BootWaitSeconds)
        while ([DateTime]::UtcNow -lt $deadline) {
            Append-Uart $serial.ReadExisting()

            if ($script:omTail -match 'topaz>\s*$') {
                Write-Host "`nOMF5_AUTOBREAK_TOPAZ_READY=1 spaces=$spaceCount atgu=$atguCount log=$logPath"
                return
            }

            $spacePrompt = $script:omTail -match 'Hit any key (to stop autoboot|to exit)'
            $bootbaseSeen = $script:omTail -match 'Bootbase|ZyNOS|ZLD|ZHAL|=>'
            if ($ConsoleRebootAssist -and -not $bootbaseSeen -and
                ([DateTime]::UtcNow - $script:omLastConsoleRebootAt).TotalSeconds -ge $ConsoleRebootRetrySeconds) {
                $consoleRebootCount += 1
                Send-ConsoleRebootProbe "retry$consoleRebootCount"
                Start-Sleep -Milliseconds 250
                continue
            }
            if ($SysRqRebootFirst -and -not $bootbaseSeen -and
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
                Write-Host "`nOMF5_AUTOBREAK_SPACE_SENT=$spaceCount prompt=$spacePrompt bootbase=$bootbaseSeen"
                if ($spacePrompt) {
                    $script:omTail = ""
                    continue
                }
            }

            if ($script:omTail -match 'ZHAL>\s*$') {
                $serial.Write([string][char]0x15)
                $serial.Write([string][char]0x08)
                Start-Sleep -Milliseconds 80
                $serial.Write("ATGU`r")
                $atguCount += 1
                $script:omTail = ""
                Write-Host "`nOMF5_AUTOBREAK_ATGU_SENT=$atguCount"
                continue
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

$env:OM_F5_EXPECTED_CURRENT_LIVE_CRC32 = $CurrentLiveCrc32.ToLowerInvariant()
$env:OM_F5_ALLOW_LIVE_SLOT_DRIFT_CRC_ONLY = "1"
$flashOutput = & python (Join-Path $Root "tools\run_f5_safe2g_emacrxrestart_mtd4_flash_one_shot.py") `
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

$latest = Get-ChildItem -LiteralPath (Join-Path $Root "work\mission-state\f5-safe2g-emacrxrestart-gzipinit\build") -Directory |
    Where-Object { $_.Name -like "flash-one-shot-*" } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if ($latest) {
    $uartLog = Join-Path $latest.FullName "bootbase-flash-uart.log"
    $backendLog = Join-Path $latest.FullName "backend.log"
    Write-Host "OMF5_FLASH_EVIDENCE_DIR=$($latest.FullName)"
    if (Test-Path -LiteralPath $uartLog) {
        Select-String -LiteralPath $uartLog -Pattern @(
            "OMF5_AUTONOMOUS_MTD4_PREWRITE_PHYSICAL_RECHECK_PASS",
            "spi_flash erase",
            "spi_flash write",
            "OMF5_AUTONOMOUS_PROTECTED_PARTITION_CRC_PASS",
            "OMF5_AUTONOMOUS_MTD4_BOOTBASE_READBACK_PASS",
            "Linux version 5\.10\.260-openmitrastar-radiohw",
            "OMNETWORK_READY",
            "OMSSH_READY",
            "OMF5_AUTONOMOUS_PRODUCT_READY_OPTIONAL_TIMEOUT",
            "OMF5_AUTONOMOUS_MTD4_FLASH_AND_READBACK_PASS",
            "Exception:",
            "UART timeout"
        ) | ForEach-Object { Write-Host ("OMF5_FLASH_MARKER " + $_.Line.Trim()) }
    }
    if ($flashRc -ne 0 -and (Test-Path -LiteralPath $backendLog)) {
        Write-Host "OMF5_FLASH_BACKEND_TAIL_BEGIN"
        Get-Content -LiteralPath $backendLog -Tail 40 | ForEach-Object { Write-Host $_ }
        Write-Host "OMF5_FLASH_BACKEND_TAIL_END"
    }
}

exit $flashRc

