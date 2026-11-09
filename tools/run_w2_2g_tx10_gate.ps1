param(
    [string]$HostAddress = "192.168.1.90",
    [int]$Seconds = 600,
    [int]$Interval = 2,
    [int]$ClientWaitSeconds = 300,
    [int]$ClientPollInterval = 2,
    [int]$PreSeconds = 10,
    [int]$PostSeconds = 20,
    [string]$Tx10BootEvidenceJson,
    [switch]$ExecuteGate,
    [string]$AckRamOnly = ""
)

$ErrorActionPreference = "Stop"
$Audit = Join-Path $PSScriptRoot "audit_w2_tx10_candidate.py"
$BootVerifier = Join-Path $PSScriptRoot "verify_w2_tx10_boot_evidence.py"
$CandidateGate = Join-Path $PSScriptRoot "run_w2_2g_candidate_gate.ps1"
$Waiter = Join-Path $PSScriptRoot "wait_w2_2g_client.py"
$AckValue = "OPENMITRASTAR_TX10_CONTROLS_CLIENT_GATE_RAM_ONLY"
$ImageName = if ($env:OM_W2_2G_EXPECTED_IMAGE_NAME) { $env:OM_W2_2G_EXPECTED_IMAGE_NAME } else { "linux510-w2-2g-parity-tx10-controls-v1-RAM-TEST-NO-FLASH.bin" }
$ImageSha256 = if ($env:OM_W2_2G_EXPECTED_IMAGE_SHA256) { $env:OM_W2_2G_EXPECTED_IMAGE_SHA256 } else { "998510e1aeabef6e51f953c33533a9b714251dbb5b52062d5eaa112aa431e7ee" }
$ImageBytes = if ($env:OM_W2_2G_EXPECTED_IMAGE_BYTES) { [long]$env:OM_W2_2G_EXPECTED_IMAGE_BYTES } else { 4331206 }

foreach ($Required in @($Audit, $BootVerifier, $CandidateGate, $Waiter)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing input: $Required" }
}
$AuditOutput = & python $Audit
if ($LASTEXITCODE -ne 0) { throw "TX10 offline candidate audit failed" }
$AuditReport = ($AuditOutput -join "`n") | ConvertFrom-Json
if ($AuditReport.status -ne "PASS") { throw "TX10 offline candidate audit did not return PASS" }

$Plan = [ordered]@{
    schema = "openmitrastar.w2-tx10-gate-plan/v1"
    classification = "PLAN-ONLY-BY-DEFAULT-RAM-ONLY-NO-FLASH"
    host = $HostAddress
    image = [ordered]@{ name = $ImageName; bytes = $ImageBytes; sha256 = $ImageSha256 }
    candidate_audit = "PASS"
    execution_requested = [bool]$ExecuteGate
    execution_requires = @(
        "exact acknowledgment $AckValue",
        "exact TX10 RAM-boot evidence verifier PASS",
        "wait_w2_2g_client.py observes one physical client associated and authorized to OpenMitraStar-2G-DIAG",
        "global 32-byte TXBD q0..q8",
        "no ARC misaligned exception while RX signal parsing",
        "BE hardware RP progress and bidirectional traffic"
    )
    uart_opened = $false; module_reload = $false; reboot = $false; bootenv = $false; mtd = $false; flash = $false
}
$Plan | ConvertTo-Json -Depth 6
if (-not $ExecuteGate) {
    Write-Output "OM2G_TX10_GATE_PLAN_PASS=1"
    Write-Output "OM2G_TX10_EXECUTION_LOCKED_UNTIL_EXACT_RAM_BOOT_EVIDENCE=1"
    exit 0
}
if ($AckRamOnly -cne $AckValue) { throw "TX10 execution requires exact -AckRamOnly $AckValue" }
if ([string]::IsNullOrWhiteSpace($Tx10BootEvidenceJson)) { throw "TX10 execution requires -Tx10BootEvidenceJson" }
$BootEvidencePath = [IO.Path]::GetFullPath($Tx10BootEvidenceJson)
if (-not (Test-Path -LiteralPath $BootEvidencePath -PathType Leaf)) { throw "Tx10BootEvidenceJson not found: $BootEvidencePath" }
$BootVerifyOutput = & python $BootVerifier $BootEvidencePath
if ($LASTEXITCODE -ne 0) { throw "TX10 boot evidence verifier failed" }
$BootVerifyReport = ($BootVerifyOutput -join "`n") | ConvertFrom-Json
if (-not ([bool]$BootVerifyReport.ok)) { throw "TX10 boot evidence verifier returned ok=false" }

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Evidence = [IO.Path]::GetFullPath((Join-Path $Root "outputs\kernel-port\realtek-loop\w2-tx10-controls-auto-gate-$Stamp-RAM-ONLY-NO-FLASH"))
New-Item -ItemType Directory -Force -Path $Evidence | Out-Null
$WaitOutput = Join-Path $Evidence "client-wait.json"
Write-Output "OM2G_TX10_GATE_WAITING_FOR_CLIENT evidence=$Evidence"
& python $Waiter `
    --host $HostAddress `
    --wait-seconds $ClientWaitSeconds `
    --interval $ClientPollInterval `
    --require-authorized `
    --output $WaitOutput
$WaitExit = $LASTEXITCODE
if ($WaitExit -ne 0) {
    Write-Output "OM2G_TX10_GATE_NO_CLIENT wait_exit=$WaitExit evidence=$Evidence"
    exit $WaitExit
}

& $CandidateGate -ImageName $ImageName -ExpectedSha256 $ImageSha256 -ExpectedBytes $ImageBytes `
    -Variant "TX10_CONTROLS" -HostAddress $HostAddress -Seconds $Seconds `
    -Interval $Interval -PreSeconds $PreSeconds -PostSeconds $PostSeconds
exit $LASTEXITCODE
