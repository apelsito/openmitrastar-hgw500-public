[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$RouterHost = "192.168.1.90",
    [string]$OracleHost = "192.168.1.63",
    [string]$OracleUser = "AELITA",
    [string]$TftpHost = "192.168.1.43",
    [ValidateSet("auto", "tftp", "uart-ymodem")][string]$Transport = "auto",
    [string]$WebPasswordFile = "",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$requiredAck = "OPENMITRASTAR_F301_FLASH_TEST_ROLLBACK_4C280E84"
$f301Sha = "4c280e84b4593008b900cec70041b801d204bdde748b09064410708253b87262"
$f301FullCrc = "2483522f"
$f301FullSha = "c9c98d000fa9ea1c2fd53738e97decf83ef9a21132b382a23df03121fac1577b"
$currentF301PreviousFullCrc = "626a7e0d"
$currentF301PreviousFullSha = "aa07a2960304497d745e412292fc93a0bf20bb276ffabb6c50a2c908ab5a7d37"
$f300Sha = "734bba8ad1b706c0c17ad5e73341cbb7c7a5c4d78cf05e069d955705d789edbb"
$f300FullCrc = "841f11c8"
$f300FullSha = "fb7867874640a428124a18be38b8521e52e5d27322393f88ab44bbd6d17baf9b"
$f301Build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f301-device-bound"
$promoter = Join-Path $root "tools\promote_f301_mtd4_direct.ps1"
$campaign = Join-Path $root "tools\run_f301_physical_campaign.ps1"
$rollback = Join-Path $root "tools\rollback_f301_to_f300_mtd4.ps1"

function Invoke-DryRun([string]$Script, [string[]]$Arguments) {
    $text = (& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script @Arguments | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "offline dry-run failed: $Script" }
    return $text | ConvertFrom-Json
}

function Test-F301FlashCompleted([datetime]$StartedUtc) {
    $latest = Get-ChildItem -LiteralPath $f301Build -Directory -Filter "flash-one-shot-*" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTimeUtc -ge $StartedUtc.AddSeconds(-5) } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if (-not $latest) { return $false }
    $resultPath = Join-Path $latest.FullName "result.json"
    if (-not (Test-Path -LiteralPath $resultPath)) { return $false }
    $payload = Get-Content -Raw -LiteralPath $resultPath | ConvertFrom-Json
    $result = if ($payload.result) { $payload.result } else { $payload }
    return (
        $result.status -eq "PASS" -and
        $result.candidate_sha256 -eq $f301Sha -and
        $result.readback.full_slot_crc32 -eq $f301FullCrc -and
        $result.readback.full_slot_sha256 -eq $f301FullSha -and
        $result.physical_write.partition -eq "mtd4/linux_live" -and
        $result.protected_partitions.status -eq "PASS"
    )
}

$promoteArgs = @("-Port", $Port, "-RouterHost", $RouterHost, "-TftpHost", $TftpHost, "-Transport", $Transport)
if ($WebPasswordFile) { $promoteArgs += @("-WebPasswordFile", $WebPasswordFile) }
$promotePlan = Invoke-DryRun $promoter $promoteArgs
$campaignPlan = Invoke-DryRun $campaign @(
    "-RouterHost", $RouterHost, "-OracleHost", $OracleHost, "-OracleUser", $OracleUser
)
$rollbackPlan = Invoke-DryRun $rollback @(
    "-Port", $Port, "-RouterHost", $RouterHost, "-TftpHost", $TftpHost, "-Transport", $Transport
)
$ready = (
    $promotePlan.target -eq "mtd4/linux_live" -and
    $promotePlan.sha256 -eq $f301Sha -and
    $promotePlan.bytes -eq 5267456 -and
    $promotePlan.full_slot_crc32 -eq $f301FullCrc -and
    $promotePlan.full_slot_sha256 -eq $f301FullSha -and
    $promotePlan.expected_current_full_slot_crc32 -eq $currentF301PreviousFullCrc -and
    $promotePlan.expected_current_full_slot_sha256 -eq $currentF301PreviousFullSha -and
    @($promotePlan.authenticated_api_endpoints).Count -eq 6 -and
    $promotePlan.live_asset_hash_count -eq 7 -and
    $promotePlan.capability_rows -eq 23 -and
    $campaignPlan.candidate_sha256 -eq $f301Sha -and
    $campaignPlan.realtek_runs -eq 1 -and
    $campaignPlan.realtek_bytes_per_direction -eq 33554432 -and
    $campaignPlan.radio5_profile -eq "f301" -and
    $campaignPlan.radio5_bytes_per_direction -eq 33554432 -and
    $campaignPlan.radio5_soak_seconds -eq 120 -and
    $campaignPlan.final_health.monolithic_command -eq $false -and
    $campaignPlan.final_health.retries_per_read -eq 5 -and
    $rollbackPlan.target -eq "mtd4/linux_live" -and
    $rollbackPlan.sha256 -eq $f300Sha -and
    $rollbackPlan.bytes -eq 5259264 -and
    $rollbackPlan.full_slot_crc32 -eq $f300FullCrc -and
    $rollbackPlan.full_slot_sha256 -eq $f300FullSha -and
    $rollbackPlan.expected_current_full_slot_crc32 -eq $f301FullCrc -and
    $rollbackPlan.expected_current_full_slot_sha256 -eq $f301FullSha
)

[ordered]@{
    schema = "openmitrastar.f301-flash-test-rollback-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    ready = $ready
    flash = @{
        target = "mtd4/linux_live"
        sha256 = $f301Sha
        bytes = 5267456
        full_slot_crc32 = $f301FullCrc
        full_slot_sha256 = $f301FullSha
        transport = $Transport
    }
    postflash = @{
        platform_gate = $true
        authenticated_api_endpoints = @("status", "firmware", "frontend", "capabilities", "diagnostics", "storage")
        live_asset_hashes = 7
        capability_rows = 23
        f300_metrics = $true
        store_observer_disabled = $true
        multicast_available = $true
    }
    test = @{
        realtek_runs = 1
        bytes_per_direction = 33554432
        radio5_profile = "f301"
        radio5_soak_seconds = 120
        final_health_separate_reads = $true
        retries_per_read = 5
    }
    rollback = @{
        automatic_on_any_non_pass = $true
        target = "mtd4/linux_live"
        sha256 = $f300Sha
        bytes = 5259264
        full_slot_crc32 = $f300FullCrc
        full_slot_sha256 = $f300FullSha
    }
    protected_partitions = @("mtd0", "mtd1", "mtd2", "mtd3", "mtd5")
    hardware_actions_performed = $false
} | ConvertTo-Json -Depth 7

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing campaign: exact -Ack is required" }
if (-not $ready) { throw "F301 offline campaign contract is not ready" }

if (-not $OutputDir) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $OutputDir = Join-Path $root "outputs\campaign\f301-flash-test-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$started = [DateTime]::UtcNow
$promoted = $false
$campaignPassed = $false
$rollbackAttempted = $false
$rollbackPassed = $false
$failure = ""

try {
    $executePromoteArgs = @(
        "-Execute", "-Ack", "OPENMITRASTAR_F301_LOGIN_REDIRECT_4C280E84",
        "-Port", $Port, "-RouterHost", $RouterHost, "-TftpHost", $TftpHost, "-Transport", $Transport
    )
    if ($WebPasswordFile) { $executePromoteArgs += @("-WebPasswordFile", $WebPasswordFile) }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $promoter @executePromoteArgs `
        2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "promotion.log")
    if ($LASTEXITCODE -ne 0) {
        $promoted = Test-F301FlashCompleted $started
        throw "F301 promotion or post-flash gate failed"
    }
    $promoted = $true

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $campaign `
        -Execute -Ack OPENMITRASTAR_F301_INTEGRATED_PHYSICAL `
        -RouterHost $RouterHost -OracleHost $OracleHost -OracleUser $OracleUser `
        -OutputDir (Join-Path $OutputDir "physical") `
        2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "campaign.log")
    if ($LASTEXITCODE -ne 0) { throw "F301 physical campaign did not PASS" }
    $campaignData = Get-Content -Raw -LiteralPath (Join-Path $OutputDir "physical\campaign.json") | ConvertFrom-Json
    if ($campaignData.status -ne "PASS") { throw "F301 physical campaign result is not PASS" }
    $campaignPassed = $true
} catch {
    $failure = $_.Exception.Message
    if ($promoted) {
        $rollbackAttempted = $true
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $rollback `
            -Execute -Ack OPENMITRASTAR_ROLLBACK_F301_TO_F300_734BBA8A `
            -Port $Port -RouterHost $RouterHost -TftpHost $TftpHost -Transport $Transport `
            2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "rollback.log")
        $rollbackPassed = $LASTEXITCODE -eq 0
    }
} finally {
    $status = if ($campaignPassed) {
        "PASS"
    } elseif ($rollbackAttempted -and $rollbackPassed) {
        "ROLLED_BACK_AFTER_NON_PASS"
    } elseif ($promoted) {
        "MANUAL_RECOVERY_REQUIRED"
    } else {
        "PROMOTION_NOT_CONFIRMED"
    }
    [ordered]@{
        schema = "openmitrastar.f301-flash-test-rollback/v1"
        status = $status
        started_utc = $started.ToString("o")
        finished_utc = [DateTime]::UtcNow.ToString("o")
        candidate_sha256 = $f301Sha
        candidate_full_slot_crc32 = $f301FullCrc
        candidate_full_slot_sha256 = $f301FullSha
        rollback_sha256 = $f300Sha
        rollback_full_slot_crc32 = $f300FullCrc
        rollback_full_slot_sha256 = $f300FullSha
        promoted = $promoted
        campaign_passed = $campaignPassed
        rollback_attempted = $rollbackAttempted
        rollback_passed = $rollbackPassed
        failure = $failure
        write_targets = @("mtd4/linux_live")
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $OutputDir "result.json") -Encoding ascii
}

if (-not $campaignPassed) {
    if ($rollbackAttempted -and $rollbackPassed) {
        throw "F301 campaign was not PASS and F300 was restored; inspect $OutputDir"
    }
    throw "F301 campaign was not PASS; manual recovery may be required; inspect $OutputDir"
}
Write-Output "OMF301_FLASH_TEST_PASS=1 output=$OutputDir"
