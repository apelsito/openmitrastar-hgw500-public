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
$AckValue = "OPENMITRASTAR_COLLECT_TX11_BOOT_EVIDENCE_READONLY"
$ImageName = if ($env:OM_W2_2G_EXPECTED_IMAGE_NAME) { $env:OM_W2_2G_EXPECTED_IMAGE_NAME } else { "linux510-w2-2g-parity-tx11-green-boot-controls-v1-RAM-TEST-NO-FLASH.bin" }
$ImagePath = "work/tftp/omvl/$ImageName"
$ImageSha256 = if ($env:OM_W2_2G_EXPECTED_IMAGE_SHA256) { $env:OM_W2_2G_EXPECTED_IMAGE_SHA256 } else { "0ba758b8f10fb7f16237d0b21b1a489bb5895106698b3155bb3d41dc218cf95a" }
$ImageBytes = if ($env:OM_W2_2G_EXPECTED_IMAGE_BYTES) { [long]$env:OM_W2_2G_EXPECTED_IMAGE_BYTES } else { 4331749 }
$ImageVariant = if ($env:OM_W2_2G_IMAGE_VARIANT) { $env:OM_W2_2G_IMAGE_VARIANT } else { "TX11_GREEN_BOOT_CONTROLS" }
$ExpectedBootToken = if ($env:OM_W2_2G_EXPECTED_BOOT_CLASSIFICATION_TOKEN) { $env:OM_W2_2G_EXPECTED_BOOT_CLASSIFICATION_TOKEN } else { "RAM-ONLY-$ImageVariant" }

foreach ($Required in @($Collector, $Verifier)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing input: $Required" }
}
if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $Root "outputs\uart-live\w2-tx11-boot-evidence-latest.json"
}
$OutputPath = [IO.Path]::GetFullPath($Output)
$RawOutputPath = [IO.Path]::ChangeExtension($OutputPath, ".raw.txt")
$VerifierStdout = [IO.Path]::ChangeExtension($OutputPath, ".verifier.stdout.json")
$VerifierStderr = [IO.Path]::ChangeExtension($OutputPath, ".verifier.stderr.txt")

$Plan = [ordered]@{
    schema = "openmitrastar.w2-tx11-boot-evidence-collection-plan/v1"
    classification = "PLAN-ONLY-BY-DEFAULT-READONLY-SSH-NO-FLASH"
    host = $HostAddress
    output = $OutputPath
    image = [ordered]@{ path = $ImagePath; bytes = $ImageBytes; sha256 = $ImageSha256; variant = $ImageVariant }
    execution_requested = [bool]$ExecuteCollection
    execution_requires = @(
        "exact acknowledgment $AckValue",
        "router already RAM-booted with the exact TX11 image",
        "no COM, reboot, module reload, bootenv, MTD or flash"
    )
    uart_opened = $false; module_reload = $false; reboot = $false; bootenv = $false; mtd = $false; flash = $false
}
$Plan | ConvertTo-Json -Depth 6
if (-not $ExecuteCollection) {
    Write-Output "OMTX11_BOOT_EVIDENCE_COLLECTION_PLAN_PASS=1"
    Write-Output "OMTX11_BOOT_EVIDENCE_COLLECTION_LOCKED_UNTIL_ACK=1"
    exit 0
}
if ($AckReadOnly -cne $AckValue) { throw "TX11 boot evidence collection requires exact -AckReadOnly $AckValue" }

New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($OutputPath)) | Out-Null
& python $Collector --host $HostAddress --timeout $Timeout --irq-window $IrqWindow `
    --duration-seconds 0 --be-queue-max 512 --image-path $ImagePath `
    --image-sha256 $ImageSha256 --image-bytes $ImageBytes --image-variant $ImageVariant `
    --output $OutputPath --raw-output $RawOutputPath
if ($LASTEXITCODE -ne 0) { throw "TX11 boot evidence collector failed: $LASTEXITCODE" }
$env:OM_W2_2G_EXPECTED_IMAGE_NAME = $ImageName
$env:OM_W2_2G_EXPECTED_IMAGE_SHA256 = $ImageSha256
$env:OM_W2_2G_EXPECTED_IMAGE_BYTES = [string]$ImageBytes
$env:OM_W2_2G_EXPECTED_BOOT_CLASSIFICATION_TOKEN = $ExpectedBootToken
& python $Verifier $OutputPath > $VerifierStdout 2> $VerifierStderr
if ($LASTEXITCODE -ne 0) { throw "TX11 boot evidence verifier failed: $LASTEXITCODE" }
$Report = Get-Content -LiteralPath $VerifierStdout -Raw | ConvertFrom-Json
if (-not ([bool]$Report.ok)) { throw "TX11 boot evidence verifier returned ok=false" }
Write-Output "OMTX11_BOOT_EVIDENCE_VERIFIED=1 path=$OutputPath"
