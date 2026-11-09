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
    [switch]$NoRollback,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$requiredAck = "OPENMITRASTAR_F293_FLASH_TEST_ROLLBACK_76F07B7D"
$f293Sha = "76f07b7d868fe878fe032bf302b2c75340498cd0186537bf75fc3ef9066ddc37"
$f292Sha = "bb796f406c0e7941a868b329234611f014809d5cd2643565fad9888b3cd48b1e"
$f293Build = Join-Path $env:USERPROFILE ".openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f293-device-bound"
$promoter = Join-Path $root "tools\promote_f293_mtd4_direct.ps1"
$campaign = Join-Path $root "tools\run_f293_physical_campaign.ps1"
$rollback = Join-Path $root "tools\rollback_f293_to_f292_mtd4.ps1"

function Invoke-DryRun([string]$Script, [string[]]$Arguments) {
    $text = (& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script @Arguments | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "dry-run failed: $Script" }
    return $text | ConvertFrom-Json
}

function Test-F293FlashCompleted([datetime]$StartedUtc) {
    $latest = Get-ChildItem -LiteralPath $f293Build -Directory -Filter "flash-one-shot-*" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTimeUtc -ge $StartedUtc.AddSeconds(-5) } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if (-not $latest) { return $false }
    $resultPath = Join-Path $latest.FullName "result.json"
    if (-not (Test-Path -LiteralPath $resultPath)) { return $false }
    $result = Get-Content -Raw -LiteralPath $resultPath | ConvertFrom-Json
    return (
        $result.status -eq "PASS" -and
        $result.candidate_sha256 -eq $f293Sha -and
        $result.physical_write.partition -eq "mtd4/linux_live" -and
        $result.protected_partitions.status -eq "PASS"
    )
}

$promotePlan = Invoke-DryRun $promoter @("-Port", $Port, "-RouterHost", $RouterHost, "-TftpHost", $TftpHost, "-Transport", $Transport)
$campaignPlan = Invoke-DryRun $campaign @("-RouterHost", $RouterHost, "-OracleHost", $OracleHost, "-OracleUser", $OracleUser)
$rollbackPlan = Invoke-DryRun $rollback @("-Port", $Port, "-RouterHost", $RouterHost, "-TftpHost", $TftpHost, "-Transport", $Transport)
$ready = (
    $promotePlan.target -eq "mtd4/linux_live" -and
    $promotePlan.sha256 -eq $f293Sha -and
    $promotePlan.router_ssh -eq $true -and
    $promotePlan.tftp_host_local -eq $true -and
    $promotePlan.uart_present -eq $true -and
    $campaignPlan.candidate_sha256 -eq $f293Sha -and
    $campaignPlan.router_ssh -eq $true -and
    $campaignPlan.oracle_ssh -eq $true -and
    $rollbackPlan.target -eq "mtd4/linux_live" -and
    $rollbackPlan.sha256 -eq $f292Sha
)

$plan = [ordered]@{
    schema = "openmitrastar.f293-flash-test-rollback-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    ready = $ready
    flash = @{ target = "mtd4/linux_live"; sha256 = $f293Sha; transport = $Transport }
    test = @{ realtek_runs = 3; bytes_per_direction = 33554432; quantenna_seconds = 120 }
    rollback = @{ enabled = -not $NoRollback; target = "mtd4/linux_live"; sha256 = $f292Sha }
    protected_partitions = @("mtd0", "mtd1", "mtd2", "mtd3", "mtd5")
}
$plan | ConvertTo-Json -Depth 5

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing campaign: exact -Ack is required" }
if (-not $ready) { throw "F293 campaign preflight is not ready" }

if (-not $OutputDir) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $OutputDir = Join-Path $root "outputs\campaign\f293-flash-test-$stamp"
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
        -Execute -Ack OPENMITRASTAR_F293_HW_RX_DEMAND_76F07B7D `
        -Port $Port -RouterHost $RouterHost -TftpHost $TftpHost -Transport $Transport `
        2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "promotion.log")
    if ($LASTEXITCODE -ne 0) {
        $promoted = Test-F293FlashCompleted $started
        throw "F293 promotion failed"
    }
    $promoted = $true

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $campaign `
        -Execute -Ack OPENMITRASTAR_F293_HW_RX_DEMAND_PHYSICAL `
        -RouterHost $RouterHost -OracleHost $OracleHost -OracleUser $OracleUser `
        -OutputDir (Join-Path $OutputDir "physical") `
        2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "campaign.log")
    if ($LASTEXITCODE -ne 0) { throw "F293 physical campaign failed" }
    $campaignPassed = $true
} catch {
    $failure = $_.Exception.Message
    if ($promoted -and -not $NoRollback) {
        $rollbackAttempted = $true
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $rollback `
            -Execute -Ack OPENMITRASTAR_ROLLBACK_F293_TO_F292_BB796F40 `
            -Port $Port -RouterHost $RouterHost -TftpHost $TftpHost -Transport $Transport `
            2>&1 | Tee-Object -FilePath (Join-Path $OutputDir "rollback.log")
        $rollbackPassed = $LASTEXITCODE -eq 0
    }
} finally {
    $status = if ($campaignPassed) {
        "PASS"
    } elseif ($rollbackAttempted -and $rollbackPassed) {
        "ROLLED_BACK_AFTER_FAILED_CAMPAIGN"
    } elseif ($promoted) {
        "MANUAL_RECOVERY_REQUIRED"
    } else {
        "PROMOTION_NOT_CONFIRMED"
    }
    [ordered]@{
        schema = "openmitrastar.f293-flash-test-rollback/v1"
        status = $status
        started_utc = $started.ToString("o")
        finished_utc = [DateTime]::UtcNow.ToString("o")
        candidate_sha256 = $f293Sha
        rollback_sha256 = $f292Sha
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
        throw "F293 campaign failed and F292 was restored; inspect $OutputDir"
    }
    throw "F293 campaign failed; manual recovery may be required; inspect $OutputDir"
}
Write-Output "OMF293_FLASH_TEST_PASS=1 output=$OutputDir"
