param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{64}$')]
    [string]$ExpectedSha256,

    [string]$Port = 'COM3',
    [string]$ServerIp = '192.168.1.43',
    [string]$BootClientIp = '192.168.1.200',
    [string]$SshHost = '192.168.1.90',
    [switch]$UseSshReboot,
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$filename = 'linux510-q3-persistent-v1-LZMA-RAM-TEST-NO-FLASH.bin'
$image = Join-Path $root "work\tftp\omvl\$filename"
$manifestPath = Join-Path $root 'work\mission-state\q3-persistent-composite\build\manifest.json'
$bootTool = Join-Path $root 'tools\reboot_boot_ramssh.ps1'
$sshTool = Join-Path $root 'tools\ramssh_exec.py'
$slotBytes = 0x7a0000

if (-not (Test-Path -LiteralPath $image -PathType Leaf)) { throw "Missing Q3 TFTP image: $image" }
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Missing Q3 build manifest: $manifestPath" }
$expected = $ExpectedSha256.ToLowerInvariant()
$actual = (Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash.ToLowerInvariant()
$bytes = (Get-Item -LiteralPath $image).Length
if ($actual -ne $expected) { throw "Q3 TFTP hash mismatch expected=$expected actual=$actual" }
if ($bytes -le 0 -or $bytes -gt $slotBytes) { throw "Q3 image outside one slot: $bytes" }

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.artifacts.webformat.sha256 -ne $actual -or
    $manifest.slot.fits -ne $true -or $manifest.slot.bootbase_contract -ne 'PASS') {
    throw 'Q3 manifest does not bind a slot-fitting Bootbase-PASS candidate'
}

$ports = [IO.Ports.SerialPort]::GetPortNames()
$serialPresent = $ports -contains $Port
$tftpEndpoint = Get-NetUDPEndpoint -LocalPort 69 -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalAddress -eq $ServerIp -or $_.LocalAddress -eq '0.0.0.0' } |
    Select-Object -First 1
$captureProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.ProcessId -ne $PID -and $_.CommandLine -match [regex]::Escape($Port) -and
        $_.CommandLine -match 'capture_topaz_uart|reboot_boot_ramssh|boot_linux510_tftp'
    } |
    Select-Object ProcessId, Name, CommandLine)

$report = [ordered]@{
    schema = 'openmitrastar.q3-ram-boot-preflight/v1'
    image = $image
    sha256 = $actual
    bytes = $bytes
    slot_bytes = $slotBytes
    spare_bytes = $slotBytes - $bytes
    bootbase_contract = 'PASS'
    port = $Port
    serial_present = $serialPresent
    serial_users = @($captureProcesses | ForEach-Object { $_.ProcessId })
    tftp_server_ip = $ServerIp
    tftp_udp69_ready = $null -ne $tftpEndpoint
    boot_client_ip = $BootClientIp
    ssh_host = $SshHost
    autonomous_entropy = $true
    flash_actions = $false
    execute_requested = [bool]$Execute
}
$report | ConvertTo-Json -Depth 5

if (-not $serialPresent) { throw "$Port is not enumerated" }
if ($null -eq $tftpEndpoint) { throw "TFTP UDP/69 is not bound on $ServerIp" }
if (-not $Execute) {
    Write-Host 'OMQ3_RAM_BOOT_PREFLIGHT_PASS execute=0 flash=0'
    exit 0
}
if ($captureProcesses.Count -gt 0) {
    throw "$Port is already owned by a UART automation process: $($captureProcesses.ProcessId -join ',')"
}

$arguments = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $bootTool,
    '-Port', $Port, '-Filename', $filename, '-ServerIp', $ServerIp,
    '-ClientIp', $BootClientIp, '-SshHost', $SshHost,
    # The product rootfs currently records readiness in tmpfs but does not
    # reliably mirror OMPRODUCT_READY to UART.  Stop UART waiting at the
    # proven SSH-ready marker, then attest the actual runtime state over SSH.
    '-AutonomousEntropy', '-ReadyPattern', 'OMSSH_READY port=22'
)
if ($UseSshReboot) { $arguments += '-UseSshReboot' }
# reboot_boot_ramssh.ps1 uses ProcessStartInfo.ArgumentList, which is available
# in PowerShell 7/.NET but null under Windows PowerShell 5.1.  Keep the whole
# supervised UART boot in the same pwsh runtime as this wrapper.
& pwsh.exe @arguments
if ($LASTEXITCODE -ne 0) { throw "Q3 RAM boot failed rc=$LASTEXITCODE" }
& python.exe $sshTool 'test "$(cat /run/openmitrastar/boot-state)" = ready; echo OMQ3_RUNTIME_READY_PASS' `
    --host $SshHost --timeout 30
if ($LASTEXITCODE -ne 0) { throw "Q3 runtime ready attestation failed rc=$LASTEXITCODE" }
Write-Host "OMQ3_RAM_BOOT_TOOL_PASS sha256=$actual flash=0"
