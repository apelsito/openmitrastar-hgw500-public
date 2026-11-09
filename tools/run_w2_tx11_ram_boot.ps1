param(
    [string]$Port = 'COM3',
    [string]$ServerIp = '192.168.1.43',
    [string]$BootClientIp = '192.168.1.200',
    [string]$SshHost = '192.168.1.90',
    [switch]$UseSshReboot,
    [switch]$Execute,
    [string]$AckRamOnly = ''
)

$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Filename = 'linux510-w2-2g-parity-tx11-green-boot-controls-v1-RAM-TEST-NO-FLASH.bin'
$ExpectedSha256 = '0ba758b8f10fb7f16237d0b21b1a489bb5895106698b3155bb3d41dc218cf95a'
$ExpectedBytes = 4331749
$AckValue = 'OPENMITRASTAR_TX11_RAM_BOOT_ONLY_NO_FLASH'
$Image = Join-Path $Root "work\tftp\omvl\$Filename"
$ManifestPath = Join-Path $Root 'work\mission-state\w2-2g-parity-tx11-green-boot-controls-v1\build\manifest.json'
$BootTool = Join-Path $Root 'tools\reboot_boot_ramssh.ps1'

foreach ($Required in @($Image, $ManifestPath, $BootTool)) {
    if (-not (Test-Path -LiteralPath $Required)) { throw "Missing required input: $Required" }
}

$ActualSha256 = (Get-FileHash -LiteralPath $Image -Algorithm SHA256).Hash.ToLowerInvariant()
$Bytes = (Get-Item -LiteralPath $Image).Length
if ($ActualSha256 -ne $ExpectedSha256) {
    throw "TX11 image hash mismatch expected=$ExpectedSha256 actual=$ActualSha256"
}
if ($Bytes -ne $ExpectedBytes) {
    throw "TX11 image byte mismatch expected=$ExpectedBytes actual=$Bytes"
}
if ($Bytes -le 0 -or $Bytes -gt 0x7a0000) {
    throw "TX11 image outside one linux slot: $Bytes"
}

$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
if ($Manifest.classification -ne 'RAM-ONLY-W2-2G-PARITY-TX11-GREEN-BOOT-CONTROLS-NO-FLASH') {
    throw "Unexpected TX11 manifest classification: $($Manifest.classification)"
}
if ($Manifest.flash_supported -ne $false -or $Manifest.candidate_eligible -ne $false) {
    throw "TX11 manifest must remain no-flash and non-promotable"
}
if ($Manifest.artifacts.tftp_copy.sha256 -ne $ExpectedSha256 -or $Manifest.artifacts.tftp_copy.bytes -ne $ExpectedBytes) {
    throw "TX11 manifest does not bind the exact TFTP artifact"
}
if ($Manifest.slot.fits -ne $true -or $Manifest.slot.bootbase_contract -ne 'PASS') {
    throw "TX11 manifest does not bind a Bootbase-PASS slot-fitting image"
}

$Ports = [IO.Ports.SerialPort]::GetPortNames()
$SerialPresent = $Ports -contains $Port
$TftpEndpoint = Get-NetUDPEndpoint -LocalPort 69 -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalAddress -eq $ServerIp -or $_.LocalAddress -eq '0.0.0.0' -or $_.LocalAddress -eq '::' } |
    Select-Object -First 1
$CaptureProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.ProcessId -ne $PID -and $_.CommandLine -match [regex]::Escape($Port) -and
        $_.CommandLine -match 'capture_topaz_uart|reboot_boot_ramssh|boot_linux510_tftp|run_w2_tx11_ram_boot|wait_topaz_uart_marker'
    } |
    Select-Object ProcessId, Name, CommandLine)

$Report = [ordered]@{
    schema = 'openmitrastar.w2-tx11-ram-boot-preflight/v1'
    classification = 'PLAN-ONLY-BY-DEFAULT-RAM-BOOT-NO-FLASH'
    image = [ordered]@{
        path = "work/tftp/omvl/$Filename"
        bytes = $Bytes
        sha256 = $ActualSha256
        variant = 'TX11_GREEN_BOOT_CONTROLS'
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
    serial_present = $SerialPresent
    serial_users = @($CaptureProcesses | ForEach-Object { $_.ProcessId })
    tftp_server_ip = $ServerIp
    tftp_udp69_ready = $null -ne $TftpEndpoint
    boot_client_ip = $BootClientIp
    ssh_host = $SshHost
    execute_requested = [bool]$Execute
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

if (-not $SerialPresent) { throw "$Port is not enumerated" }
if ($null -eq $TftpEndpoint) { throw "TFTP UDP/69 is not bound on $ServerIp or 0.0.0.0" }
if ($CaptureProcesses.Count -gt 0) {
    throw "$Port is already owned by a UART automation process: $($CaptureProcesses.ProcessId -join ',')"
}
if (-not $Execute) {
    Write-Output 'OMTX11_RAM_BOOT_PREFLIGHT_PASS=1 execute=0 flash=0'
    exit 0
}
if ($AckRamOnly -cne $AckValue) {
    throw "TX11 RAM boot execution requires exact -AckRamOnly $AckValue"
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
if ($LASTEXITCODE -ne 0) { throw "TX11 RAM boot failed rc=$LASTEXITCODE" }
Write-Output "OMTX11_RAM_BOOT_PASS=1 sha256=$ActualSha256 flash=0"
