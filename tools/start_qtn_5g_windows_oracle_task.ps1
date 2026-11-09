[CmdletBinding()]
param(
    [switch]$Execute,
    [switch]$IsolatedL3,
    [switch]$AssociationOnly,
    [switch]$MtuProbe,
    [switch]$SkipThroughput,
    [ValidateRange(0, 5000)][int]$PingStressCount = 0,
    [ValidateRange(32, 1472)][int]$PingStressPayloadBytes = 1400,
    [string]$Ack = '',
    [string]$SourceScript = '',
    [string]$WatchdogSourceScript = '',
    [ValidateLength(1, 32)][string]$TestSsid = 'OpenMitraStar-5G-DIAG',
    [ValidateLength(1, 32)][string]$RestoreSsid = 'MOVISTAR-WIFI6-A348',
    [ValidateNotNullOrEmpty()][string]$WifiInterface = 'Wi-Fi',
    [ValidateNotNullOrEmpty()][string]$RouterIp = '192.168.1.90',
    [ValidateNotNullOrEmpty()][string]$ControllerIp = '192.168.1.43',
    [ValidateRange(1, 65535)][int]$ControllerPort = 8081,
    [string]$ExpectedBssid = '',
    [ValidateNotNullOrEmpty()][string]$InternetUrl = 'https://www.microsoft.com/favicon.ico',
    [ValidateNotNullOrEmpty()][string]$DnsName = 'www.microsoft.com',
    [ValidateRange(1, 256)][int]$UploadMiB = 32,
    [ValidateRange(10, 300)][int]$TransferTimeoutSeconds = 180,
    [ValidateRange(0, 1800)][int]$SoakSeconds = 600,
    [ValidateRange(2, 30)][int]$RestoreWatchdogMinutes = 22
)

$ErrorActionPreference = 'Stop'
$SourceScript = if ($SourceScript) { $SourceScript } else { Join-Path $PSScriptRoot 'run_qtn_5g_windows_oracle.ps1' }
$WatchdogSourceScript = if ($WatchdogSourceScript) { $WatchdogSourceScript } else { Join-Path $PSScriptRoot 'restore_wifi_oracle_watchdog.ps1' }
$requiredAck = 'OPENMITRASTAR_QTN_5G_WINDOWS_ORACLE_TASK_RAM_ONLY'
$root = 'C:\ProgramData\OpenMitraStar\oracle'
$script = Join-Path $root 'run_qtn_5g_windows_oracle.ps1'
$watchdogScript = Join-Path $root 'restore_wifi_oracle_watchdog.ps1'
$result = Join-Path $root 'qtn-5g-result.json'
$watchdogResult = Join-Path $root 'restore-watchdog-result.json'
$taskName = 'OpenMitraStar-QTN5G-WindowsOracle'
$watchdogTaskName = 'OpenMitraStar-QTN5G-Restore'
$powerShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$netsh = Join-Path $env:WINDIR 'System32\netsh.exe'

if (-not $Execute) {
    [ordered]@{
        schema = 'openmitrastar.qtn-5g-windows-oracle-task-plan/v2'
        execute = $false
        oracle = 'AELITA@192.168.1.63'
        association_only = [bool]$AssociationOnly
        task = $taskName
        watchdog_task = $watchdogTaskName
        principal = 'SYSTEM'
        watchdog_preflight = 'required-as-SYSTEM-before-oracle'
        watchdog_delay_minutes = $RestoreWatchdogMinutes
        restore_ssid = $RestoreSsid
        result = $result
        flash = $false
    } | ConvertTo-Json -Depth 4
    Write-Output 'OMQTN5G_WINDOWS_ORACLE_TASK_DRY_RUN_PASS=1 execute=0 principal=SYSTEM watchdog=preflight-first restore=independent'
    exit 0
}
if ($Ack -ne $requiredAck) { throw "Require -Ack $requiredAck" }
if (-not $AssociationOnly -and $SoakSeconds -lt 60) { throw 'SoakSeconds must be 60..1800 unless AssociationOnly is set' }

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
foreach ($value in @($TestSsid, $RestoreSsid, $WifiInterface, $RouterIp, $ControllerIp, $InternetUrl, $DnsName)) {
    if ([string]::IsNullOrWhiteSpace($value) -or $value -match '[\x00-\x1f]') {
        throw 'Task parameters must be non-empty and contain no control characters'
    }
}
if ($ExpectedBssid -and $ExpectedBssid -notmatch '^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$') {
    throw 'ExpectedBssid must be empty or a colon-separated MAC address'
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
    "-Execute -Ack 'OPENMITRASTAR_QTN_5G_WINDOWS_ORACLE_RAM_ONLY' " +
    "-TestSsid $(Quote-PowerShellLiteral $TestSsid) -RestoreSsid $(Quote-PowerShellLiteral $RestoreSsid) " +
    "-WifiInterface $(Quote-PowerShellLiteral $WifiInterface) -RouterIp $(Quote-PowerShellLiteral $RouterIp) " +
    "-ControllerIp $(Quote-PowerShellLiteral $ControllerIp) -ControllerPort $ControllerPort " +
    "-InternetUrl $(Quote-PowerShellLiteral $InternetUrl) -DnsName $(Quote-PowerShellLiteral $DnsName) " +
    "-UploadMiB $UploadMiB -TransferTimeoutSeconds $TransferTimeoutSeconds " +
    "-SoakSeconds $SoakSeconds -OutputPath $(Quote-PowerShellLiteral $result)"
if ($IsolatedL3) { $oracleCommand += " -IsolatedL3 -IsolatedRouterIp '192.168.77.1' -IsolatedClientIp '192.168.77.2'" }
if ($AssociationOnly) { $oracleCommand += " -AssociationOnly" }
if ($MtuProbe) { $oracleCommand += " -MtuProbe" }
if ($SkipThroughput) { $oracleCommand += " -SkipThroughput" }
if ($PingStressCount -gt 0) {
    $oracleCommand += " -PingStressCount $PingStressCount -PingStressPayloadBytes $PingStressPayloadBytes"
}
if ($ExpectedBssid) {
    $oracleCommand += " -ExpectedBssid $(Quote-PowerShellLiteral $ExpectedBssid)"
}
$oracleEncoded = ConvertTo-EncodedPowerShell $oracleCommand
$oracleAction = New-ScheduledTaskAction -Execute $powerShell `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $oracleEncoded"
$oracleTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(-5)
$oracleSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Seconds ($SoakSeconds + 600)) `
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
    -RepetitionDuration (New-TimeSpan -Minutes 30)
$restoreSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -WakeToRun

# Independent restore is registered and proven from SYSTEM before the oracle.
Register-ScheduledTask -TaskName $watchdogTaskName -Action $restoreAction `
    -Trigger $restoreTrigger -Principal $principal -Settings $restoreSettings `
    -Description "Failsafe restore to $RestoreSsid after Quantenna 5 GHz oracle" -Force | Out-Null
Register-ScheduledTask -TaskName $taskName -Action $oracleAction `
    -Trigger $oracleTrigger -Principal $principal -Settings $oracleSettings `
    -Description 'One-shot Quantenna 5 GHz Windows oracle with independent restore' -Force | Out-Null

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
    schema = 'openmitrastar.qtn-5g-windows-oracle-task/v2'
    oracle = 'AELITA@192.168.1.63'
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
} | ConvertTo-Json -Depth 4
