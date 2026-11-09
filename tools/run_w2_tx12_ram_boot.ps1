param(
    [string]$Port = 'COM3',
    [string]$ServerIp = '192.168.1.43',
    [string]$BootClientIp = '192.168.1.200',
    [string]$SshHost = '192.168.1.90',
    [switch]$UseSshReboot,
    [switch]$Execute,
    [string]$AckRamOnly = '',
    [string]$Filename = 'linux510-w2-2g-parity-tx12-mgmt-trace-v1-RAM-TEST-NO-FLASH.bin',
    [string]$ExpectedSha256 = '5feef36a0aa7c17384a0f1fec05a1940399fb3100978b9faaa526cb46fcb02c9',
    [long]$ExpectedBytes = 4333757,
    [string]$ExpectedClassification = 'RAM-ONLY-W2-2G-PARITY-TX12-MGMT-TRACE-NO-FLASH',
    [string]$ManifestRelativePath = 'work\mission-state\w2-2g-parity-tx12-mgmt-trace-v1\build\manifest.json',
    [string]$Variant = 'TX12_MGMT_TRACE',
    [string]$AckValue = 'OPENMITRASTAR_TX12_RAM_BOOT_ONLY_NO_FLASH',
    [string]$Label = 'TX12',
    [string]$MarkerPrefix = 'OMTX12'
)

$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Image = Join-Path $Root "work\tftp\omvl\$Filename"
$ManifestPath = Join-Path $Root $ManifestRelativePath
$BootTool = Join-Path $Root 'tools\reboot_boot_ramssh.ps1'

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

foreach ($Required in @($Image, $ManifestPath, $BootTool)) {
    if (-not (Test-Path -LiteralPath $Required)) { throw "Missing required input: $Required" }
}

$ActualSha256 = Get-Sha256Hex $Image
$Bytes = (Get-Item -LiteralPath $Image).Length
if ($ActualSha256 -ne $ExpectedSha256) {
    throw "$Label image hash mismatch expected=$ExpectedSha256 actual=$ActualSha256"
}
if ($Bytes -ne $ExpectedBytes) {
    throw "$Label image byte mismatch expected=$ExpectedBytes actual=$Bytes"
}
if ($Bytes -le 0 -or $Bytes -gt 0x7a0000) {
    throw "$Label image outside one linux slot: $Bytes"
}

$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
if ($Manifest.classification -ne $ExpectedClassification) {
    throw "Unexpected $Label manifest classification: $($Manifest.classification)"
}
if ($Manifest.flash_supported -ne $false -or $Manifest.candidate_eligible -ne $false) {
    throw "$Label manifest must remain no-flash and non-promotable"
}
if ($Manifest.reproducibility.fast_iteration -ne $true) {
    throw "$Label must be marked as FAST diagnostic, not sealed proof"
}
if ($Manifest.artifacts.tftp_copy.sha256 -ne $ExpectedSha256 -or $Manifest.artifacts.tftp_copy.bytes -ne $ExpectedBytes) {
    throw "$Label manifest does not bind the exact TFTP artifact"
}
if ($Manifest.slot.fits -ne $true -or $Manifest.slot.bootbase_contract -ne 'PASS') {
    throw "$Label manifest does not bind a Bootbase-PASS slot-fitting image"
}

$Report = [ordered]@{
    schema = "openmitrastar.w2-$($Label.ToLowerInvariant())-ram-boot-preflight/v1"
    classification = 'PLAN-ONLY-BY-DEFAULT-RAM-BOOT-NO-FLASH'
    image = [ordered]@{
        path = "work/tftp/omvl/$Filename"
        bytes = $Bytes
        sha256 = $ActualSha256
        variant = $Variant
        fast_iteration = $true
    }
    manifest = [ordered]@{
        classification = $Manifest.classification
        profile = $Manifest.profile
        flash_supported = [bool]$Manifest.flash_supported
        candidate_eligible = [bool]$Manifest.candidate_eligible
        bootbase_contract = $Manifest.slot.bootbase_contract
        fits = [bool]$Manifest.slot.fits
    }
    port = $Port
    tftp_server_ip = $ServerIp
    boot_client_ip = $BootClientIp
    ssh_host = $SshHost
    execute_requested = [bool]$Execute
    ack_required = $AckValue
    execution_requires = @(
        "exact acknowledgment $AckValue",
        "COM/UART $Port present and not owned by another capture",
        "TFTP UDP/69 bound on $ServerIp or 0.0.0.0",
        "RAM boot only through reboot_boot_ramssh.ps1",
        "no bootenv write, no MTD write, no flash"
    )
    uart_opened = $false
    bootenv = $false
    mtd = $false
    flash = $false
}
$Report | ConvertTo-Json -Depth 6

if (-not $Execute) {
    Write-Output "$MarkerPrefix`_RAM_BOOT_PREFLIGHT_PASS=1 execute=0 flash=0"
    return
}
if ($AckRamOnly -cne $AckValue) {
    throw "$Label RAM boot execution requires exact -AckRamOnly $AckValue"
}

$Ports = [IO.Ports.SerialPort]::GetPortNames()
if (-not ($Ports -contains $Port)) { throw "$Port is not enumerated" }
$TftpEndpoint = Get-NetUDPEndpoint -LocalPort 69 -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalAddress -eq $ServerIp -or $_.LocalAddress -eq '0.0.0.0' -or $_.LocalAddress -eq '::' } |
    Select-Object -First 1
if ($null -eq $TftpEndpoint) { throw "TFTP UDP/69 is not bound on $ServerIp or 0.0.0.0" }
$CaptureProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.ProcessId -ne $PID -and $_.CommandLine -match [regex]::Escape($Port) -and
        $_.CommandLine -match 'capture_topaz_uart|reboot_boot_ramssh|boot_linux510_tftp|run_w2_tx1[23]_ram_boot|wait_topaz_uart_marker'
    } |
    Select-Object ProcessId, Name, CommandLine)
if ($CaptureProcesses.Count -gt 0) {
    throw "$Port is already owned by a UART automation process: $($CaptureProcesses.ProcessId -join ',')"
}

$Arguments = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $BootTool,
    '-Port', $Port,
    '-Filename', $Filename,
    '-ServerIp', $ServerIp,
    '-ClientIp', $BootClientIp,
    '-SshHost', $SshHost,
    '-AutonomousEntropy',
    '-ReadyPattern', 'OMSSH_READY port=22'
)
if ($UseSshReboot) { $Arguments += '-UseSshReboot' }

& pwsh.exe @Arguments
if ($LASTEXITCODE -ne 0) { throw "$Label RAM boot failed rc=$LASTEXITCODE" }
Write-Output "$MarkerPrefix`_RAM_BOOT_PASS=1 sha256=$ActualSha256 flash=0"
