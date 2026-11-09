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
$requiredAck = "OPENMITRASTAR_F310_FLASH_TEST_ROLLBACK_DF451D72"
$f310Sha = "df451d720d8a959ff79ae6a2377940f6f9c3253f22d00f4b15752827e55ba330"
$f310FullCrc = "115c78af"
$f310FullSha = "3b24a09219485bc68e821d20b4a4a84a0ab31cc005144b492493158bd50d1c09"
$currentF310PreviousFullCrc = "8bf06eee"
$currentF310PreviousFullSha = "260dc685a62215eb4bdbb654668ea734386f1e0fc7a3834d0cc45fb6f4a8eb23"
$f309Sha = "bf784c8ca144fbd18f5222a5cd23e909c59b6a1cf3bcabfc2f254fce21f91bf8"
$f309FullCrc = "8bf06eee"
$f309FullSha = "260dc685a62215eb4bdbb654668ea734386f1e0fc7a3834d0cc45fb6f4a8eb23"
$f310Build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f310-device-bound"
$promoter = Join-Path $root "tools\promote_f310_mtd4_direct.ps1"
$campaign = Join-Path $root "tools\run_f310_physical_campaign.ps1"
$rollback = Join-Path $root "tools\rollback_f310_to_f309_mtd4.ps1"
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

function Invoke-LoggedPowerShell([string]$Script, [string[]]$Arguments, [string]$LogPath) {
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script @Arguments `
            2>&1 | Tee-Object -FilePath $LogPath
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedPreference
    }
}

function Test-F310FlashCompleted([datetime]$StartedUtc) {
    foreach ($attempt in 1..10) {
        $resultFiles = Get-ChildItem -LiteralPath $f310Build -Directory -Filter "flash-one-shot-*" -ErrorAction SilentlyContinue |
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
                    $result.candidate_sha256 -eq $f310Sha -and
                    $result.readback.full_slot_crc32 -eq $f310FullCrc -and
                    $result.readback.full_slot_sha256 -eq $f310FullSha -and
                    $result.physical_write.partition -eq "mtd4/linux_live" -and
                    $result.protected_partitions.status -eq "PASS"
                ) {
                    return $true
                }
            } catch {
                continue
            }
        }
        if ($attempt -lt 10) { Start-Sleep -Seconds 2 }
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
    $promotePlan.sha256 -eq $f310Sha -and
    $promotePlan.bytes -eq 5267456 -and
    $promotePlan.full_slot_crc32 -eq $f310FullCrc -and
    $promotePlan.full_slot_sha256 -eq $f310FullSha -and
    $promotePlan.expected_current_full_slot_crc32 -eq $currentF310PreviousFullCrc -and
    $promotePlan.expected_current_full_slot_sha256 -eq $currentF310PreviousFullSha -and
    @($promotePlan.authenticated_api_endpoints).Count -eq 6 -and
    $promotePlan.live_asset_hash_count -eq 7 -and
    $promotePlan.public_dashboard_policy -eq "404-not-packaged" -and
    $promotePlan.capability_rows -eq 23 -and
    $campaignPlan.candidate_sha256 -eq $f310Sha -and
    $campaignPlan.realtek_runs -eq 1 -and
    $campaignPlan.realtek_bytes_per_direction -eq 33554432 -and
    $campaignPlan.radio5_profile -eq "f310" -and
    $campaignPlan.radio5_bytes_per_direction -eq 33554432 -and
    $campaignPlan.radio5_soak_seconds -eq 120 -and
    $campaignPlan.final_health.monolithic_command -eq $false -and
    $campaignPlan.final_health.retries_per_read -eq 5 -and
    $rollbackPlan.target -eq "mtd4/linux_live" -and
    $rollbackPlan.sha256 -eq $f309Sha -and
    $rollbackPlan.bytes -eq 5267456 -and
    $rollbackPlan.full_slot_crc32 -eq $f309FullCrc -and
    $rollbackPlan.full_slot_sha256 -eq $f309FullSha -and
    $rollbackPlan.legacy_dashboard_policy -eq "removed-exact-f309-rollback" -and
    $rollbackPlan.expected_current_full_slot_crc32 -eq $f310FullCrc -and
    $rollbackPlan.expected_current_full_slot_sha256 -eq $f310FullSha
)
$ready = $offlineContractReady -and -not $lockState.active

[ordered]@{
    schema = "openmitrastar.f310-flash-test-rollback-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    ready = $ready
    offline_contract_ready = $offlineContractReady
    execute_allowed_now = $ready
    hardware_lock = $lockState
    flash = @{
        target = "mtd4/linux_live"
        sha256 = $f310Sha
        bytes = 5267456
        full_slot_crc32 = $f310FullCrc
        full_slot_sha256 = $f310FullSha
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
    flash_detection = @{
        evidence = "result.json/generated_at"
        attempts = 10
        delay_seconds = 2
        directory_mtime_authoritative = $false
    }
    test = @{
        realtek_runs = 1
        bytes_per_direction = 33554432
        radio5_profile = "f310"
        radio5_soak_seconds = 120
        final_health_separate_reads = $true
        retries_per_read = 5
    }
    rollback = @{
        automatic_on_any_non_pass = $true
        target = "mtd4/linux_live"
        sha256 = $f309Sha
        bytes = 5267456
        full_slot_crc32 = $f309FullCrc
        full_slot_sha256 = $f309FullSha
    }
    protected_partitions = @("mtd0", "mtd1", "mtd2", "mtd3", "mtd5")
    hardware_actions_performed = $false
} | ConvertTo-Json -Depth 7

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing campaign: exact -Ack is required" }
if ($lockState.active) { throw "Refusing campaign: F301 physical lock is active ($($lockState.owner), pid=$($lockState.pid), reason=$($lockState.reason))" }
if (-not $ready) { throw "F310 offline campaign contract is not ready" }

if (-not $OutputDir) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $OutputDir = Join-Path $root "outputs\campaign\f310-flash-test-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$lockAcquired = $false
try {
    New-Item -ItemType Directory -Path $hardwareLock -ErrorAction Stop | Out-Null
    [ordered]@{
        schema = "openmitrastar.f301-physical-radio-lock/v1"
        owner = "f310-flash-test-rollback"
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
        "-Execute", "-Ack", "OPENMITRASTAR_F310_CANONICAL_FRONTEND_IDENTITY_DF451D72",
        "-Port", $Port, "-RouterHost", $RouterHost, "-TftpHost", $TftpHost, "-Transport", $Transport
    )
    if ($WebPasswordFile) { $executePromoteArgs += @("-WebPasswordFile", $WebPasswordFile) }
    $promoteExit = Invoke-LoggedPowerShell $promoter $executePromoteArgs (Join-Path $OutputDir "promotion.log")
    if ($promoteExit -ne 0) {
        $promoted = Test-F310FlashCompleted $started
        throw "F310 promotion or post-flash gate failed"
    }
    $promoted = $true

    $campaignArgs = @(
        "-Execute", "-Ack", "OPENMITRASTAR_F310_CANONICAL_FRONTEND_IDENTITY_PHYSICAL",
        "-RouterHost", $RouterHost, "-OracleHost", $OracleHost, "-OracleUser", $OracleUser,
        "-OutputDir", (Join-Path $OutputDir "physical")
    )
    $campaignExit = Invoke-LoggedPowerShell $campaign $campaignArgs (Join-Path $OutputDir "campaign.log")
    if ($campaignExit -ne 0) { throw "F310 physical campaign did not PASS" }
    $campaignData = Get-Content -Raw -LiteralPath (Join-Path $OutputDir "physical\campaign.json") | ConvertFrom-Json
    if ($campaignData.status -ne "PASS") { throw "F310 physical campaign result is not PASS" }
    $campaignPassed = $true
} catch {
    $failure = $_.Exception.Message
    if ($promoted) {
        $rollbackAttempted = $true
        $rollbackArgs = @(
            "-Execute", "-Ack", "OPENMITRASTAR_ROLLBACK_F310_TO_F309_BF784C8C",
            "-Port", $Port, "-RouterHost", $RouterHost, "-TftpHost", $TftpHost,
            "-Transport", $Transport
        )
        $rollbackExit = Invoke-LoggedPowerShell $rollback $rollbackArgs (Join-Path $OutputDir "rollback.log")
        $rollbackPassed = $rollbackExit -eq 0
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
        schema = "openmitrastar.f310-flash-test-rollback/v1"
        status = $status
        started_utc = $started.ToString("o")
        finished_utc = [DateTime]::UtcNow.ToString("o")
        candidate_sha256 = $f310Sha
        candidate_full_slot_crc32 = $f310FullCrc
        candidate_full_slot_sha256 = $f310FullSha
        rollback_sha256 = $f309Sha
        rollback_full_slot_crc32 = $f309FullCrc
        rollback_full_slot_sha256 = $f309FullSha
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
        throw "F310 campaign was not PASS and F309 was restored; inspect $OutputDir"
    }
    throw "F310 campaign was not PASS; manual recovery may be required; inspect $OutputDir"
}
Write-Output "OMF310_FLASH_TEST_PASS=1 output=$OutputDir"

