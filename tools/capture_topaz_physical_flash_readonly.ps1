param(
    [string]$Port = "COM3",
    [string]$OutputRoot = "outputs\flash-backups",
    [string]$SessionDir = "",
    [int[]]$PartitionIndexes = @(0, 1, 2, 3, 4, 5),
    [ValidateRange(1024, 65536)] [int]$ChunkBytes = 4096,
    [long]$ResumeBytes = -1,
    [ValidateRange(1, 10)] [int]$MaxRetries = 3,
    [ValidateRange(10, 600)] [int]$CommandTimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if (($ChunkBytes % 16) -ne 0) { throw "ChunkBytes must be a multiple of 16" }
$invalidIndexes = @($PartitionIndexes | Where-Object { $_ -lt 0 -or $_ -gt 5 })
if ($invalidIndexes.Count) { throw "PartitionIndexes accepts only physical mtd0..mtd5" }
if ($ResumeBytes -ge 0 -and $PartitionIndexes.Count -ne 1) {
    throw "Explicit ResumeBytes requires exactly one PartitionIndexes value"
}

$layout = @(
    [ordered]@{ index = 0; name = "uboot";         offset = 0x000000; size = 0x020000 },
    [ordered]@{ index = 1; name = "uboot_env";     offset = 0x020000; size = 0x010000 },
    [ordered]@{ index = 2; name = "uboot_env_bak"; offset = 0x030000; size = 0x010000 },
    [ordered]@{ index = 3; name = "linux_safety";  offset = 0x040000; size = 0x7a0000 },
    [ordered]@{ index = 4; name = "linux_live";    offset = 0x7e0000; size = 0x7a0000 },
    [ordered]@{ index = 5; name = "data";          offset = 0xf80000; size = 0x080000 }
)
$selected = @($layout | Where-Object { $PartitionIndexes -contains $_.index })

if ($SessionDir) {
    $sessionDirPath = [IO.Path]::GetFullPath((Join-Path (Get-Location) $SessionDir))
    $sessionPath = Join-Path $sessionDirPath "capture-session.json"
    if (-not (Test-Path -LiteralPath $sessionPath -PathType Leaf)) {
        throw "Existing SessionDir has no capture-session.json: $sessionDirPath"
    }
    $existing = Get-Content -LiteralPath $sessionPath -Raw | ConvertFrom-Json
    if (-not $existing.read_only -or -not $existing.mtd6_excluded -or $existing.physical_flash_size -ne 0x1000000) {
        throw "Existing session does not satisfy the physical read-only contract"
    }
    Write-Host "RESUME_SESSION=$sessionDirPath"
} else {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $sessionDirPath = [IO.Path]::GetFullPath((Join-Path (Get-Location) (Join-Path $OutputRoot "hgw500-physical-uart-$stamp")))
    New-Item -ItemType Directory -Force -Path $sessionDirPath | Out-Null
    $session = [ordered]@{
        schema = "openmitrastar.topaz-physical-flash-capture.v2"
        created_utc = [DateTime]::UtcNow.ToString("o")
        port = $Port; baud = 115200; ram_address = "0x83000000"
        chunk_bytes = $ChunkBytes; read_only = $true
        physical_flash_size = 0x1000000; mtd6_excluded = $true
        mtd6_reason = "logical rootfs view; not a physical flash partition"
        partitions = $layout
    }
    $sessionPath = Join-Path $sessionDirPath "capture-session.json"
    $session | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $sessionPath -Encoding utf8
}

$parserPath = Join-Path $PSScriptRoot "parse_topaz_physical_flash.py"
if (-not (Test-Path -LiteralPath $parserPath -PathType Leaf)) { throw "Missing parser helper: $parserPath" }
$progressJson = & python $parserPath --capture-dir $sessionDirPath --progress-json
if ($LASTEXITCODE -ne 0) { throw "Unable to inspect existing capture progress" }
$progress = $progressJson | ConvertFrom-Json
([ordered]@{
    started_utc = [DateTime]::UtcNow.ToString("o"); port = $Port
    chunk_bytes = $ChunkBytes; max_retries = $MaxRetries
    partition_indexes = $PartitionIndexes; explicit_resume_bytes = $ResumeBytes
} | ConvertTo-Json -Compress) | Add-Content -LiteralPath (Join-Path $sessionDirPath "capture-runs.jsonl") -Encoding utf8

$serial = [IO.Ports.SerialPort]::new($Port, 115200, 'None', 8, 'One')
$serial.Handshake = 'None'; $serial.DtrEnable = $false; $serial.RtsEnable = $false
$serial.ReadTimeout = 100; $serial.WriteTimeout = 2000
$script:writer = $null
$script:rollingTail = ""

function Write-HostMarker([string]$Text) {
    Write-Host ("[{0}] {1}" -f [DateTime]::UtcNow.ToString("o"), $Text)
}

function Wait-TopazPrompt([int]$TimeoutSeconds, [string]$Stage) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $buffer = [Text.StringBuilder]::new(16384)
    $script:rollingTail = ""
    while ([DateTime]::UtcNow -lt $deadline) {
        $chunk = $serial.ReadExisting()
        if ($chunk) {
            if ($null -ne $script:writer) { $script:writer.Write($chunk) }
            Write-Host -NoNewline $chunk
            [void]$buffer.Append($chunk)
            $script:rollingTail += $chunk
            if ($script:rollingTail.Length -gt 4096) {
                $script:rollingTail = $script:rollingTail.Substring($script:rollingTail.Length - 4096)
            }
            if ($script:rollingTail -match 'topaz>\s*$') {
                if ($null -ne $script:writer) { $script:writer.Flush() }
                return $buffer.ToString()
            }
            if ($script:rollingTail -match '(?im)(unknown command|usage:|data abort|machine check|spi_flash[^\r\n]*(fail|error))') {
                throw "Bootbase rejected a read-only command during $Stage"
            }
        }
        Start-Sleep -Milliseconds 10
    }
    throw "Timed out waiting for topaz> during $Stage"
}

function Acquire-Prompt([string]$Stage) {
    $serial.DiscardInBuffer(); $serial.Write("`r")
    [void](Wait-TopazPrompt -TimeoutSeconds 15 -Stage $Stage)
}

function Send-ReadOnlyCommand([string]$Command, [string]$Stage) {
    $flashRead = '^spi_flash read 0x[0-9a-f]{8} 0x83000000 0x[0-9a-f]{8}$'
    $memoryDisplay = '^md\.l 0x83000000 0x[0-9a-f]+$'
    if ($Command -notmatch $flashRead -and $Command -notmatch $memoryDisplay) {
        throw "Refusing command outside the read-only allowlist: $Command"
    }
    $serial.Write($Command + "`r")
    return Wait-TopazPrompt -TimeoutSeconds $CommandTimeoutSeconds -Stage $Stage
}

try {
    $serial.Open(); Acquire-Prompt -Stage "initial prompt acquisition"
    Write-HostMarker "TOPAZ_PROMPT_PASS session=$sessionDirPath"
    foreach ($part in $selected) {
        $progressProperty = "mtd$($part.index)"
        $autoDone = [long]$progress.$progressProperty.contiguous_bytes
        $done = if ($ResumeBytes -ge 0) { $ResumeBytes } else { $autoDone }
        if ($done -lt 0 -or $done -gt $part.size -or ($done % 4)) { throw "Invalid resume point $done" }
        if ($ResumeBytes -ge 0 -and $ResumeBytes -gt $autoDone) {
            throw "ResumeBytes=$ResumeBytes would skip data; verified=$autoDone"
        }
        if ($done -eq $part.size) {
            Write-HostMarker ("CAPTURE_PARTITION_ALREADY_COMPLETE mtd={0} bytes={1}" -f $part.index, $done)
            continue
        }
        $aggregatePath = Join-Path $sessionDirPath ("mtd{0}-{1}.uart.log" -f $part.index, $part.name)
        $chunkDir = Join-Path $sessionDirPath ("chunks\mtd{0}-{1}" -f $part.index, $part.name)
        $rejectedDir = Join-Path $chunkDir "rejected"
        New-Item -ItemType Directory -Force -Path $chunkDir, $rejectedDir | Out-Null
        Write-HostMarker ("CAPTURE_RESUME mtd={0} verified_bytes=0x{1:x} flash_offset=0x{2:x8} chunk_bytes=0x{3:x}" -f $part.index, $done, ($part.offset + $done), $ChunkBytes)
        while ($done -lt $part.size) {
            $thisChunk = [int][Math]::Min($ChunkBytes, ($part.size - $done))
            $flashOffset = [uint32]($part.offset + $done)
            $wordCount = [uint32]($thisChunk / 4)
            $finalChunk = Join-Path $chunkDir ("chunk-{0:x8}-{1:x8}.uart.log" -f $flashOffset, $thisChunk)
            $captured = $false
            for ($attempt = 1; $attempt -le $MaxRetries -and -not $captured; $attempt++) {
                $tempChunk = "$finalChunk.attempt$attempt.tmp"
                if (Test-Path -LiteralPath $tempChunk) { Remove-Item -LiteralPath $tempChunk -Force }
                $script:writer = [IO.StreamWriter]::new($tempChunk, $false, [Text.UTF8Encoding]::new($false), 32768)
                try {
                    $readCommand = "spi_flash read 0x{0:x8} 0x83000000 0x{1:x8}" -f $flashOffset, $thisChunk
                    $readOutput = Send-ReadOnlyCommand -Command $readCommand -Stage ("mtd{0} offset 0x{1:x8} attempt {2} SPI read" -f $part.index, $flashOffset, $attempt)
                    $decimalSize = [string]$thisChunk; $hexSize = "{0:x}" -f $thisChunk
                    if ($readOutput -notmatch "(?i)ret_size\s*=\s*(?:$decimalSize|0x0*$hexSize)\b") { throw "Incorrect ret_size" }
                    $dumpCommand = "md.l 0x83000000 0x{0:x}" -f $wordCount
                    [void](Send-ReadOnlyCommand -Command $dumpCommand -Stage ("mtd{0} offset 0x{1:x8} attempt {2} memory dump" -f $part.index, $flashOffset, $attempt))
                    $script:writer.Flush()
                } catch {
                    Write-HostMarker ("CAPTURE_CHUNK_RETRY mtd={0} offset=0x{1:x8} attempt={2} reason={3}" -f $part.index, $flashOffset, $attempt, $_.Exception.Message)
                } finally {
                    if ($null -ne $script:writer) { $script:writer.Dispose(); $script:writer = $null }
                }
                $validation = & python $parserPath --validate-chunk-log $tempChunk --flash-offset ("0x{0:x}" -f $flashOffset) --size ("0x{0:x}" -f $thisChunk) 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Move-Item -LiteralPath $tempChunk -Destination $finalChunk -Force
                    $aggregate = [IO.File]::Open($aggregatePath, [IO.FileMode]::Append, [IO.FileAccess]::Write, [IO.FileShare]::Read)
                    try {
                        $source = [IO.File]::OpenRead($finalChunk)
                        try { $source.CopyTo($aggregate) } finally { $source.Dispose() }
                    } finally { $aggregate.Dispose() }
                    $captured = $true; $done += $thisChunk
                    Write-HostMarker ("CAPTURE_CHUNK_PASS mtd={0} offset=0x{1:x8} bytes=0x{2:x} attempt={3}" -f $part.index, $flashOffset, $thisChunk, $attempt)
                } else {
                    $rejected = Join-Path $rejectedDir ("chunk-{0:x8}-{1:x8}-attempt{2}.rejected.log" -f $flashOffset, $thisChunk, $attempt)
                    if (Test-Path -LiteralPath $tempChunk) { Move-Item -LiteralPath $tempChunk -Destination $rejected -Force }
                    Write-HostMarker ("CAPTURE_CHUNK_RETRY mtd={0} offset=0x{1:x8} attempt={2} validator={3}" -f $part.index, $flashOffset, $attempt, ($validation -join ' '))
                    if ($attempt -lt $MaxRetries) { Acquire-Prompt -Stage "retry prompt reacquisition" }
                }
            }
            if (-not $captured) { throw "Chunk mtd$($part.index) offset 0x$('{0:x8}' -f $flashOffset) failed $MaxRetries attempts" }
            Write-Progress -Activity "Read-only physical flash backup" -Status ("mtd{0}: {1}/{2}" -f $part.index, $done, $part.size) -PercentComplete ([Math]::Round(100.0 * $done / $part.size, 1))
        }
        Write-HostMarker ("CAPTURE_PARTITION_PASS mtd={0} name={1} bytes={2}" -f $part.index, $part.name, $part.size)
    }
    Write-Progress -Activity "Read-only physical flash backup" -Completed
    Write-HostMarker "CAPTURE_SELECTED_PASS session=$sessionDirPath"
    Write-Output "CAPTURE_SESSION=$sessionDirPath"
    Write-Output "NEXT=python tools/parse_topaz_physical_flash.py --capture-dir `"$sessionDirPath`""
} finally {
    if ($null -ne $script:writer) { $script:writer.Dispose() }
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
}
