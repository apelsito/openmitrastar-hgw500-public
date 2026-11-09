param(
    [string]$Port = "COM3",
    [string]$Filename = "linux510-emac-ddr-sysrq-webformat.bin",
    [string]$TftpRoot = "work\tftp\omvl",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.200",
    [string]$LoadAddress = "0x83000000",
    [int]$CaptureSeconds = 210,
    [string]$ReadyPattern = "RAMSSH_SSH_EXEC",
    [switch]$VerifySsh
)

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$image = [IO.Path]::GetFullPath((Join-Path $root (Join-Path $TftpRoot $Filename)))
if (-not (Test-Path -LiteralPath $image -PathType Leaf)) {
    throw "TFTP image not found: $image"
}
$size = (Get-Item -LiteralPath $image).Length
if ($size -le 0 -or $size -gt 0x7a0000) {
    throw "Image size outside one firmware slot: $size"
}
$sha256 = (Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash.ToLowerInvariant()
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logDir = Join-Path $root "outputs\uart-live"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir "linux510-tftp-boot-$stamp.log"

$serial = [IO.Ports.SerialPort]::new(
    $Port, 115200, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
$serial.Handshake = [IO.Ports.Handshake]::None
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 100
$serial.WriteTimeout = 500
$writer = [IO.StreamWriter]::new(
    [IO.File]::Open($logPath, [IO.FileMode]::Create,
        [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite),
    [Text.UTF8Encoding]::new($false))
$writer.AutoFlush = $true

function Invoke-TopazCommand {
    param([string]$Command, [int]$TimeoutSeconds = 120)
    $script:serial.DiscardInBuffer()
    $script:serial.Write($Command + "`r")
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $all = ""
    while ([DateTime]::UtcNow -lt $deadline) {
        $chunk = $script:serial.ReadExisting()
        if ($chunk) {
            $script:writer.Write($chunk)
            Write-Host -NoNewline $chunk
            $all += $chunk
            if ($all -match 'topaz>\s*$') { return $all }
        }
        Start-Sleep -Milliseconds 15
    }
    throw "Timeout after topaz command: $Command"
}

try {
    $serial.Open()
    Write-Host "TFTP_BOOT_PREFLIGHT file=$Filename bytes=$size sha256=$sha256"
    $serial.Write("`r")
    Start-Sleep -Milliseconds 200
    $prompt = $serial.ReadExisting()
    if ($prompt -notmatch 'topaz>') {
        throw "topaz> prompt is required; run recover_to_oem_safety.ps1 -NoBoot first"
    }
    [void](Invoke-TopazCommand "setenv ipaddr $ClientIp" 20)
    [void](Invoke-TopazCommand "setenv serverip $ServerIp" 20)
    $transfer = Invoke-TopazCommand "tftpboot $LoadAddress $Filename" 150
    if ($transfer -notmatch "Bytes transferred = $size") {
        throw "TFTP size verification failed"
    }
    $verified = Invoke-TopazCommand "iminfo $LoadAddress" 45
    if ($verified -notmatch 'Verifying Checksum \.\.\. OK') {
        throw "Bootbase iminfo rejected the staged image"
    }
    Write-Host "TFTP_BOOT_IMAGE_PASS bytes=$size sha256=$sha256"
    $serial.DiscardInBuffer()
    $serial.Write("bootm $LoadAddress`r")
    $deadline = [DateTime]::UtcNow.AddSeconds($CaptureSeconds)
    $bootTail = ""
    $sshReady = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        $chunk = $serial.ReadExisting()
        if ($chunk) {
            $writer.Write($chunk)
            Write-Host -NoNewline $chunk
            $bootTail += $chunk
            if ($bootTail.Length -gt 32768) {
                $bootTail = $bootTail.Substring($bootTail.Length - 32768)
            }
            if ($bootTail -match $ReadyPattern) {
                $sshReady = $true
                Start-Sleep -Seconds 2
                break
            }
        }
        Start-Sleep -Milliseconds 15
    }
    Write-Host "TFTP_BOOT_CAPTURE_COMPLETE ssh_marker=$([int]$sshReady) log=$logPath"
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
    $writer.Dispose()
}

if ($VerifySsh) {
    if (-not $sshReady) {
        throw "UART did not reach readiness pattern '$ReadyPattern'; SSH verification suppressed"
    }
    & python (Join-Path $PSScriptRoot "verify_ramssh.py") --host $ClientIp
    if ($LASTEXITCODE -ne 0) { throw "RAM SSH authenticated gate failed" }
}
