param(
    [string]$HostAddress = "192.168.1.90",
    [int]$Seconds = 600,
    [int]$Interval = 2,
    [int]$PreSeconds = 10,
    [int]$PostSeconds = 20,
    [string]$Tx9BootEvidenceJson,
    [switch]$ExecuteGate,
    [string]$AckRamOnly = ""
)

$ErrorActionPreference = "Stop"
$Audit = Join-Path $PSScriptRoot "audit_w2_tx9_candidate.py"
$BootVerifier = Join-Path $PSScriptRoot "verify_w2_tx9_boot_evidence.py"
$CandidateGate = Join-Path $PSScriptRoot "run_w2_2g_candidate_gate.ps1"
$AckValue = "OPENMITRASTAR_TX9_GLOBAL32_RX_UNALIGNED_CLIENT_GATE_RAM_ONLY"
$ImageName = "linux510-w2-2g-parity-tx9-global32-rx-unaligned-v1-RAM-TEST-NO-FLASH.bin"
$ImageSha256 = "cf101c61314a446203b3e581d00f6b32b3111bfd81bc6c2d178f526cd5c1da8a"
$ImageBytes = 4329980

foreach ($Required in @($Audit, $BootVerifier, $CandidateGate)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing input: $Required" }
}

$AuditOutput = & python $Audit
if ($LASTEXITCODE -ne 0) { throw "TX9 offline candidate audit failed" }
$AuditReport = ($AuditOutput -join "`n") | ConvertFrom-Json
if ($AuditReport.status -ne "PASS") { throw "TX9 offline candidate audit did not return PASS" }

$Plan = [ordered]@{
    schema = "openmitrastar.w2-tx9-gate-plan/v1"
    classification = "PLAN-ONLY-BY-DEFAULT-RAM-ONLY-NO-FLASH"
    host = $HostAddress
    image = [ordered]@{ name = $ImageName; bytes = $ImageBytes; sha256 = $ImageSha256 }
    candidate_audit = "PASS"
    execution_requested = [bool]$ExecuteGate
    execution_requires = @(
        "exact acknowledgment $AckValue",
        "exact TX9 RAM-boot evidence JSON for this image hash and byte count",
        "boot evidence produced by collect_w2_tx9_boot_evidence.ps1 or equivalent verifier PASS",
        "one physical client associated and authorized to OpenMitraStar-2G-DIAG",
        "BE hardware RP progress plus bidirectional traffic during the monitor window"
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
    Write-Output "OM2G_TX9_GATE_PLAN_PASS=1"
    Write-Output "OM2G_TX9_EXECUTION_LOCKED_UNTIL_EXACT_RAM_BOOT_EVIDENCE=1"
    exit 0
}

if ($AckRamOnly -cne $AckValue) { throw "TX9 execution requires exact -AckRamOnly $AckValue" }
if ([string]::IsNullOrWhiteSpace($Tx9BootEvidenceJson)) { throw "TX9 execution requires -Tx9BootEvidenceJson" }

$BootEvidencePath = [IO.Path]::GetFullPath($Tx9BootEvidenceJson)
if (-not (Test-Path -LiteralPath $BootEvidencePath -PathType Leaf)) { throw "Tx9BootEvidenceJson not found: $BootEvidencePath" }
$BootVerifyOutput = & python $BootVerifier $BootEvidencePath
if ($LASTEXITCODE -ne 0) { throw "TX9 boot evidence verifier failed" }
$BootVerifyReport = ($BootVerifyOutput -join "`n") | ConvertFrom-Json
if (-not ([bool]$BootVerifyReport.ok)) { throw "TX9 boot evidence verifier returned ok=false" }

& $CandidateGate `
    -ImageName $ImageName `
    -ExpectedSha256 $ImageSha256 `
    -ExpectedBytes $ImageBytes `
    -Variant "TX9_GLOBAL32_RX_UNALIGNED" `
    -HostAddress $HostAddress `
    -Seconds $Seconds `
    -Interval $Interval `
    -PreSeconds $PreSeconds `
    -PostSeconds $PostSeconds
exit $LASTEXITCODE
