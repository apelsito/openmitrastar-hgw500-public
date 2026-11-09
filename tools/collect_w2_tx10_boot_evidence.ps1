param(
    [string]$HostAddress = "192.168.1.90",
    [string]$Output = "",
    [int]$Timeout = 30,
    [int]$IrqWindow = 2,
    [switch]$ExecuteCollection,
    [string]$AckReadOnly = ""
)

$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Collector = Join-Path $PSScriptRoot "collect_w2_2g_client_gate.py"
$Verifier = Join-Path $PSScriptRoot "verify_w2_tx10_boot_evidence.py"
$AckValue = "OPENMITRASTAR_COLLECT_TX10_BOOT_EVIDENCE_READONLY"
$ImagePath = if ($env:OM_W2_2G_EXPECTED_IMAGE_NAME) { "work/tftp/omvl/$($env:OM_W2_2G_EXPECTED_IMAGE_NAME)" } else { "work/tftp/omvl/linux510-w2-2g-parity-tx10-controls-v1-RAM-TEST-NO-FLASH.bin" }
$ImageSha256 = if ($env:OM_W2_2G_EXPECTED_IMAGE_SHA256) { $env:OM_W2_2G_EXPECTED_IMAGE_SHA256 } else { "998510e1aeabef6e51f953c33533a9b714251dbb5b52062d5eaa112aa431e7ee" }
$ImageBytes = if ($env:OM_W2_2G_EXPECTED_IMAGE_BYTES) { [long]$env:OM_W2_2G_EXPECTED_IMAGE_BYTES } else { 4331206 }

foreach ($Required in @($Collector, $Verifier)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing input: $Required" }
}
if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $Root "outputs\uart-live\w2-tx10-boot-evidence-latest.json"
}
$OutputPath = [IO.Path]::GetFullPath($Output)
$RawOutputPath = [IO.Path]::ChangeExtension($OutputPath, ".raw.txt")
$VerifierStdout = [IO.Path]::ChangeExtension($OutputPath, ".verifier.stdout.json")
$VerifierStderr = [IO.Path]::ChangeExtension($OutputPath, ".verifier.stderr.txt")

$Plan = [ordered]@{
    schema = "openmitrastar.w2-tx10-boot-evidence-collection-plan/v1"
    classification = "PLAN-ONLY-BY-DEFAULT-READONLY-SSH-NO-FLASH"
    host = $HostAddress
    output = $OutputPath
    image = [ordered]@{ path = $ImagePath; bytes = $ImageBytes; sha256 = $ImageSha256 }
    execution_requested = [bool]$ExecuteCollection
    execution_requires = @(
        "exact acknowledgment $AckValue",
        "router already RAM-booted with the exact TX10 image",
        "no COM, reboot, module reload, bootenv, MTD or flash"
    )
    uart_opened = $false; module_reload = $false; reboot = $false; bootenv = $false; mtd = $false; flash = $false
}
$Plan | ConvertTo-Json -Depth 6
if (-not $ExecuteCollection) {
    Write-Output "OMTX10_BOOT_EVIDENCE_COLLECTION_PLAN_PASS=1"
    Write-Output "OMTX10_BOOT_EVIDENCE_COLLECTION_LOCKED_UNTIL_ACK=1"
    exit 0
}
if ($AckReadOnly -cne $AckValue) { throw "TX10 boot evidence collection requires exact -AckReadOnly $AckValue" }

New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($OutputPath)) | Out-Null
& python $Collector --host $HostAddress --timeout $Timeout --irq-window $IrqWindow `
    --duration-seconds 0 --be-queue-max 512 --image-path $ImagePath `
    --image-sha256 $ImageSha256 --image-bytes $ImageBytes --image-variant "TX10_CONTROLS" `
    --output $OutputPath --raw-output $RawOutputPath
if ($LASTEXITCODE -ne 0) { throw "TX10 boot evidence collector failed: $LASTEXITCODE" }
& python $Verifier $OutputPath > $VerifierStdout 2> $VerifierStderr
if ($LASTEXITCODE -ne 0) { throw "TX10 boot evidence verifier failed: $LASTEXITCODE" }
$Report = Get-Content -LiteralPath $VerifierStdout -Raw | ConvertFrom-Json
if (-not ([bool]$Report.ok)) { throw "TX10 boot evidence verifier returned ok=false" }
Write-Output "OMTX10_BOOT_EVIDENCE_VERIFIED=1 path=$OutputPath"
