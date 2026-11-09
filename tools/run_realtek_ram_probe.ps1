param(
    [switch]$ExecuteRam,
    [switch]$SkipBoot,
    [string]$Acknowledge = "",
    [string]$Bundle = "outputs\kernel-port\realtek-loop\current-RAM-ONLY-NO-FLASH",
    [ValidatePattern('^COM[0-9]+$')]
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.200",
    [string]$LoadAddress = "0x83000000",
    [int]$CaptureSeconds = 75,
    [int]$TimeoutSeconds = 480
)

$ErrorActionPreference = "Stop"
$requiredAck = "OPENMITRASTAR_RAM_ONLY_NO_FLASH"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

function Get-Sha256Hex([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $algorithm.ComputeHash($stream)
        return ([BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
    } finally {
        $algorithm.Dispose()
        $stream.Dispose()
    }
}

$bundlePath = if ([IO.Path]::IsPathRooted($Bundle)) {
    [IO.Path]::GetFullPath($Bundle)
} else {
    [IO.Path]::GetFullPath((Join-Path $root $Bundle))
}
$allowedRoot = [IO.Path]::GetFullPath(
    (Join-Path $root "outputs\kernel-port\realtek-loop"))
if (-not $bundlePath.StartsWith($allowedRoot + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase)) {
    throw "Bundle must remain below $allowedRoot"
}

$manifestPath = Join-Path $bundlePath "manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Missing RAM-only bundle manifest: $manifestPath"
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.classification -ne "RAM-ONLY-NO-FLASH" -or
    [bool]$manifest.candidate_eligible) {
    throw "Bundle is not classified RAM-ONLY-NO-FLASH"
}
if ([bool]$manifest.safety.flash_supported -or
    [bool]$manifest.safety.persistent_writes_supported) {
    throw "Manifest unexpectedly permits persistent writes"
}

foreach ($artifact in $manifest.artifacts) {
    $path = [IO.Path]::GetFullPath((Join-Path $bundlePath $artifact.path))
    if (-not $path.StartsWith($bundlePath + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)) {
        throw "Artifact escapes bundle: $($artifact.path)"
    }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing bundle artifact: $path"
    }
    $item = Get-Item -LiteralPath $path
    $hash = Get-Sha256Hex $path
    if ($item.Length -ne [int64]$artifact.bytes -or
        $hash -ne [string]$artifact.sha256) {
        throw "Bundle artifact integrity failure: $($artifact.path)"
    }
}

$imagePath = [IO.Path]::GetFullPath(
    (Join-Path $root ([string]$manifest.base_ram_image.path)))
if (-not (Test-Path -LiteralPath $imagePath -PathType Leaf)) {
    throw "Missing pinned RAM image: $imagePath"
}
$imageHash = Get-Sha256Hex $imagePath
if ($imageHash -ne [string]$manifest.base_ram_image.sha256 -or
    (Get-Item -LiteralPath $imagePath).Length -ne
        [int64]$manifest.base_ram_image.bytes) {
    throw "Pinned RAM image no longer matches bundle manifest"
}
if ([string]$manifest.base_ram_image.classification -ne "RAM-ONLY") {
    throw "Base image is not classified RAM-ONLY"
}

$plan = [ordered]@{
    mode = if ($ExecuteRam) { "EXECUTE_RAM" } else { "DRY_RUN" }
    flash_supported = $false
    persistent_writes = $false
    bundle = $bundlePath
    kernel_release = [string]$manifest.kernel_release
    image = $imagePath
    image_sha256 = $imageHash
    uart = "$Port 115200 8N1"
    target = $ClientIp
    stages = @(
        "start one-shot TFTP for the pinned RAM image",
        "reboot current RAM kernel via serial SysRq and interrupt Bootbase",
        "iminfo CRC gate and bootm to RAM only",
        "authenticated SSH upload to /tmp/omrtl",
        "start passive UART capture before any module load",
        "verify upload SHA-256 on target",
        "load dependencies in manifest order and rtl8192ee last",
        "collect /proc/modules, /proc/net/dev, sysfs and dmesg tail"
    )
}
$plan | ConvertTo-Json -Depth 5

if (-not $ExecuteRam) {
    Write-Output "REALTEK_RAM_PROBE_DRY_RUN=1"
    Write-Output "To execute volatile hardware actions, add -ExecuteRam -Acknowledge $requiredAck"
    exit 0
}
if ($Acknowledge -cne $requiredAck) {
    throw "RAM execution refused: exact -Acknowledge $requiredAck is required"
}
if ($CaptureSeconds -lt 20 -or $CaptureSeconds -gt 300) {
    throw "CaptureSeconds must be between 20 and 300"
}
if ($TimeoutSeconds -lt 120 -or $TimeoutSeconds -gt 1200) {
    throw "TimeoutSeconds must be between 120 and 1200"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$evidenceDir = Join-Path $root "outputs\kernel-port\realtek-loop\hardware-$stamp-RAM-ONLY"
$uartDir = Join-Path $evidenceDir "uart"
New-Item -ItemType Directory -Force -Path $uartDir | Out-Null
$transcript = Join-Path $evidenceDir "probe-transcript.log"
$tftpOut = Join-Path $evidenceDir "tftp.stdout.log"
$tftpErr = Join-Path $evidenceDir "tftp.stderr.log"
$captureOut = Join-Path $evidenceDir "uart-capture.stdout.log"
$captureErr = Join-Path $evidenceDir "uart-capture.stderr.log"
$tftpRoot = Split-Path -Parent $imagePath
$filename = Split-Path -Leaf $imagePath
$tftp = $null
$capture = $null

function Invoke-LoggedPython {
    param([string[]]$Arguments, [string]$Label)
    "=== $Label ===" | Tee-Object -FilePath $transcript -Append | Out-Host
    # Windows PowerShell promotes native stderr to ErrorRecord objects when
    # ErrorActionPreference=Stop. Capture the complete child output first so a
    # Python traceback is preserved in the evidence transcript.
    $savedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & python @Arguments 2>&1
        $rc = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedErrorActionPreference
    }
    $output | Tee-Object -FilePath $transcript -Append | Out-Host
    if ($rc -ne 0) {
        throw "$Label failed with exit code $rc"
    }
    return @($output)
}

try {
    if (-not $SkipBoot) {
        # The listener is deliberately one-shot and exists only for the RAM image.
        $tftp = Start-Process -FilePath "python.exe" -WindowStyle Hidden -PassThru `
            -ArgumentList @(
                (Join-Path $PSScriptRoot "tftp_serve_once.py"),
                "--root", $tftpRoot,
                "--bind", "0.0.0.0",
                "--port", "69",
                "--timeout", "$TimeoutSeconds",
                "--once"
            ) -RedirectStandardOutput $tftpOut -RedirectStandardError $tftpErr
        Start-Sleep -Milliseconds 600
        if ($tftp.HasExited -and $tftp.ExitCode -ne 0) {
            throw "One-shot TFTP server failed before RAM boot"
        }

        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
            (Join-Path $PSScriptRoot "reboot_boot_ramssh.ps1") `
            -Port $Port -Filename $filename -ServerIp $ServerIp `
            -ClientIp $ClientIp -LoadAddress $LoadAddress `
            -TimeoutSeconds $TimeoutSeconds
        if ($LASTEXITCODE -ne 0) {
            throw "RAM boot/SSH gate failed"
        }
    } else {
        Write-Output "REALTEK_RAM_PROBE_SKIP_BOOT=1 host=$ClientIp"
    }

    Invoke-LoggedPython @(
        (Join-Path $PSScriptRoot "ramssh_exec.py"),
        "mkdir -p /tmp/omrtl/modules /tmp/omrtl/firmware/rtlwifi; ln -sf /tmp/omrtl/ram_insmod /tmp/omrtl/busybox",
        "--host", $ClientIp, "--timeout", "20"
    ) "remote-staging"

    # Start passive RX immediately after SSH is ready. This also captures any
    # early reset or watchdog event while artifacts are still uploading.
    $capture = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -PassThru `
        -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            (Join-Path $PSScriptRoot "capture_topaz_uart.ps1"),
            "-Port", $Port,
            "-Seconds", "$CaptureSeconds",
            "-OutputDirectory", $uartDir
        ) -RedirectStandardOutput $captureOut -RedirectStandardError $captureErr
    Start-Sleep -Milliseconds 800
    if ($capture.HasExited -and $capture.ExitCode -ne 0) {
        throw "UART capture could not start"
    }

    foreach ($artifact in $manifest.artifacts) {
        $relative = ([string]$artifact.path).Replace('\', '/')
        $source = Join-Path $bundlePath ([string]$artifact.path)
        $destination = "/tmp/omrtl/$relative"
        $mode = if ($relative -eq "ram_insmod") { "0700" } else { "0600" }
        Invoke-LoggedPython @(
            (Join-Path $PSScriptRoot "ramssh_upload.py"),
            $source, $destination, "--host", $ClientIp, "--mode", $mode
        ) "upload-$relative"
    }
    Invoke-LoggedPython @(
        (Join-Path $PSScriptRoot "ramssh_upload.py"),
        (Join-Path $bundlePath "UPLOAD_SHA256SUMS"),
        "/tmp/omrtl/UPLOAD_SHA256SUMS",
        "--host", $ClientIp, "--mode", "0600"
    ) "upload-hash-manifest"

    $uname = Invoke-LoggedPython @(
        (Join-Path $PSScriptRoot "ramssh_exec.py"),
        "uname -r", "--host", $ClientIp, "--timeout", "20"
    ) "kernel-release"
    if (($uname -join "`n") -notmatch [regex]::Escape([string]$manifest.kernel_release)) {
        throw "Target kernel release does not match the module bundle"
    }
    Invoke-LoggedPython @(
        (Join-Path $PSScriptRoot "ramssh_exec.py"),
        "cd /tmp/omrtl && ./busybox sha256sum -c UPLOAD_SHA256SUMS",
        "--host", $ClientIp, "--timeout", "30"
    ) "remote-sha256-gate"

    Invoke-LoggedPython @(
        (Join-Path $PSScriptRoot "ramssh_exec.py"),
        "if grep -q '^cfg80211 ' /proc/modules; then echo OMRTL_REGDB_ORDER_FAIL=cfg80211-already-loaded; exit 42; fi; echo OMRTL_REGDB_ORDER_PASS=cfg80211-absent",
        "--host", $ClientIp, "--timeout", "20"
    ) "regdb-first-preflight"

    Invoke-LoggedPython @(
        (Join-Path $PSScriptRoot "ramssh_exec.py"),
        "mkdir -p /lib/firmware && cp /tmp/omrtl/firmware/regulatory.db /lib/firmware/regulatory.db && printf '%s  %s\n' 'e9051546c38849b54e6b6a90ca32151c9e29f23edb7698f2c4a437fc353b3393' '/lib/firmware/regulatory.db' | /tmp/omrtl/busybox sha256sum -c - && echo OMRTL_REGDB_INSTALLED_BEFORE_CFG80211=1",
        "--host", $ClientIp, "--timeout", "20"
    ) "install-regdb-before-cfg80211"

    Invoke-LoggedPython @(
        (Join-Path $PSScriptRoot "ramssh_exec.py"),
        "mkdir -p /lib/firmware/rtlwifi && cp /tmp/omrtl/firmware/rtlwifi/rtl8192eefw.bin /lib/firmware/rtlwifi/rtl8192eefw.bin",
        "--host", $ClientIp, "--timeout", "20"
    ) "install-firmware-ram-only"

    foreach ($module in $manifest.load_order) {
        $moduleName = [string]$module
        $moduleParameters = if ($moduleName -eq "rtl8192ee.ko") {
            "msi=0 dma64=0 aspm=0 ips=0 fwlps=0 swenc=1 disable_watchdog=1 debug_level=5"
        } else { "" }
        Invoke-LoggedPython @(
            (Join-Path $PSScriptRoot "ramssh_exec.py"),
            "echo OMRTL_LOAD_BEGIN=$moduleName; /tmp/omrtl/busybox insmod /tmp/omrtl/modules/$moduleName $moduleParameters && echo OMRTL_LOAD_PASS=$moduleName",
            "--host", $ClientIp, "--timeout", "60"
        ) "insmod-$moduleName"
    }

    Invoke-LoggedPython @(
        (Join-Path $PSScriptRoot "ramssh_exec.py"),
        "echo ===MODULES===; cat /proc/modules; echo ===NETDEV===; cat /proc/net/dev; echo ===IEEE80211===; ls -la /sys/class/ieee80211 2>&1; echo ===NETCLASS===; ls -la /sys/class/net 2>&1; echo ===DMESG===; dmesg",
        "--host", $ClientIp, "--timeout", "40"
    ) "targeted-probe"
} finally {
    if ($capture -and -not $capture.HasExited) {
        try { Wait-Process -Id $capture.Id -Timeout ($CaptureSeconds + 20) } catch { }
    }
    if ($tftp -and -not $tftp.HasExited) {
        Stop-Process -Id $tftp.Id -Force -ErrorAction SilentlyContinue
    }
}

$uartLogs = @(Get-ChildItem -LiteralPath $uartDir -Filter '*.log' -File -ErrorAction SilentlyContinue)
$uartText = ($uartLogs | ForEach-Object {
    Get-Content -LiteralPath $_.FullName -Raw -ErrorAction SilentlyContinue
}) -join "`n"
$probeText = if (Test-Path -LiteralPath $transcript) {
    Get-Content -LiteralPath $transcript -Raw
} else { "" }
$fatal = $uartText -match 'Unhandled .*Exception|Kernel panic|Oops:'
$eepromExit = $uartText -match 'OMRTL stage=eeprom-exit'
$interface = $probeText -match '/sys/class/net/(wlan|wl)|\bwlan[0-9]+\b|\bphy[0-9]+\b'
$result = [ordered]@{
    schema = "openmitrastar.realtek-ram-probe/v1"
    classification = "RAM-ONLY-NO-FLASH"
    image_sha256 = $imageHash
    bundle_manifest = $manifestPath
    evidence_directory = $evidenceDir
    uart_logs = @($uartLogs.FullName)
    eeprom_exit_observed = $eepromExit
    fatal_exception_observed = $fatal
    wireless_interface_observed = $interface
    pass = ($eepromExit -and -not $fatal)
}
$resultPath = Join-Path $evidenceDir "result.json"
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $resultPath -Encoding UTF8
$result | ConvertTo-Json -Depth 5
if (-not $result.pass) {
    throw "Realtek RAM probe did not prove eeprom-exit without a fatal exception; see $evidenceDir"
}
Write-Output "REALTEK_RAM_PROBE_PASS evidence=$evidenceDir"
