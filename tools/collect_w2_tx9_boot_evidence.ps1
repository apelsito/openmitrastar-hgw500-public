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
$Verifier = Join-Path $PSScriptRoot "verify_w2_tx9_boot_evidence.py"
$AckValue = "OPENMITRASTAR_COLLECT_TX9_BOOT_EVIDENCE_READONLY"
$ImagePath = "work/tftp/omvl/linux510-w2-2g-parity-tx9-global32-rx-unaligned-v1-RAM-TEST-NO-FLASH.bin"
$ImageSha256 = "cf101c61314a446203b3e581d00f6b32b3111bfd81bc6c2d178f526cd5c1da8a"
$ImageBytes = 4329980

foreach ($Required in @($Collector, $Verifier)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing input: $Required" }
}

if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $Root "outputs\uart-live\w2-tx9-boot-evidence-latest.json"
}
$OutputPath = [IO.Path]::GetFullPath($Output)
$RawOutputPath = [IO.Path]::ChangeExtension($OutputPath, ".raw.txt")
$VerifierStdout = [IO.Path]::ChangeExtension($OutputPath, ".verifier.stdout.json")
$VerifierStderr = [IO.Path]::ChangeExtension($OutputPath, ".verifier.stderr.txt")

$Plan = [ordered]@{
    schema = "openmitrastar.w2-tx9-boot-evidence-collection-plan/v1"
    classification = "PLAN-ONLY-BY-DEFAULT-READONLY-SSH-NO-FLASH"
    host = $HostAddress
    output = $OutputPath
    raw_output = $RawOutputPath
    verifier_stdout = $VerifierStdout
    image = [ordered]@{ path = $ImagePath; bytes = $ImageBytes; sha256 = $ImageSha256 }
    execution_requested = [bool]$ExecuteCollection
    execution_requires = @(
        "exact acknowledgment $AckValue",
        "router reachable over existing RAM SSH at $HostAddress",
        "no COM, no reboot, no module reload, no bootenv, no MTD and no flash"
    )
    uart_opened = $false
    module_reload = $false
    reboot = $false
    bootenv = $false
    mtd = $false
    flash = $false
}
$Plan | ConvertTo-Json -Depth 6

if (-not $ExecuteCollection) {
    Write-Output "OMTX9_BOOT_EVIDENCE_COLLECTION_PLAN_PASS=1"
    Write-Output "OMTX9_BOOT_EVIDENCE_COLLECTION_LOCKED_UNTIL_ACK=1"
    exit 0
}

if ($AckReadOnly -cne $AckValue) { throw "TX9 boot evidence collection requires exact -AckReadOnly $AckValue" }

New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($OutputPath)) | Out-Null

& python $Collector `
    --host $HostAddress `
    --timeout $Timeout `
    --irq-window $IrqWindow `
    --duration-seconds 0 `
    --be-queue-max 512 `
    --image-path $ImagePath `
    --image-sha256 $ImageSha256 `
    --image-bytes $ImageBytes `
    --image-variant "TX9" `
    --output $OutputPath `
    --raw-output $RawOutputPath
$CollectorExit = $LASTEXITCODE
if ($CollectorExit -ne 0) { throw "TX9 boot evidence collector failed: $CollectorExit" }

& python $Verifier $OutputPath > $VerifierStdout 2> $VerifierStderr
$VerifierExit = $LASTEXITCODE
if ($VerifierExit -ne 0) { throw "TX9 boot evidence verifier failed: $VerifierExit" }
$Report = Get-Content -LiteralPath $VerifierStdout -Raw | ConvertFrom-Json
if (-not ([bool]$Report.ok)) { throw "TX9 boot evidence verifier returned ok=false" }

Write-Output "OMTX9_BOOT_EVIDENCE_VERIFIED=1 path=$OutputPath"
