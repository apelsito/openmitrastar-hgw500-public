param(
    [string]$Port = 'COM3',
    [string]$ServerIp = '192.168.1.43',
    [string]$BootClientIp = '192.168.1.90',
    [string]$SshHost = '192.168.1.90',
    [switch]$UseSshReboot,
    [switch]$Execute,
    [string]$AckRamOnly = ''
)

$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Filename = 'openmitrastar-5.10.260-lab-2g4-RAM-TEST-NO-FLASH.bin'
$ExpectedSha256 = '5a528ca78446041d7a53a0c789da8fd388f8bacc6e2286056adaa118775a1f53'
$ExpectedBytes = 4332045
$ExpectedClassification = 'RAM-ONLY-W2-2G-PARITY-TX17-BEACON128-NO-FLASH'
$ExpectedBundleManifestSha256 = '2688b9511ddd24b31f7af8525f956da8055fc3d0297d4f25edec5b6c9122124c'
$AckValue = 'OPENMITRASTAR_TX17_RAM_BOOT_ONLY_NO_FLASH'
$Image = Join-Path $Root "work\tftp\omvl\$Filename"
$ManifestPath = Join-Path $Root 'work\mission-state\w2-2g-parity-tx17-beacon128-v1\build\manifest.json'
$BundleManifestPath = Join-Path $Root 'outputs\kernel-port\realtek-loop\w2-tx17-all32-beacon128-RAM-ONLY-NO-FLASH\manifest.json'
$BootTool = Join-Path $Root 'tools\reboot_boot_ramssh.ps1'
$ExecTool = Join-Path $Root 'tools\ramssh_exec.py'

function Get-Sha256Hex([string]$Path) {
    $GetFileHash = Get-Command Get-FileHash -ErrorAction SilentlyContinue
    if ($GetFileHash) {
        return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $Stream = [IO.File]::OpenRead($Path)
    try {
        $Sha = [Security.Cryptography.SHA256]::Create()
        try {
            return -join ($Sha.ComputeHash($Stream) | ForEach-Object { $_.ToString('x2') })
        } finally {
            $Sha.Dispose()
        }
    } finally {
        $Stream.Dispose()
    }
}

foreach ($Required in @($Image, $ManifestPath, $BundleManifestPath, $BootTool, $ExecTool)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) {
        throw "Missing required input: $Required"
    }
}

$ActualSha256 = Get-Sha256Hex $Image
$Bytes = (Get-Item -LiteralPath $Image).Length
$BundleManifestSha256 = Get-Sha256Hex $BundleManifestPath
if ($ActualSha256 -ne $ExpectedSha256) {
    throw "TX17 image hash mismatch expected=$ExpectedSha256 actual=$ActualSha256"
}
if ($Bytes -ne $ExpectedBytes) {
    throw "TX17 image byte mismatch expected=$ExpectedBytes actual=$Bytes"
}
if ($BundleManifestSha256 -ne $ExpectedBundleManifestSha256) {
    throw "TX17 bundle manifest mismatch expected=$ExpectedBundleManifestSha256 actual=$BundleManifestSha256"
}

$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
$Bundle = Get-Content -LiteralPath $BundleManifestPath -Raw | ConvertFrom-Json
if ($Manifest.classification -ne $ExpectedClassification) {
    throw "Unexpected TX17 classification: $($Manifest.classification)"
}
if ($Manifest.flash_supported -ne $false -or $Manifest.candidate_eligible -ne $false) {
    throw 'TX17 must remain RAM-only and non-promotable'
}
if ($Manifest.slot.fits -ne $true -or $Manifest.slot.bootbase_contract -ne 'PASS') {
    throw 'TX17 Bootbase/slot contract failed'
}
if ($Bundle.static_gates.hgw500_beacon_txbd_aperture -ne 'PASS') {
    throw 'TX17 beacon aperture static gate missing'
}
$Aperture = $Bundle.experiments.hgw500_beacon_txbd_aperture
if ($Aperture.descriptor_stride_bytes -ne 32 -or $Aperture.allocated_bytes -ne 128) {
    throw 'TX17 beacon aperture manifest mismatch'
}

$Plan = [ordered]@{
    schema = 'openmitrastar.w2-tx17-ram-boot-preflight/v1'
    classification = 'PLAN-ONLY-BY-DEFAULT-RAM-BOOT-NO-FLASH'
    image = [ordered]@{ path = "work/tftp/omvl/$Filename"; bytes = $Bytes; sha256 = $ActualSha256 }
    experiment = [ordered]@{
        global_txbd = 'four 8-byte segments / bit15=0'
        all_queue_stride_bytes = 32
        beacon_aperture_bytes = 128
        own_reclaim_rate_ampdu_irq = 'unchanged'
    }
    execute_requested = [bool]$Execute
    ack_required = $AckValue
    uart_opened = $false
    reboot = $false
    bootenv = $false
    mtd = $false
    flash = $false
}
$Plan | ConvertTo-Json -Depth 6

if (-not $Execute) {
    Write-Output 'OMTX17_RAM_BOOT_PREFLIGHT_PASS=1 execute=0 flash=0'
    exit 0
}
if ($AckRamOnly -cne $AckValue) {
    throw "TX17 RAM boot execution requires exact -AckRamOnly $AckValue"
}

$Ports = [IO.Ports.SerialPort]::GetPortNames()
if (-not ($Ports -contains $Port)) { throw "$Port is not enumerated" }
$TftpEndpoint = Get-NetUDPEndpoint -LocalPort 69 -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalAddress -eq $ServerIp -or $_.LocalAddress -eq '0.0.0.0' -or $_.LocalAddress -eq '::' } |
    Select-Object -First 1
if ($null -eq $TftpEndpoint) { throw "TFTP UDP/69 is not bound on $ServerIp or 0.0.0.0" }
$Owners = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.ProcessId -ne $PID -and $_.CommandLine -match [regex]::Escape($Port) -and
        $_.CommandLine -match 'capture_topaz_uart|reboot_boot_ramssh|boot_linux510_tftp|run_w2_tx17_ram_boot'
    })
if ($Owners.Count -gt 0) { throw "$Port is already owned by UART automation: $($Owners.ProcessId -join ',')" }

$Arguments = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $BootTool,
    '-Port', $Port, '-Filename', $Filename,
    '-ServerIp', $ServerIp, '-ClientIp', $BootClientIp, '-SshHost', $SshHost,
    '-AutonomousEntropy', '-ReadyPattern', 'OMSSH_READY port=22'
)
if ($UseSshReboot) { $Arguments += '-UseSshReboot' }
& pwsh.exe @Arguments
if ($LASTEXITCODE -ne 0) { throw "TX17 RAM boot failed rc=$LASTEXITCODE" }

$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$EvidenceDir = Join-Path $Root "outputs\uart-live\w2-tx17-postboot-$Stamp-RAM-ONLY-NO-FLASH"
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null
$Remote = @'
echo OM_TX17_MARKERS_BEGIN
dmesg | grep -E 'OMRTLTX17 stage=beacon-aperture|OMRTLTX6 stage=txbd-system-width|OMRTLTX9 stage=txbd-ring'
echo OM_TX17_MARKERS_END
echo OM_TX17_HOSTAPD_BEGIN
/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status 2>/dev/null
echo OM_TX17_HOSTAPD_END
echo OM_TX17_BRIDGE_BEGIN
ls -1 /sys/class/net/br0/brif 2>/dev/null
echo OM_TX17_BRIDGE_END
echo OM_TX17_SAFETY_BEGIN
dmesg | grep -E '(^|[[:space:]])(Oops:|Kernel panic|BUG:|Misaligned Access)' || true
echo OM_TX17_SAFETY_END
'@
$Raw = & python $ExecTool --host $SshHost --timeout 30 $Remote
$Raw | Set-Content -LiteralPath (Join-Path $EvidenceDir 'postboot.txt') -Encoding UTF8
if ($LASTEXITCODE -ne 0) { throw 'TX17 postboot SSH collection failed' }
$RawText = $Raw -join "`n"
if ($RawText -notmatch 'OMRTLTX17 stage=beacon-aperture stride=32 entries=4 bytes=128 oem_offset=128') {
    throw 'TX17 beacon aperture runtime marker missing'
}
if ($RawText -notmatch 'OMRTLTX6 stage=txbd-system-width compact32=1 bit15=0') {
    throw 'TX17 global TXBD width marker missing'
}
if ($RawText -notmatch 'state=ENABLED' -or $RawText -notmatch 'ssid\[0\]=OpenMitraStar-2G-DIAG') {
    throw 'TX17 hostapd/SSID gate failed'
}
if ($RawText -notmatch '(?m)^eth0\r?$' -or $RawText -notmatch '(?m)^wlan0\r?$') {
    throw 'TX17 bridge membership gate failed'
}
$Safety = [regex]::Match($RawText, '(?s)OM_TX17_SAFETY_BEGIN\s*(.*?)\s*OM_TX17_SAFETY_END').Groups[1].Value.Trim()
if (-not [string]::IsNullOrWhiteSpace($Safety)) { throw "TX17 fatal kernel marker detected: $Safety" }

Write-Output "OMTX17_RAM_BOOT_PASS=1 sha256=$ActualSha256 evidence=$EvidenceDir flash=0"
