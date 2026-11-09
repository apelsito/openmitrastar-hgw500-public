param(
    [switch]$ExecuteRam,
    [string]$AckRamOnly = "",
    [string]$PskFile = "",
    [string]$Ssid = "OpenMitraStar-Lab",
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.200",
    [int]$TimeoutSeconds = 480
)

$ErrorActionPreference = "Stop"
$AckValue = "OPENMITRASTAR_INTEGRATED_CONTROLS_RAM_ONLY"
$Root = Split-Path -Parent $PSScriptRoot
$Filename = "linux510-radiohw-controls-integrated-RAM-ONLY.bin"
$Image = Join-Path $Root "work\tftp\omvl\$Filename"
$ExpectedSha = "9bbd30181b0df52e5c2b982dd3b767c0cc00657cdb13dd12d097f52468ab2913"
$TftpOut = Join-Path $Root "outputs\kernel-port\hgw500-controls-integrated\tftp-runtime.stdout.log"
$TftpErr = Join-Path $Root "outputs\kernel-port\hgw500-controls-integrated\tftp-runtime.stderr.log"

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

if (-not (Test-Path -LiteralPath $Image -PathType Leaf)) { throw "Missing integrated RAM image" }
$ActualSha = Get-Sha256Hex $Image
if ($ActualSha -ne $ExpectedSha) { throw "Integrated RAM image SHA-256 mismatch" }
if ($Ssid -notmatch '^[A-Za-z0-9_.-]{1,32}$') { throw "Invalid SSID" }

$Plan = [ordered]@{
    schema = "openmitrastar.integrated-controls-secure-ap/v1"
    mode = if ($ExecuteRam) { "EXECUTE_RAM" } else { "DRY_RUN" }
    classification = "RAM-ONLY-NO-FLASH"
    image = $Image
    image_sha256 = $ActualSha
    stages = @(
        "one-shot TFTP + Bootbase RAM boot",
        "authenticated Realtek/CTR/CCM/CMAC bundle load",
        "detached WPA2 bridge launch",
        "LED brightness + input event + hostapd readback"
    )
    flash_supported = $false
    persistent_writes_supported = $false
}
$Plan | ConvertTo-Json -Depth 5

if (-not $ExecuteRam) {
    Write-Output "OMINTEGRATED_DRY_RUN_PASS=1"
    exit 0
}
if ($AckRamOnly -cne $AckValue) { throw "Execution requires exact -AckRamOnly $AckValue" }
if (-not $PskFile -or -not (Test-Path -LiteralPath $PskFile -PathType Leaf)) {
    throw "-PskFile must name a local secret file"
}

$tftp = $null
try {
    $tftp = Start-Process -FilePath "python.exe" -WindowStyle Hidden -PassThru `
        -ArgumentList @(
            (Join-Path $PSScriptRoot "tftp_serve_once.py"),
            "--root", (Split-Path -Parent $Image),
            "--bind", "0.0.0.0", "--port", "69",
            "--timeout", "$TimeoutSeconds", "--once"
        ) -RedirectStandardOutput $TftpOut -RedirectStandardError $TftpErr
    Start-Sleep -Milliseconds 600
    if ($tftp.HasExited -and $tftp.ExitCode -ne 0) { throw "TFTP failed before boot" }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
        (Join-Path $PSScriptRoot "reboot_boot_ramssh.ps1") `
        -Port $Port -Filename $Filename -ServerIp $ServerIp `
        -ClientIp $ClientIp -TimeoutSeconds $TimeoutSeconds
    if ($LASTEXITCODE) { throw "Integrated RAM boot failed" }
} finally {
    if ($tftp -and -not $tftp.HasExited) {
        Stop-Process -Id $tftp.Id -Force -ErrorAction SilentlyContinue
    }
}

& python (Join-Path $PSScriptRoot "openmitrastar_realtek_loop.py") `
    --execute-ram --skip-boot `
    --ack-ram-only OPENMITRASTAR_RAM_ONLY_NO_FLASH `
    --capture-seconds 75 --uart-port $Port `
    --server-ip $ServerIp --client-ip $ClientIp
if ($LASTEXITCODE) { throw "Integrated Realtek runtime load failed" }

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    (Join-Path $PSScriptRoot "run_openmitrastar_ap_detached.ps1") `
    -ExecuteRam -AckRamOnly OPENMITRASTAR_RAM_ONLY_AP_DETACHED `
    -Topology bridge -Ssid $Ssid -PskFile ([IO.Path]::GetFullPath($PskFile)) `
    -HostAddress $ClientIp -TimeoutSeconds 120
if ($LASTEXITCODE) { throw "Integrated WPA2 bridge launch failed" }

$readback = & python (Join-Path $PSScriptRoot "ramssh_exec.py") `
    "echo ===LED===; cat /sys/class/leds/openmitrastar:green:wlan2g/brightness; echo ===INPUT===; cat /proc/bus/input/devices; echo ===HOSTAPD===; /tmp/openmitrastar-ap/bundle/bin/hostapd_cli -p /tmp/openmitrastar-ap/ctrl -i wlan0 status; echo ===BRIDGE===; /tmp/openmitrastar-ap/bundle/bin/busybox brctl show" `
    --host $ClientIp --timeout 30
if ($LASTEXITCODE) { throw "Integrated controls readback failed" }
$text = $readback -join "`n"
if ($text -notmatch '(?m)^255$' -or
    $text -notmatch 'OpenMitraStar Wi-Fi button' -or
    $text -notmatch 'Handlers=event0' -or
    $text -notmatch 'state=ENABLED' -or
    $text -notmatch '(?s)br0.*eth0.*wlan0') {
    throw "Integrated controls/AP contract failed"
}
$readback
Write-Output "OMINTEGRATED_RUNTIME_PASS image_sha256=$ActualSha"
