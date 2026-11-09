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
$requiredAck = "OPENMITRASTAR_F309_FLASH_TEST_ROLLBACK_BF784C8C"
$f309Sha = "bf784c8ca144fbd18f5222a5cd23e909c59b6a1cf3bcabfc2f254fce21f91bf8"
$f309FullCrc = "8bf06eee"
$f309FullSha = "260dc685a62215eb4bdbb654668ea734386f1e0fc7a3834d0cc45fb6f4a8eb23"
$currentF309PreviousFullCrc = "71548682"
$currentF309PreviousFullSha = "c0a17995cbde98d28748dce3a7163b3629dd3a9783ea33dde32cda5eaf077b36"
$f306Sha = "a245ab177e9ce7688c638b34161265bcdc70c5d21da54715530801fe20e33dc2"
$f306FullCrc = "71548682"
$f306FullSha = "c0a17995cbde98d28748dce3a7163b3629dd3a9783ea33dde32cda5eaf077b36"
$f309Build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f309-device-bound"
$promoter = Join-Path $root "tools\promote_f309_mtd4_direct.ps1"
$campaign = Join-Path $root "tools\run_f309_physical_campaign.ps1"
$rollback = Join-Path $root "tools\rollback_f309_to_f306_mtd4.ps1"
$hardwareLock = Join-Path $root "outputs\locks\f301-physical-radio.lock"

function Get-HardwareLockState {
    $state = [ordered]@{
        present = $false
        active = $false
        owner = ""
        pid = 0
        reason = "absent"
    }
    if (-not (Test-Path -LiteralPath $hardwareLock -PathType Container)) { return $state }
    $state.present = $true
    $ownerPath = Join-Path $hardwareLock "owner.json"
    if (-not (Test-Path -LiteralPath $ownerPath -PathType Leaf)) {
        $state.active = $true
        $state.reason = "lock-present-owner-missing"
        return $state
    }
    try {
        $owner = Get-Content -Raw -LiteralPath $ownerPath | ConvertFrom-Json
        $state.owner = [string]$owner.owner
        $state.pid = [int]$owner.pid
        $process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
        $state.active = [bool]$process
        $state.reason = if ($process) { "live-process" } else { "stale-process" }
    } catch {
        $state.active = $true
        $state.reason = "lock-unreadable"
    }
    return $state
}

function Invoke-DryRun([string]$Script, [string[]]$Arguments) {
    $text = (& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script @Arguments | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "offline dry-run failed: $Script" }
    return $text | ConvertFrom-Json
}

function Test-F309FlashCompleted([datetime]$StartedUtc) {
    $resultFiles = Get-ChildItem -LiteralPath $f309Build -Directory -Filter "flash-one-shot-*" -ErrorAction SilentlyContinue |
        ForEach-Object {
            $path = Join-Path $_.FullName "result.json"
            if (Test-Path -LiteralPath $path -PathType Leaf) { Get-Item -LiteralPath $path }
        } |
        Sort-Object LastWriteTimeUtc -Descending
    foreach ($resultFile in $resultFiles) {
        try {
            $payload = Get-Content -Raw -LiteralPath $resultFile.FullName | ConvertFrom-Json
            $result = if ($payload.result) { $payload.result } else { $payload }
            $generatedValue = if ($result.generated_at) { $result.generated_at } else { $payload.generated_at }
            if (-not $generatedValue) { continue }
            $generatedUtc = if ($generatedValue -is [datetime]) {
                $generatedValue.ToUniversalTime()
            } else {
                [DateTimeOffset]::Parse([string]$generatedValue).UtcDateTime
            }
            if ($generatedUtc -lt $StartedUtc.AddSeconds(-5)) { continue }
            if (
                $result.status -eq "PASS" -and
                $result.candidate_sha256 -eq $f309Sha -and
                $result.readback.full_slot_crc32 -eq $f309FullCrc -and
                $result.readback.full_slot_sha256 -eq $f309FullSha -and
                $result.physical_write.partition -eq "mtd4/linux_live" -and
                $result.protected_partitions.status -eq "PASS"
            ) {
                return $true
            }
        } catch {
            continue
        }
    }
    return $false
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
$lockState = Get-HardwareLockState
$offlineContractReady = (
    $promotePlan.target -eq "mtd4/linux_live" -and
    $promotePlan.sha256 -eq $f309Sha -and
    $promotePlan.bytes -eq 5267456 -and
    $promotePlan.full_slot_crc32 -eq $f309FullCrc -and
    $promotePlan.full_slot_sha256 -eq $f309FullSha -and
    $promotePlan.expected_current_full_slot_crc32 -eq $currentF309PreviousFullCrc -and
    $promotePlan.expected_current_full_slot_sha256 -eq $currentF309PreviousFullSha -and
    @($promotePlan.authenticated_api_endpoints).Count -eq 6 -and
    $promotePlan.live_asset_hash_count -eq 7 -and
    $promotePlan.public_dashboard_policy -eq "404-not-packaged" -and
    $promotePlan.capability_rows -eq 23 -and
    $campaignPlan.candidate_sha256 -eq $f309Sha -and
    $campaignPlan.realtek_runs -eq 1 -and
    $campaignPlan.realtek_bytes_per_direction -eq 33554432 -and
    $campaignPlan.radio5_profile -eq "f309" -and
    $campaignPlan.radio5_bytes_per_direction -eq 33554432 -and
    $campaignPlan.radio5_soak_seconds -eq 120 -and
    $campaignPlan.final_health.monolithic_command -eq $false -and
    $campaignPlan.final_health.retries_per_read -eq 5 -and
    $rollbackPlan.target -eq "mtd4/linux_live" -and
    $rollbackPlan.sha256 -eq $f306Sha -and
    $rollbackPlan.bytes -eq 5267456 -and
    $rollbackPlan.full_slot_crc32 -eq $f306FullCrc -and
    $rollbackPlan.full_slot_sha256 -eq $f306FullSha -and
    $rollbackPlan.legacy_dashboard_policy -eq "present-exact-f306-rollback" -and
    $rollbackPlan.expected_current_full_slot_crc32 -eq $f309FullCrc -and
    $rollbackPlan.expected_current_full_slot_sha256 -eq $f309FullSha
)
$ready = $offlineContractReady -and -not $lockState.active

[ordered]@{
    schema = "openmitrastar.f309-flash-test-rollback-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    ready = $ready
    offline_contract_ready = $offlineContractReady
    execute_allowed_now = $ready
    hardware_lock = $lockState
    flash = @{
        target = "mtd4/linux_live"
        sha256 = $f309Sha
        bytes = 5267456
        full_slot_crc32 = $f309FullCrc
        full_slot_sha256 = $f309FullSha
        transport = $Transport
    }
    postflash = @{
        platform_gate = $true
        public_dashboard_404 = $true
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
        radio5_profile = "f309"
        radio5_soak_seconds = 120
        final_health_separate_reads = $true
        retries_per_read = 5
    }
    rollback = @{
        automatic_on_any_non_pass = $true
        target = "mtd4/linux_live"
        sha256 = $f306Sha
        bytes = 5267456
        full_slot_crc32 = $f306FullCrc
        full_slot_sha256 = $f306FullSha
    }
    protected_partitions = @("mtd0", "mtd1", "mtd2", "mtd3", "mtd5")
    hardware_actions_performed = $false
} | ConvertTo-Json -Depth 7

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing campaign: exact -Ack is required" }
if ($lockState.active) { throw "Refusing campaign: F301 physical lock is active ($($lockState.owner), pid=$($lockState.pid), reason=$($lockState.reason))" }
if (-not $ready) { throw "F309 offline campaign contract is not ready" }

if (-not $OutputDir) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $OutputDir = Join-Path $root "outputs\campaign\f309-flash-test-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$lockAcquired = $false
try {
    New-Item -ItemType Directory -Path $hardwareLock -ErrorAction Stop | Out-Null
    [ordered]@{
        schema = "openmitrastar.f301-physical-radio-lock/v1"
        owner = "f309-flash-test-rollback"
        pid = $PID
        started_at = [DateTime]::UtcNow.ToString("o")
        evidence_dir = $OutputDir
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $hardwareLock "owner.json") -Encoding ascii
    $lockAcquired = $true
} catch {
    if ($lockAcquired -and (Test-Path -LiteralPath $hardwareLock)) {
        Remove-Item -LiteralPath $hardwareLock -Recurse -Force
    }
    throw "Refusing campaign: physical lock could not be acquired atomically"
}
$started = [DateTime]::UtcNow
$promoted = $false
$campaignPassed = $false
$rollbackAttempted = $false
$rollbackPassed = $false
$failure = ""

try {
    $executePromoteArgs = @(
        "-Execute", "-Ack", "OPENMITRASTAR_F309_AUTHENTICATED_DASHBOARD_BF784C8C",
        "-Port", $Port, "-RouterHost", $RouterHost, "-TftpHost", $TftpHost, "-Transport", $Transport
    )
    if ($WebPasswordFile) { $executePromoteArgs += @("-WebPasswordFile", $WebPasswordFile) }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $promoter @executePromoteArgs `
        2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "promotion.log")
    if ($LASTEXITCODE -ne 0) {
        $promoted = Test-F309FlashCompleted $started
        throw "F309 promotion or post-flash gate failed"
    }
    $promoted = $true

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $campaign `
        -Execute -Ack OPENMITRASTAR_F309_AUTHENTICATED_DASHBOARD_PHYSICAL `
        -RouterHost $RouterHost -OracleHost $OracleHost -OracleUser $OracleUser `
        -OutputDir (Join-Path $OutputDir "physical") `
        2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "campaign.log")
    if ($LASTEXITCODE -ne 0) { throw "F309 physical campaign did not PASS" }
    $campaignData = Get-Content -Raw -LiteralPath (Join-Path $OutputDir "physical\campaign.json") | ConvertFrom-Json
    if ($campaignData.status -ne "PASS") { throw "F309 physical campaign result is not PASS" }
    $campaignPassed = $true
} catch {
    $failure = $_.Exception.Message
    if ($promoted) {
        $rollbackAttempted = $true
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $rollback `
            -Execute -Ack OPENMITRASTAR_ROLLBACK_F309_TO_F306_A245AB17 `
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
        schema = "openmitrastar.f309-flash-test-rollback/v1"
        status = $status
        started_utc = $started.ToString("o")
        finished_utc = [DateTime]::UtcNow.ToString("o")
        candidate_sha256 = $f309Sha
        candidate_full_slot_crc32 = $f309FullCrc
        candidate_full_slot_sha256 = $f309FullSha
        rollback_sha256 = $f306Sha
        rollback_full_slot_crc32 = $f306FullCrc
        rollback_full_slot_sha256 = $f306FullSha
        promoted = $promoted
        campaign_passed = $campaignPassed
        rollback_attempted = $rollbackAttempted
        rollback_passed = $rollbackPassed
        failure = $failure
        write_targets = @("mtd4/linux_live")
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $OutputDir "result.json") -Encoding ascii
    if ($lockAcquired -and (Test-Path -LiteralPath $hardwareLock)) {
        Remove-Item -LiteralPath $hardwareLock -Recurse -Force
        $lockAcquired = $false
    }
}

if (-not $campaignPassed) {
    if ($rollbackAttempted -and $rollbackPassed) {
        throw "F309 campaign was not PASS and F306 was restored; inspect $OutputDir"
    }
    throw "F309 campaign was not PASS; manual recovery may be required; inspect $OutputDir"
}
Write-Output "OMF309_FLASH_TEST_PASS=1 output=$OutputDir"

