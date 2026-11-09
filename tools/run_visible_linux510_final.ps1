param(
    [string]$Image = "linux510-ssh-multiuser-webformat.bin",
    [string]$LogPath = "outputs\uart-live\interactive-uart.log",
    [int]$TimeoutSeconds = 600
)

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$log = [IO.Path]::GetFullPath((Join-Path $root $LogPath))
$imagePath = Join-Path $root "work\tftp\omvl\$Image"
$sender = Join-Path $PSScriptRoot "send_uart_visible.ps1"
if (-not (Test-Path -LiteralPath $imagePath -PathType Leaf)) {
    throw "Image missing: $imagePath"
}
$expectedSize = (Get-Item -LiteralPath $imagePath).Length
$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$offset = if (Test-Path -LiteralPath $log) { (Get-Item -LiteralPath $log).Length } else { 0 }
$observed = ""

function Queue-Uart([string]$command) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $sender -Command $command | Out-Host
}

function Read-NewLog {
    if (-not (Test-Path -LiteralPath $log)) { return "" }
    $stream = [IO.File]::Open($log, [IO.FileMode]::Open, [IO.FileAccess]::Read,
        [IO.FileShare]::ReadWrite)
    try {
        if ($offset -gt $stream.Length) { $script:offset = 0 }
        $stream.Seek($offset, [IO.SeekOrigin]::Begin) | Out-Null
        $reader = [IO.StreamReader]::new($stream, [Text.UTF8Encoding]::new($false),
            $true, 4096, $true)
        try { $text = $reader.ReadToEnd() } finally { $reader.Dispose() }
        $script:offset = $stream.Length
        return $text
    } finally { $stream.Dispose() }
}

function Wait-For([string]$pattern, [int]$seconds, [string]$label) {
    $localDeadline = [DateTime]::UtcNow.AddSeconds($seconds)
    while ([DateTime]::UtcNow -lt $localDeadline -and [DateTime]::UtcNow -lt $deadline) {
        $chunk = Read-NewLog
        if ($chunk) {
            $script:observed += $chunk
            if ($script:observed.Length -gt 131072) {
                $script:observed = $script:observed.Substring($script:observed.Length - 131072)
            }
            if ($script:observed -match $pattern) {
                Write-Output "VISIBLE_UART_STAGE_PASS=$label"
                return
            }
        }
        Start-Sleep -Milliseconds 100
    }
    throw "Timeout waiting for $label ($pattern)"
}

Write-Output "VISIBLE_UART_AUTOPILOT_READY image=$Image bytes=$expectedSize"
Write-Output "POWER_CYCLE_ROUTER_NOW=1"
Wait-For 'Hit any key to stop autoboot' 300 'autoboot_countdown'
Queue-Uart ' '
Wait-For 'ZHAL>\s*$' 30 'zhal_prompt'
Queue-Uart 'ATGU'
Wait-For 'Hit any key to exit' 30 'bootextension_exit'
Queue-Uart ' '
Wait-For 'topaz>\s*$' 30 'topaz_prompt'

foreach ($command in @(
    'setenv ipaddr 192.168.1.200',
    'setenv serverip 192.168.1.43'
)) {
    $script:observed = ""
    Queue-Uart $command
    Wait-For 'topaz>\s*$' 20 $command
}

$script:observed = ""
Queue-Uart "tftpboot 0x83000000 $Image"
Wait-For "Bytes transferred = $expectedSize" 180 'tftp_size'
Wait-For 'topaz>\s*$' 30 'tftp_complete'
$script:observed = ""
Queue-Uart 'iminfo 0x83000000'
Wait-For 'Verifying Checksum \.\.\. OK' 45 'iminfo_crc'
Wait-For 'topaz>\s*$' 20 'iminfo_complete'
$script:observed = ""
Queue-Uart 'bootm 0x83000000'
Wait-For 'RAMSSH_ENTROPY_SEED_REQUIRED' 120 'entropy_prompt'
$seed = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'new_ramssh_seed.ps1')
if ($seed -notmatch '^seed_[0-9a-f]{64}$') { throw "Invalid generated seed" }
Queue-Uart $seed
Wait-For 'RAMSSH_SERIAL_ENTROPY_OK bits=256' 30 'entropy_added'
Wait-For 'RAMSSH_SSH_EXEC' 60 'dropbear_exec'
Write-Output "VISIBLE_UART_LINUX510_BOOT_PASS=1"
