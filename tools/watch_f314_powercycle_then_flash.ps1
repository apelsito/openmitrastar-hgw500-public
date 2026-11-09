[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$ExpectedPnpDeviceId = "FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000",
    [string]$ServerIp = "192.168.1.43",
    [string]$RouterHost = "192.168.1.90",
    [ValidateRange(300, 43200)][int]$WaitSeconds = 21600,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$deviceRoot = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary"
$build = Join-Path $deviceRoot "firmware\f314-device-bound"
$base = "openmitrastar-linux510-f314-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
$candidate = Join-Path $build ($base + ".webformat.bin")
$requiredAck = "OPENMITRASTAR_F314_QTN_NONDFS_GUARD_A0C7350A"
$expectedSha = "a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11"
$expectedBytes = 5292032
$expectedFullCrc = "d6b13baa"
$expectedFullSha = "bc06db537f4eb20ae2b2c64c47262f44c678b1f46a035d2229a768aa36732989"
$currentFullCrc = "542257b9"
$currentFullSha = "158f3b853edb21c4b3f833f14c26cd053f2170a0ee61d761be2474c795a3f53d"
$expectedVersion = "lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device"

if (-not $OutputDir) {
    $OutputDir = Join-Path $root ("outputs\flash-watch\f314-powercycle-{0}" -f [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ"))
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$statusPath = Join-Path $OutputDir "status.json"
$uartPath = Join-Path $OutputDir "uart.log"
$runnerLog = Join-Path $OutputDir "runner.log"

function Write-Status([string]$State, [string]$Detail = "", [int64]$Bytes = 0) {
    [ordered]@{
        schema = "openmitrastar.f314-powercycle-watch/v1"
        state = $State
        detail = $Detail
        updated_at = [DateTimeOffset]::UtcNow.ToString("o")
        watcher_pid = $PID
        execute = [bool]$Execute
        port = $Port
        pinned_pnp_device_id = $ExpectedPnpDeviceId
        uart_bytes = $Bytes
        target = "physical mtd4/linux_live"
        candidate = $candidate
        candidate_bytes = $expectedBytes
        candidate_sha256 = $expectedSha
        expected_current_full_slot_crc32 = $currentFullCrc
        expected_current_full_slot_sha256 = $currentFullSha
        output_dir = $OutputDir
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statusPath -Encoding ascii
}

function Resolve-PinnedPort {
    $device = Get-PnpDevice -Class Ports -PresentOnly -ErrorAction SilentlyContinue |
        Where-Object { $_.InstanceId -ieq $ExpectedPnpDeviceId } |
        Select-Object -First 1
    if (-not $device -or $device.FriendlyName -notmatch '\((COM[0-9]{1,3})\)') { return $null }
    return $Matches[1]
}

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace("-", "").ToLowerInvariant()
    } finally {
        $sha.Dispose()
        $stream.Dispose()
    }
}

if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "F314 candidate missing" }
if ((Get-Item -LiteralPath $candidate).Length -ne $expectedBytes -or (Get-Sha256 $candidate) -ne $expectedSha) {
    throw "F314 candidate identity mismatch"
}
if (-not $Execute) {
    Write-Status "dry-run" "watcher validated; no UART or flash action"
    Get-Content -Raw -LiteralPath $statusPath
    exit 0
}
if ($Ack -ne $requiredAck) { throw "Execute requires exact Ack: $requiredAck" }

$mutex = [Threading.Mutex]::new($false, "Local\OpenMitraStar-F314-Powercycle-Watch")
$owned = $mutex.WaitOne(0)
if (-not $owned) { throw "F314 power-cycle watcher is already active" }
$serial = $null
$uart = $null
$bytes = [int64]0
$tail = ""
$breakCount = 0
$atguCount = 0
$deadline = [DateTimeOffset]::UtcNow.AddSeconds($WaitSeconds)

try {
    $uart = [IO.StreamWriter]::new(
        [IO.File]::Open($uartPath, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite),
        [Text.UTF8Encoding]::new($false))
    $uart.AutoFlush = $true
    Write-Status "waiting_uart_first_byte" "No blind input will be sent" 0

    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        if (-not $serial -or -not $serial.IsOpen) {
            $currentPort = Resolve-PinnedPort
            if (-not $currentPort) { Start-Sleep -Milliseconds 250; continue }
            try {
                $serial = [IO.Ports.SerialPort]::new($currentPort, 115200, [IO.Ports.Parity]::None, 8, [IO.Ports.StopBits]::One)
                $serial.Handshake = [IO.Ports.Handshake]::None
                $serial.DtrEnable = $false
                $serial.RtsEnable = $false
                $serial.ReadTimeout = 200
                $serial.WriteTimeout = 500
                $serial.Open()
                $serial.DiscardInBuffer()
            } catch {
                if ($serial) { $serial.Dispose(); $serial = $null }
                Start-Sleep -Milliseconds 500
                continue
            }
        }

        try {
            $chunk = $serial.ReadExisting()
            if ($chunk) {
                $uart.Write($chunk)
                $bytes += [Text.Encoding]::ASCII.GetByteCount($chunk)
                $tail += $chunk
                if ($tail.Length -gt 32768) { $tail = $tail.Substring($tail.Length - 32768) }
                Write-Status "uart_seen" "Waiting for Bootbase/Topaz prompt" $bytes

                if ($tail -match 'Hit any key (to stop autoboot|to exit)') {
					if ($breakCount -ge 4) { throw "Bootbase prompt loop exceeded safe break limit" }
                    $serial.Write(" ")
					Start-Sleep -Milliseconds 40
					$serial.Write("`r")
					$breakCount += 1
					$tail = ""
                    Write-Status "autoboot_interrupted" "Space+Enter sent after observed prompt count=$breakCount" $bytes
					continue
                }
				if ($tail -match 'ZHAL>\s*$') {
					if ($atguCount -ge 2) { throw "ZHAL ATGU loop exceeded safe command limit" }
					$serial.Write([string][char]0x15)
					$serial.Write([string][char]0x08)
					Start-Sleep -Milliseconds 80
                    $serial.Write("ATGU`r")
					$atguCount += 1
					$tail = ""
                    Write-Status "atgu_sent" "ATGU sent after observed ZHAL count=$atguCount" $bytes
					continue
                }
                if ($tail -match 'topaz>\s*$') {
                    Write-Status "topaz_ready" "Handing UART to guarded flasher" $bytes
                    break
                }
            }
            Start-Sleep -Milliseconds 50
        } catch [IO.IOException], [InvalidOperationException] {
            try { $serial.Close() } catch {}
            $serial.Dispose(); $serial = $null
            Start-Sleep -Milliseconds 250
        }
    }
    if ($tail -notmatch 'topaz>\s*$') { throw "Timed out before observed topaz prompt" }
} finally {
    if ($serial) { try { $serial.Close() } catch {}; $serial.Dispose() }
    if ($uart) { $uart.Dispose() }
    if ($owned) { try { $mutex.ReleaseMutex() } catch {} }
    $mutex.Dispose()
}

$env:OM_Q3_FLASH_ACK = $requiredAck
$env:OM_Q3_FLASH_BUILD_DIR = $build
$env:OM_Q3_FLASH_CANDIDATE = $candidate
$env:OM_Q3_FLASH_BOOTBASE_CONTRACT = Join-Path $build "bootbase-contract.json"
$env:OM_Q3_FLASH_MANIFEST = Join-Path $build "manifest.json"
$env:OM_Q3_FLASH_INITRAMFS = Join-Path $build ($base + ".kernel.raw.bin")
$env:OM_Q3_FLASH_KCONFIG = Join-Path $build ($base + ".config")
$env:OM_Q3_FLASH_LAYOUT_MODE = "squashfs-split"
$env:OM_Q3_FLASH_ROOTFS_IMAGE = Join-Path $build ($base + ".rootfs.squashfs")
$env:OM_Q3_FLASH_DTB = Join-Path $build ($base + ".dtb")
$env:OM_Q3_FLASH_ROOTFS_OFFSET = "0x180000"
$env:OM_Q3_FLASH_EXPECTED_SHA256 = $expectedSha
$env:OM_Q3_FLASH_EXPECTED_BYTES = [string]$expectedBytes
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32 = $currentFullCrc
$env:OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256 = $currentFullSha

$runner = Join-Path $root "tools\run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py"
& python $runner --execute --ack $requiredAck --port $Port --server-ip $ServerIp `
    --client-ip $RouterHost --host $RouterHost --transport tftp --skip-reboot `
    --uart-attach-topaz --timeout 1800 --erase-bytes 0x5e0000 2>&1 |
    Tee-Object -FilePath $runnerLog
if ($LASTEXITCODE -ne 0) { Write-Status "flash_failed" "See runner.log" $bytes; exit 1 }

$post = Join-Path $OutputDir "postflash"
& python (Join-Path $root "tools\post_flash_f214_device_gate.py") --host $RouterHost `
    --wait-seconds 360 --output-dir $post --device-dir $build `
    --expected-version $expectedVersion --known-hosts-name known_hosts.f314
if ($LASTEXITCODE -ne 0) { Write-Status "postflash_failed" "Platform gate failed" $bytes; exit 1 }

$ssh = (Get-Command ssh.exe -ErrorAction Stop).Source
$knownHosts = Join-Path $build "known_hosts.f314"
$radio = & $ssh -i "$env:USERPROFILE\.ssh\id_ed25519" -o IdentitiesOnly=yes -o BatchMode=yes `
    -o ConnectTimeout=8 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$knownHosts" `
    -o LogLevel=ERROR "root@$RouterHost" "/usr/sbin/om-radioctl status 5g" 2>&1
if ($LASTEXITCODE -ne 0) { Write-Status "radio_gate_failed" (($radio | Out-String).Trim()) $bytes; exit 1 }
$radioJson = ($radio | Out-String).Trim() | ConvertFrom-Json
if ([int]$radioJson.channel -notin @(36, 40, 44, 48) -or $radioJson.state -ne "ready") {
    Write-Status "radio_gate_failed" "F314 did not boot ready on a non-DFS channel" $bytes
    exit 1
}

$matrixDir = Join-Path $OutputDir "qtn-control-matrix"
Write-Status "control_matrix" "Running 14 transactional Quantenna controls; 3 DFS-dependent controls must reject" $bytes
& python (Join-Path $root "tools\run_f314_qtn_control_matrix_gate.py") --execute `
    --ack OPENMITRASTAR_F314_QTN_CONTROL_MATRIX --host $RouterHost `
    --known-hosts $knownHosts --output-dir $matrixDir --resume 2>&1 |
    Tee-Object -FilePath (Join-Path $OutputDir "qtn-control-matrix.log")
if ($LASTEXITCODE -ne 0) {
    Write-Status "control_matrix_failed" "F314 remains installed; see qtn-control-matrix checkpoint/log" $bytes
    exit 1
}

Write-Status "pass" "F314 flashed, read back, booted on non-DFS channel $($radioJson.channel), and passed the control matrix" $bytes
Write-Output "OMF314_POWERCYCLE_FLASH_PASS=1 output=$OutputDir"
