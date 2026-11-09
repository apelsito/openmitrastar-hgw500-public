param(
    [string]$HostAddress = '192.168.1.90',
    [int]$ClientWaitSeconds = 900,
    [int]$ClientPollInterval = 2,
    [int]$TrafficSeconds = 600,
    [int]$TrafficInterval = 2,
    [int]$PreSeconds = 10,
    [int]$PostSeconds = 20,
    [string]$BootLog = 'outputs/uart-live/ramssh-cycle-20260822-200834.log',
    [string]$PostbootEvidence = 'outputs/uart-live/w2-tx18-postboot-20260822-200908-RAM-ONLY-NO-FLASH/postboot.txt',
    [switch]$ExecuteGate,
    [string]$AckReadOnly = ''
)

$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Waiter = Join-Path $PSScriptRoot 'wait_w2_2g_client.py'
$CandidateGate = Join-Path $PSScriptRoot 'run_w2_2g_candidate_gate.ps1'
$ImageName = 'linux510-w2-2g-parity-tx18-beacon128-nosplit-v1-RAM-TEST-NO-FLASH.bin'
$ImageSha256 = '6a4486fa3f1e4312bee30758155d5bbbc1b732c821c9d6898f3b25f2f4164243'
$ImageBytes = 4331946
$AckValue = 'OPENMITRASTAR_TX18_CLIENT_GATE_READONLY_NO_FLASH'
$Image = Join-Path $Root "work\tftp\omvl\$ImageName"
$BootLogPath = [IO.Path]::GetFullPath((Join-Path $Root $BootLog))
$PostbootPath = [IO.Path]::GetFullPath((Join-Path $Root $PostbootEvidence))

function Get-Sha256Hex([string]$Path) {
    $GetFileHash = Get-Command Get-FileHash -ErrorAction SilentlyContinue
    if ($GetFileHash) {
        return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $Stream = [IO.File]::OpenRead($Path)
    try {
        $Sha = [Security.Cryptography.SHA256]::Create()
        try { return -join ($Sha.ComputeHash($Stream) | ForEach-Object { $_.ToString('x2') }) }
        finally { $Sha.Dispose() }
    } finally { $Stream.Dispose() }
}

foreach ($Required in @($Waiter, $CandidateGate, $Image, $BootLogPath, $PostbootPath)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing required input: $Required" }
}
$ActualHash = Get-Sha256Hex $Image
$ActualBytes = (Get-Item -LiteralPath $Image).Length
if ($ActualHash -ne $ImageSha256 -or $ActualBytes -ne $ImageBytes) { throw 'TX18 image identity mismatch' }

$BootText = Get-Content -LiteralPath $BootLogPath -Raw
$PostbootText = Get-Content -LiteralPath $PostbootPath -Raw
foreach ($RequiredText in @(
    "Filename '$ImageName'",
    'Bytes transferred = 4331946',
    'Verifying Checksum ... OK',
    'OMSSH_READY port=22 auth=ed25519-key-only forwarding=disabled'
)) {
    if (-not $BootText.Contains($RequiredText)) { throw "TX18 boot evidence missing: $RequiredText" }
}
foreach ($RequiredText in @(
    'OMRTLTX17 stage=beacon-aperture stride=32 entries=4 bytes=128 oem_offset=128',
    'OMRTLTX6 stage=txbd-system-width compact32=1 bit15=0',
    'MGMT_SPLIT=N',
    'state=ENABLED',
    'ssid[0]=OpenMitraStar-2G-DIAG'
)) {
    if (-not $PostbootText.Contains($RequiredText)) { throw "TX18 postboot evidence missing: $RequiredText" }
}

$Plan = [ordered]@{
    schema = 'openmitrastar.w2-tx18-client-gate/v1'
    classification = 'READ-ONLY-SSH-TX18-RAM-NO-FLASH'
    host = $HostAddress
    image = [ordered]@{ name = $ImageName; bytes = $ImageBytes; sha256 = $ImageSha256 }
    boot_evidence = $BootLogPath
    postboot_evidence = $PostbootPath
    client_wait_seconds = $ClientWaitSeconds
    traffic_seconds = $TrafficSeconds
    execution_requested = [bool]$ExecuteGate
    ack_required = $AckValue
    uart_opened = $false
    module_reload = $false
    reboot = $false
    bootenv = $false
    mtd = $false
    flash = $false
}
$Plan | ConvertTo-Json -Depth 6
if (-not $ExecuteGate) {
    Write-Output 'OMTX18_CLIENT_GATE_PLAN_PASS=1 execute=0 flash=0'
    exit 0
}
if ($AckReadOnly -cne $AckValue) { throw "TX18 client gate requires exact -AckReadOnly $AckValue" }

$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Evidence = Join-Path $Root "outputs\kernel-port\realtek-loop\w2-tx18-auto-gate-$Stamp-RAM-ONLY-NO-FLASH"
New-Item -ItemType Directory -Force -Path $Evidence | Out-Null
$WaitOutput = Join-Path $Evidence 'client-wait.json'
Write-Output "OMTX18_CLIENT_GATE_WAITING evidence=$Evidence"
& python $Waiter --host $HostAddress --wait-seconds $ClientWaitSeconds `
    --interval $ClientPollInterval --require-authorized --output $WaitOutput
if ($LASTEXITCODE -ne 0) {
    Write-Output "OMTX18_CLIENT_GATE_NO_CLIENT evidence=$Evidence"
    exit $LASTEXITCODE
}

Write-Output "OMTX18_CLIENT_GATE_AUTHORIZED evidence=$Evidence"
& $CandidateGate -ImageName $ImageName -ExpectedSha256 $ImageSha256 `
    -ExpectedBytes $ImageBytes -Variant 'TX18' -HostAddress $HostAddress `
    -Seconds $TrafficSeconds -Interval $TrafficInterval `
    -PreSeconds $PreSeconds -PostSeconds $PostSeconds
exit $LASTEXITCODE
