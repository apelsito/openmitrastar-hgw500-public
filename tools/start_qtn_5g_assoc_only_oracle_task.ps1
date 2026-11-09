[CmdletBinding()]
param(
    [switch]$Execute,
    [string]$Ack = '',
    [string]$SourceScript = '',
    [string]$WatchdogSourceScript = '',
    [ValidateLength(1, 32)][string]$TestSsid = 'OpenMitraStar-5G-DIAG',
    [ValidateLength(1, 32)][string]$RestoreSsid = 'MOVISTAR-WIFI6-A348',
    [ValidateNotNullOrEmpty()][string]$WifiInterface = 'Wi-Fi',
    [string]$ExpectedBssid = '',
    [ValidateRange(2, 30)][int]$RestoreWatchdogMinutes = 8
)

$ErrorActionPreference = 'Stop'
$requiredAck = 'OPENMITRASTAR_QTN_5G_ASSOC_ONLY_TASK'
$SourceScript = if ($SourceScript) { $SourceScript } else { Join-Path $PSScriptRoot 'run_qtn_5g_assoc_only_oracle.ps1' }
$WatchdogSourceScript = if ($WatchdogSourceScript) { $WatchdogSourceScript } else { Join-Path $PSScriptRoot 'restore_wifi_oracle_watchdog.ps1' }
$root = 'C:\ProgramData\OpenMitraStar\oracle'
$script = Join-Path $root 'run_qtn_5g_assoc_only_oracle.ps1'
$watchdogScript = Join-Path $root 'restore_wifi_oracle_watchdog.ps1'
$result = Join-Path $root 'qtn-5g-assoc-only-result.json'
$watchdogResult = Join-Path $root 'assoc-only-restore-watchdog-result.json'
$taskName = 'OpenMitraStar-QTN5G-AssocOnly'
$watchdogTaskName = 'OpenMitraStar-QTN5G-AssocOnly-Restore'
$powerShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$netsh = Join-Path $env:WINDIR 'System32\netsh.exe'

if (-not $Execute) {
    [ordered]@{
        schema = 'openmitrastar.qtn-5g-assoc-only-task-plan/v1'
        execute = $false
        oracle = 'AELITA'
        task = $taskName
        watchdog_task = $watchdogTaskName
        principal = 'SYSTEM'
        watchdog_preflight = 'required-as-SYSTEM-before-oracle'
        watchdog_delay_minutes = $RestoreWatchdogMinutes
        test_ssid = $TestSsid
        restore_ssid = $RestoreSsid
        result = $result
        flash = $false
        router_mutations = $false
        serial_uart = $false
    } | ConvertTo-Json -Depth 4
    Write-Output 'OMQTN5G_ASSOC_ONLY_TASK_DRY_RUN_PASS=1 execute=0 principal=SYSTEM'
    exit 0
}
if ($Ack -ne $requiredAck) { throw "Require -Ack $requiredAck" }
if ($ExpectedBssid -and $ExpectedBssid -notmatch '^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$') {
    throw 'ExpectedBssid must be empty or a colon-separated MAC address'
}

function Assert-ElevatedAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Administrator elevation is required to register SYSTEM tasks and protect ProgramData'
    }
}

function Protect-SystemOnlyPath {
    param([Parameter(Mandatory)][string]$LiteralPath)
    $item = Get-Item -LiteralPath $LiteralPath -ErrorAction Stop
    $systemGrant = if ($item.PSIsContainer) { '*S-1-5-18:(OI)(CI)F' } else { '*S-1-5-18:F' }
    $adminGrant = if ($item.PSIsContainer) { '*S-1-5-32-544:(OI)(CI)F' } else { '*S-1-5-32-544:F' }
    & icacls.exe $LiteralPath /inheritance:r /grant:r $systemGrant $adminGrant | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to protect ACL on $LiteralPath" }
}

function Quote-PowerShellLiteral {
    param([Parameter(Mandatory)][string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

function ConvertTo-EncodedPowerShell {
    param([Parameter(Mandatory)][string]$Command)
    return [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Command))
}

function Remove-StaleTask {
    param([Parameter(Mandatory)][string]$Name)
    $existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($existing) {
        Stop-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
    }
}

Assert-ElevatedAdministrator
foreach ($value in @($TestSsid, $RestoreSsid, $WifiInterface, $ExpectedBssid)) {
    if ([string]::IsNullOrWhiteSpace($value) -and $value -ne $ExpectedBssid) {
        throw 'Task parameters must be non-empty'
    }
    if ($value -match '[\x00-\x1f]') {
        throw 'Task parameters must contain no control characters'
    }
}
if ($TestSsid -eq $RestoreSsid) { throw 'TestSsid and RestoreSsid must be different' }
$wifiAdapter = Get-NetAdapter -Name $WifiInterface -ErrorAction Stop
if ($wifiAdapter.InterfaceDescription -notmatch 'Wireless|Wi-Fi|802\.11') {
    throw "Interface '$WifiInterface' does not look like a Wi-Fi adapter"
}
$restoreProfileCheck = (& $netsh wlan show profile "name=$RestoreSsid" "interface=$WifiInterface" 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Restore profile '$RestoreSsid' is not available on '$WifiInterface': $restoreProfileCheck"
}

$sourceItem = Get-Item -LiteralPath $SourceScript -ErrorAction Stop
$watchdogSourceItem = Get-Item -LiteralPath $WatchdogSourceScript -ErrorAction Stop
foreach ($item in @($sourceItem, $watchdogSourceItem)) {
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Oracle and watchdog sources must be regular files, not reparse points'
    }
}
if (Test-Path -LiteralPath $root) {
    $rootItem = Get-Item -LiteralPath $root -Force
    if ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Oracle ProgramData root must not be a reparse point'
    }
}
New-Item -ItemType Directory -Force -Path $root | Out-Null
Protect-SystemOnlyPath -LiteralPath $root

foreach ($copy in @(
    @{ Source = $sourceItem.FullName; Stage = "$script.new"; Destination = $script },
    @{ Source = $watchdogSourceItem.FullName; Stage = "$watchdogScript.new"; Destination = $watchdogScript }
)) {
    Remove-Item -LiteralPath $copy.Stage -Force -ErrorAction SilentlyContinue
    Copy-Item -LiteralPath $copy.Source -Destination $copy.Stage -Force
    Protect-SystemOnlyPath -LiteralPath $copy.Stage
    Remove-Item -LiteralPath $copy.Destination -Force -ErrorAction SilentlyContinue
    Move-Item -LiteralPath $copy.Stage -Destination $copy.Destination -Force
    Protect-SystemOnlyPath -LiteralPath $copy.Destination
    $sourceHash = (Get-FileHash -LiteralPath $copy.Source -Algorithm SHA256).Hash.ToLowerInvariant()
    $installedHash = (Get-FileHash -LiteralPath $copy.Destination -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($sourceHash -ne $installedHash) { throw "Staged hash mismatch: $($copy.Destination)" }
}
$stagedHash = (Get-FileHash -LiteralPath $script -Algorithm SHA256).Hash.ToLowerInvariant()
$watchdogStagedHash = (Get-FileHash -LiteralPath $watchdogScript -Algorithm SHA256).Hash.ToLowerInvariant()

Remove-Item -LiteralPath $result,$watchdogResult -Force -ErrorAction SilentlyContinue
Remove-StaleTask -Name $taskName
Remove-StaleTask -Name $watchdogTaskName

$oracleCommand = "& $(Quote-PowerShellLiteral $script) " +
    "-Execute -Ack 'OPENMITRASTAR_QTN_5G_ASSOC_ONLY_ORACLE' " +
    "-TestSsid $(Quote-PowerShellLiteral $TestSsid) -RestoreSsid $(Quote-PowerShellLiteral $RestoreSsid) " +
    "-WifiInterface $(Quote-PowerShellLiteral $WifiInterface) -OutputPath $(Quote-PowerShellLiteral $result)"
if ($ExpectedBssid) {
    $oracleCommand += " -ExpectedBssid $(Quote-PowerShellLiteral $ExpectedBssid)"
}
$oracleEncoded = ConvertTo-EncodedPowerShell $oracleCommand
$oracleAction = New-ScheduledTaskAction -Execute $powerShell `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $oracleEncoded"
$oracleTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(-5)
$oracleSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 4) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest

$restoreCommand = "& $(Quote-PowerShellLiteral $watchdogScript) " +
    "-RestoreSsid $(Quote-PowerShellLiteral $RestoreSsid) " +
    "-WifiInterface $(Quote-PowerShellLiteral $WifiInterface) " +
    "-StatusPath $(Quote-PowerShellLiteral $watchdogResult)"
$restoreEncoded = ConvertTo-EncodedPowerShell $restoreCommand
$restoreAction = New-ScheduledTaskAction -Execute $powerShell `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $restoreEncoded"
$restoreTrigger = New-ScheduledTaskTrigger -Once `
    -At (Get-Date).AddMinutes($RestoreWatchdogMinutes) `
    -RepetitionInterval (New-TimeSpan -Minutes 2) `
    -RepetitionDuration (New-TimeSpan -Minutes 20)
$restoreSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -WakeToRun

Register-ScheduledTask -TaskName $watchdogTaskName -Action $restoreAction `
    -Trigger $restoreTrigger -Principal $principal -Settings $restoreSettings `
    -Description "Failsafe restore to $RestoreSsid after Quantenna assoc-only oracle" -Force | Out-Null
Register-ScheduledTask -TaskName $taskName -Action $oracleAction `
    -Trigger $oracleTrigger -Principal $principal -Settings $oracleSettings `
    -Description 'One-shot Quantenna 5 GHz association-only Windows oracle' -Force | Out-Null

Start-ScheduledTask -TaskName $watchdogTaskName
$preflightDeadline = (Get-Date).AddSeconds(45)
do {
    Start-Sleep -Milliseconds 500
    $preflightState = (Get-ScheduledTask -TaskName $watchdogTaskName).State
} while ($preflightState -eq 'Running' -and (Get-Date) -lt $preflightDeadline)
if (-not (Test-Path -LiteralPath $watchdogResult)) {
    throw 'SYSTEM restore-watchdog preflight produced no status file; oracle was not started'
}
$watchdogPreflight = Get-Content -LiteralPath $watchdogResult -Raw | ConvertFrom-Json
if (-not $watchdogPreflight.profile_available -or -not $watchdogPreflight.restored) {
    throw "SYSTEM restore-watchdog preflight failed: $($watchdogPreflight.error)"
}
Start-ScheduledTask -TaskName $taskName

[ordered]@{
    schema = 'openmitrastar.qtn-5g-assoc-only-task/v1'
    task = $taskName
    task_state = (Get-ScheduledTask -TaskName $taskName).State.ToString()
    watchdog_task = $watchdogTaskName
    watchdog_at = $restoreTrigger.StartBoundary
    principal = 'SYSTEM'
    staged_script = $script
    staged_script_sha256 = $stagedHash
    staged_watchdog = $watchdogScript
    staged_watchdog_sha256 = $watchdogStagedHash
    watchdog_result = $watchdogResult
    watchdog_preflight = 'passed-as-SYSTEM'
    result = $result
    flash = $false
    router_mutations = $false
    serial_uart = $false
} | ConvertTo-Json -Depth 4
