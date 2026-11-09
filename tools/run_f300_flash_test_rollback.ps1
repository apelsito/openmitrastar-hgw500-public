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
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$requiredAck = "OPENMITRASTAR_F300_FLASH_TEST_ROLLBACK_734BBA8A"
$f300Sha = "734bba8ad1b706c0c17ad5e73341cbb7c7a5c4d78cf05e069d955705d789edbb"
$f300FullCrc = "841f11c8"
$f300FullSha = "fb7867874640a428124a18be38b8521e52e5d27322393f88ab44bbd6d17baf9b"
$f292Sha = "bb796f406c0e7941a868b329234611f014809d5cd2643565fad9888b3cd48b1e"
$f292FullCrc = "e40dada0"
$f292FullSha = "9c6dbb456207eb4006c791be76e8f40d58843e198f03abb9c0676d60202a94b1"
$f300Build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f300-device-bound"
$promoter = Join-Path $root "tools\promote_f300_mtd4_direct.ps1"
$campaign = Join-Path $root "tools\run_f300_physical_campaign.ps1"
$rollback = Join-Path $root "tools\rollback_f300_to_f292_mtd4.ps1"

function Invoke-DryRun([string]$Script, [string[]]$Arguments) {
    $text = (& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script @Arguments | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "offline dry-run failed: $Script" }
    return $text | ConvertFrom-Json
}

function Test-F300FlashCompleted([datetime]$StartedUtc) {
    $latest = Get-ChildItem -LiteralPath $f300Build -Directory -Filter "flash-one-shot-*" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTimeUtc -ge $StartedUtc.AddSeconds(-5) } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if (-not $latest) { return $false }
    $resultPath = Join-Path $latest.FullName "result.json"
    if (-not (Test-Path -LiteralPath $resultPath)) { return $false }
    $result = Get-Content -Raw -LiteralPath $resultPath | ConvertFrom-Json
    return (
        $result.status -eq "PASS" -and
        $result.candidate_sha256 -eq $f300Sha -and
        $result.readback.full_slot_crc32 -eq $f300FullCrc -and
        $result.readback.full_slot_sha256 -eq $f300FullSha -and
        $result.physical_write.partition -eq "mtd4/linux_live" -and
        $result.protected_partitions.status -eq "PASS"
    )
}

$promotePlan = Invoke-DryRun $promoter @(
    "-Port", $Port, "-RouterHost", $RouterHost, "-TftpHost", $TftpHost, "-Transport", $Transport
)
$campaignPlan = Invoke-DryRun $campaign @(
    "-RouterHost", $RouterHost, "-OracleHost", $OracleHost, "-OracleUser", $OracleUser
)
$rollbackPlan = Invoke-DryRun $rollback @(
    "-Port", $Port, "-RouterHost", $RouterHost, "-TftpHost", $TftpHost, "-Transport", $Transport
)
$ready = (
    $promotePlan.target -eq "mtd4/linux_live" -and
    $promotePlan.sha256 -eq $f300Sha -and
    $promotePlan.bytes -eq 5259264 -and
    $promotePlan.full_slot_crc32 -eq $f300FullCrc -and
    $promotePlan.full_slot_sha256 -eq $f300FullSha -and
    $promotePlan.expected_current_full_slot_crc32 -eq $f292FullCrc -and
    $promotePlan.expected_current_full_slot_sha256 -eq $f292FullSha -and
    $campaignPlan.candidate_sha256 -eq $f300Sha -and
    $campaignPlan.realtek_runs -eq 3 -and
    $campaignPlan.bytes_per_direction -eq 33554432 -and
    $campaignPlan.required_median_ratio_to_f290 -eq 0.95 -and
    $campaignPlan.required_early_restart.trigger_pokes_less_than -eq 13 -and
    $campaignPlan.required_early_restart.minimum_mac_progress_streak -eq 2 -and
    $campaignPlan.required_early_restart.must_improve_on_f299 -eq $true -and
    $rollbackPlan.target -eq "mtd4/linux_live" -and
    $rollbackPlan.sha256 -eq $f292Sha -and
    $rollbackPlan.full_slot_crc32 -eq $f292FullCrc -and
    $rollbackPlan.full_slot_sha256 -eq $f292FullSha -and
    $rollbackPlan.expected_current_full_slot_crc32 -eq $f300FullCrc -and
    $rollbackPlan.expected_current_full_slot_sha256 -eq $f300FullSha
)

[ordered]@{
    schema = "openmitrastar.f300-flash-test-rollback-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    ready = $ready
    flash = @{
        target = "mtd4/linux_live"
        sha256 = $f300Sha
        full_slot_crc32 = $f300FullCrc
        full_slot_sha256 = $f300FullSha
        transport = $Transport
    }
    test = @{
        realtek_runs = 3
        bytes_per_direction = 33554432
        f290_median_floor_ratio = 0.95
        early_restart_proof_required = $true
        minimum_mac_progress_streak = 2
        trigger_pokes_less_than = 13
        f299_trigger_must_be_improved = $true
    }
    rollback = @{
        automatic_on_any_non_pass = $true
        target = "mtd4/linux_live"
        sha256 = $f292Sha
        full_slot_crc32 = $f292FullCrc
        full_slot_sha256 = $f292FullSha
    }
    protected_partitions = @("mtd0", "mtd1", "mtd2", "mtd3", "mtd5")
    hardware_actions_performed = $false
} | ConvertTo-Json -Depth 6

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing campaign: exact -Ack is required" }
if (-not $ready) { throw "F300 offline campaign contract is not ready" }

if (-not $OutputDir) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $OutputDir = Join-Path $root "outputs\campaign\f300-flash-test-$stamp"
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
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $promoter `
        -Execute -Ack OPENMITRASTAR_F300_HW_DEMAND_TWO_SAMPLE_734BBA8A `
        -Port $Port -RouterHost $RouterHost -TftpHost $TftpHost -Transport $Transport `
        2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "promotion.log")
    if ($LASTEXITCODE -ne 0) {
        $promoted = Test-F300FlashCompleted $started
        throw "F300 promotion failed"
    }
    $promoted = $true

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $campaign `
        -Execute -Ack OPENMITRASTAR_F300_HW_DEMAND_TWO_SAMPLE_PHYSICAL `
        -RouterHost $RouterHost -OracleHost $OracleHost -OracleUser $OracleUser `
        -OutputDir (Join-Path $OutputDir "physical") `
        2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "campaign.log")
    if ($LASTEXITCODE -ne 0) { throw "F300 physical campaign did not PASS" }
    $campaignData = Get-Content -Raw -LiteralPath (Join-Path $OutputDir "physical\campaign.json") | ConvertFrom-Json
    if ($campaignData.status -ne "PASS") { throw "F300 physical campaign result is not PASS" }
    $campaignPassed = $true
} catch {
    $failure = $_.Exception.Message
    if ($promoted) {
        $rollbackAttempted = $true
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $rollback `
            -Execute -Ack OPENMITRASTAR_ROLLBACK_F300_TO_F292_BB796F40 `
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
        schema = "openmitrastar.f300-flash-test-rollback/v1"
        status = $status
        started_utc = $started.ToString("o")
        finished_utc = [DateTime]::UtcNow.ToString("o")
        candidate_sha256 = $f300Sha
        candidate_full_slot_crc32 = $f300FullCrc
        candidate_full_slot_sha256 = $f300FullSha
        rollback_sha256 = $f292Sha
        rollback_full_slot_crc32 = $f292FullCrc
        rollback_full_slot_sha256 = $f292FullSha
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
        throw "F300 campaign was not PASS and F292 was restored; inspect $OutputDir"
    }
    throw "F300 campaign was not PASS; manual recovery may be required; inspect $OutputDir"
}
Write-Output "OMF300_FLASH_TEST_PASS=1 output=$OutputDir"

