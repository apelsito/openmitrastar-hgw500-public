param(
    [string]$HostAddress = "192.168.1.90",
    [int]$Seconds = 600,
    [int]$Interval = 2,
    [int]$ClientWaitSeconds = 300,
    [int]$ClientPollInterval = 2,
    [int]$PreSeconds = 10,
    [int]$PostSeconds = 20,
    [string]$Tx11BootEvidenceJson,
    [switch]$ExecuteGate,
    [string]$AckRamOnly = ""
)

$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Audit = Join-Path $PSScriptRoot "audit_w2_tx10_candidate.py"
$BootVerifier = Join-Path $PSScriptRoot "verify_w2_tx10_boot_evidence.py"
$CandidateGate = Join-Path $PSScriptRoot "run_w2_2g_candidate_gate.ps1"
$Waiter = Join-Path $PSScriptRoot "wait_w2_2g_client.py"
$AckValue = "OPENMITRASTAR_TX11_CLIENT_GATE_RAM_ONLY"
$Lane = if ($env:OM_W2_2G_LANE) { $env:OM_W2_2G_LANE } else { Join-Path $Root "work\mission-state\w2-2g-parity-tx11-green-boot-controls-v1" }
$ImageName = if ($env:OM_W2_2G_EXPECTED_IMAGE_NAME) { $env:OM_W2_2G_EXPECTED_IMAGE_NAME } else { "linux510-w2-2g-parity-tx11-green-boot-controls-v1-RAM-TEST-NO-FLASH.bin" }
$ImageSha256 = if ($env:OM_W2_2G_EXPECTED_IMAGE_SHA256) { $env:OM_W2_2G_EXPECTED_IMAGE_SHA256 } else { "0ba758b8f10fb7f16237d0b21b1a489bb5895106698b3155bb3d41dc218cf95a" }
$ImageBytes = if ($env:OM_W2_2G_EXPECTED_IMAGE_BYTES) { [long]$env:OM_W2_2G_EXPECTED_IMAGE_BYTES } else { 4331749 }
$ImageVariant = if ($env:OM_W2_2G_IMAGE_VARIANT) { $env:OM_W2_2G_IMAGE_VARIANT } else { "TX11_GREEN_BOOT_CONTROLS" }
$ExpectedBootToken = if ($env:OM_W2_2G_EXPECTED_BOOT_CLASSIFICATION_TOKEN) { $env:OM_W2_2G_EXPECTED_BOOT_CLASSIFICATION_TOKEN } else { "RAM-ONLY-$ImageVariant" }
$ExpectedClassification = if ($env:OM_W2_2G_CLASSIFICATION) { $env:OM_W2_2G_CLASSIFICATION } else { "RAM-ONLY-W2-2G-PARITY-TX11-GREEN-BOOT-CONTROLS-NO-FLASH" }
$ExpectedProfile = if ($env:OM_W2_2G_PROFILE) { $env:OM_W2_2G_PROFILE } else { "W2_2G_TX11_GREEN_BOOT_CONTROLS_OPEN_DIAG" }
$Tftp = if ($env:OM_W2_2G_TFTP) { $env:OM_W2_2G_TFTP } else { Join-Path $Root "work\tftp\omvl\$ImageName" }
$Bundle = if ($env:OM_W2_2G_REALTEK_BUNDLE) { $env:OM_W2_2G_REALTEK_BUNDLE } else { Join-Path $Root "outputs\kernel-port\realtek-loop\w2-tx10-rx-signal-safe-v2-RAM-ONLY-NO-FLASH" }

foreach ($Required in @($Audit, $BootVerifier, $CandidateGate, $Waiter)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing input: $Required" }
}

$env:OM_W2_2G_EXPECTED_IMAGE_NAME = $ImageName
$env:OM_W2_2G_EXPECTED_IMAGE_SHA256 = $ImageSha256
$env:OM_W2_2G_EXPECTED_IMAGE_BYTES = [string]$ImageBytes
$env:OM_W2_2G_EXPECTED_BOOT_CLASSIFICATION_TOKEN = $ExpectedBootToken
$env:OM_W2_2G_LANE = $Lane
$env:OM_W2_2G_TFTP = $Tftp
$env:OM_W2_2G_CLASSIFICATION = $ExpectedClassification
$env:OM_W2_2G_PROFILE = $ExpectedProfile
$env:OM_W2_2G_REALTEK_BUNDLE = $Bundle

$AuditOutput = & python $Audit
if ($LASTEXITCODE -ne 0) { throw "TX11 offline candidate audit failed" }
$AuditReport = ($AuditOutput -join "`n") | ConvertFrom-Json
if ($AuditReport.status -ne "PASS") { throw "TX11 offline candidate audit did not return PASS" }

$Plan = [ordered]@{
    schema = "openmitrastar.w2-tx11-gate-plan/v1"
    classification = "PLAN-ONLY-BY-DEFAULT-RAM-ONLY-NO-FLASH"
    host = $HostAddress
    image = [ordered]@{ name = $ImageName; bytes = $ImageBytes; sha256 = $ImageSha256; variant = $ImageVariant }
    candidate_audit = "PASS"
    execution_requested = [bool]$ExecuteGate
    execution_requires = @(
        "exact acknowledgment $AckValue",
        "exact TX11 RAM-boot evidence verifier PASS",
        "wait_w2_2g_client.py observes one physical client associated and authorized to OpenMitraStar-2G-DIAG",
        "green stage0 LED observed at boot and released by userspace",
        "GPIO11 2.4 GHz LED observed only when SSID is enabled",
        "global 32-byte TXBD q0..q8",
        "no ARC misaligned exception while RX signal parsing",
        "BE hardware RP progress and bidirectional traffic"
    )
    uart_opened = $false; module_reload = $false; reboot = $false; bootenv = $false; mtd = $false; flash = $false
}
$Plan | ConvertTo-Json -Depth 6
if (-not $ExecuteGate) {
    Write-Output "OM2G_TX11_GATE_PLAN_PASS=1"
    Write-Output "OM2G_TX11_EXECUTION_LOCKED_UNTIL_EXACT_RAM_BOOT_EVIDENCE=1"
    exit 0
}
if ($AckRamOnly -cne $AckValue) { throw "TX11 execution requires exact -AckRamOnly $AckValue" }
if ([string]::IsNullOrWhiteSpace($Tx11BootEvidenceJson)) { throw "TX11 execution requires -Tx11BootEvidenceJson" }
$BootEvidencePath = [IO.Path]::GetFullPath($Tx11BootEvidenceJson)
if (-not (Test-Path -LiteralPath $BootEvidencePath -PathType Leaf)) { throw "Tx11BootEvidenceJson not found: $BootEvidencePath" }
$BootVerifyOutput = & python $BootVerifier $BootEvidencePath
if ($LASTEXITCODE -ne 0) { throw "TX11 boot evidence verifier failed" }
$BootVerifyReport = ($BootVerifyOutput -join "`n") | ConvertFrom-Json
if (-not ([bool]$BootVerifyReport.ok)) { throw "TX11 boot evidence verifier returned ok=false" }

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Evidence = [IO.Path]::GetFullPath((Join-Path $Root "outputs\kernel-port\realtek-loop\w2-tx11-client-gate-$Stamp-RAM-ONLY-NO-FLASH"))
New-Item -ItemType Directory -Force -Path $Evidence | Out-Null
$WaitOutput = Join-Path $Evidence "client-wait.json"
Write-Output "OM2G_TX11_GATE_WAITING_FOR_CLIENT evidence=$Evidence"
& python $Waiter `
    --host $HostAddress `
    --wait-seconds $ClientWaitSeconds `
    --interval $ClientPollInterval `
    --require-authorized `
    --output $WaitOutput
$WaitExit = $LASTEXITCODE
if ($WaitExit -ne 0) {
    Write-Output "OM2G_TX11_GATE_NO_CLIENT wait_exit=$WaitExit evidence=$Evidence"
    exit $WaitExit
}

& $CandidateGate -ImageName $ImageName -ExpectedSha256 $ImageSha256 -ExpectedBytes $ImageBytes `
    -Variant $ImageVariant -HostAddress $HostAddress -Seconds $Seconds `
    -Interval $Interval -PreSeconds $PreSeconds -PostSeconds $PostSeconds
exit $LASTEXITCODE
