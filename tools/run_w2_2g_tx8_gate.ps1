param(
    [string]$HostAddress = "192.168.1.90",
    [int]$Seconds = 180,
    [int]$Interval = 2,
    [int]$PreSeconds = 10,
    [int]$PostSeconds = 20,
    [string]$Tx7GateResultJson,
    [string]$Tx7FaultLog,
    [string]$Tx8BootEvidenceJson,
    [switch]$ExecuteGate,
    [string]$AckRamOnly = ""
)

$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Audit = Join-Path $PSScriptRoot "audit_w2_tx8_candidate.py"
$Tx7Verifier = Join-Path $PSScriptRoot "verify_w2_tx7_gate_for_tx8.py"
$CandidateGate = Join-Path $PSScriptRoot "run_w2_2g_candidate_gate.ps1"
$AckValue = "OPENMITRASTAR_TX8_AFTER_TX7_RX_UNALIGNED_GATE"
$ImageName = "linux510-w2-2g-parity-tx8-rx-unaligned-v1-RAM-TEST-NO-FLASH.bin"
$ImageSha256 = "387eedd890be8d22c55c6fbd3d14cb4f2e11c83ac5a72059c3edde1176d5ac19"
$ImageBytes = 4330975

foreach ($Required in @($Audit, $Tx7Verifier, $CandidateGate)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing input: $Required" }
}

$AuditOutput = & python $Audit
if ($LASTEXITCODE -ne 0) { throw "TX8 offline candidate audit failed" }
$AuditReport = ($AuditOutput -join "`n") | ConvertFrom-Json
if ($AuditReport.status -ne "PASS") { throw "TX8 offline candidate audit did not return PASS" }

$Plan = [ordered]@{
    schema = "openmitrastar.w2-tx8-gate-plan/v1"
    classification = "PLAN-ONLY-BY-DEFAULT-RAM-ONLY-NO-FLASH"
    host = $HostAddress
    image = [ordered]@{ name = $ImageName; bytes = $ImageBytes; sha256 = $ImageSha256 }
    candidate_audit = "PASS"
    execution_requested = [bool]$ExecuteGate
    execution_requires = @(
        "exact acknowledgment $AckValue",
        "TX7 client gate: associated+authorized terminal FAIL, not NO_CLIENT/NO_AUTH",
        "exact TX7 RX-unaligned fault proof",
        "exact TX8 RAM-boot evidence JSON"
    )
    uart_opened = $false
    module_reload = $false
    reboot = $false
    bootenv = $false
    mtd = $false
    flash = $false
}
$Plan | ConvertTo-Json -Depth 6

if (-not $ExecuteGate) {
    Write-Output "OM2G_TX8_GATE_PLAN_PASS=1"
    Write-Output "OM2G_TX8_EXECUTION_LOCKED_UNTIL_TX7_CLIENT_RX_UNALIGNED_PROOF=1"
    exit 0
}

if ($AckRamOnly -cne $AckValue) { throw "TX8 execution requires exact -AckRamOnly $AckValue" }
if ([string]::IsNullOrWhiteSpace($Tx7GateResultJson)) { throw "TX8 execution requires -Tx7GateResultJson" }
if ([string]::IsNullOrWhiteSpace($Tx8BootEvidenceJson)) { throw "TX8 execution requires -Tx8BootEvidenceJson" }

$VerifierArgs = @($Tx7Verifier, [IO.Path]::GetFullPath($Tx7GateResultJson))
if (-not [string]::IsNullOrWhiteSpace($Tx7FaultLog)) {
    $VerifierArgs += @("--fault-log", [IO.Path]::GetFullPath($Tx7FaultLog))
}
$Tx7ProofOutput = & python @VerifierArgs
if ($LASTEXITCODE -ne 0) { throw "TX7 client gate does not justify TX8" }
$Tx7Proof = ($Tx7ProofOutput -join "`n") | ConvertFrom-Json
if (-not ([bool]$Tx7Proof.ok)) { throw "TX7 proof returned ok=false" }

$BootEvidencePath = [IO.Path]::GetFullPath($Tx8BootEvidenceJson)
if (-not (Test-Path -LiteralPath $BootEvidencePath -PathType Leaf)) { throw "Tx8BootEvidenceJson not found: $BootEvidencePath" }
$BootEvidence = Get-Content -LiteralPath $BootEvidencePath -Raw | ConvertFrom-Json
if ($BootEvidence.schema -ne "openmitrastar.w2-2g-client-evidence/v1") { throw "Unexpected TX8 boot evidence schema" }
if ($BootEvidence.image.sha256 -ne $ImageSha256 -or [long]$BootEvidence.image.bytes -ne $ImageBytes) {
    throw "TX8 boot evidence image identity mismatch"
}
if ($BootEvidence.classification -notmatch 'RAM-ONLY-TX8') { throw "TX8 boot evidence classification mismatch" }
if ([bool]$BootEvidence.flash -or [bool]$BootEvidence.mutations) { throw "TX8 boot evidence reports mutations/flash" }

& $CandidateGate `
    -ImageName $ImageName `
    -ExpectedSha256 $ImageSha256 `
    -ExpectedBytes $ImageBytes `
    -Variant "TX8_RX_UNALIGNED" `
    -HostAddress $HostAddress `
    -Seconds $Seconds `
    -Interval $Interval `
    -PreSeconds $PreSeconds `
    -PostSeconds $PostSeconds
exit $LASTEXITCODE
