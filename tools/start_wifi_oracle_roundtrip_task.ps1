[CmdletBinding()]
param(
    [string]$SourceScript = (Join-Path $PSScriptRoot 'run_wifi_oracle_roundtrip.ps1'),
    [string]$WatchdogSourceScript = (Join-Path $PSScriptRoot 'restore_wifi_oracle_watchdog.ps1'),
    [string]$TestSsid = 'OpenMitraStar-2G-DIAG',
    [string]$RestoreSsid = 'MOVISTAR-WIFI6-A348',
    [string]$WifiInterface = 'Wi-Fi',
    [string]$RouterIp = '192.168.1.90',
    [string]$ControllerUrl = 'http://192.168.1.43:8081/downlink-4m.bin',
    [ValidateRange(2, 15)][int]$RestoreWatchdogMinutes = 6
)

$ErrorActionPreference = 'Stop'
$root = 'C:\ProgramData\OpenMitraStar\oracle'
$script = Join-Path $root 'run_wifi_oracle_roundtrip.ps1'
$watchdogScript = Join-Path $root 'restore_wifi_oracle_watchdog.ps1'
$result = Join-Path $root 'roundtrip-result.json'
$watchdogResult = Join-Path $root 'restore-watchdog-result.json'
$taskName = 'OpenMitraStar-WiFiOracle-OneShot'
$watchdogTaskName = 'OpenMitraStar-WiFiOracle-Restore'
$powerShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$netsh = Join-Path $env:WINDIR 'System32\netsh.exe'

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
    $aclArguments = @(
        $LiteralPath,
        '/inheritance:r',
        '/grant:r',
        $systemGrant,
        $adminGrant
    )
    & icacls.exe @aclArguments | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to protect ACL on $LiteralPath"
    }
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
foreach ($value in @($TestSsid, $RestoreSsid, $WifiInterface, $RouterIp, $ControllerUrl)) {
    if ([string]::IsNullOrWhiteSpace($value) -or $value -match '[\x00-\x1f]') {
        throw 'Task parameters must be non-empty and contain no control characters'
    }
}
if ($TestSsid -eq $RestoreSsid) {
    throw 'TestSsid and RestoreSsid must be different'
}
$wifiAdapter = Get-NetAdapter -Name $WifiInterface -ErrorAction Stop
if ($wifiAdapter.InterfaceDescription -notmatch 'Wireless|Wi-Fi|802\.11') {
    throw "Interface '$WifiInterface' does not look like a Wi-Fi adapter"
}
$restoreProfileCheck = (& $netsh wlan show profile "name=$RestoreSsid" "interface=$WifiInterface" 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Restore profile '$RestoreSsid' is not available on '$WifiInterface': $restoreProfileCheck"
}
$sourceItem = Get-Item -LiteralPath $SourceScript -ErrorAction Stop
if ($sourceItem.PSIsContainer) {
    throw 'SourceScript must be a file'
}
if ($sourceItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'SourceScript must not be a reparse point'
}
$watchdogSourceItem = Get-Item -LiteralPath $WatchdogSourceScript -ErrorAction Stop
if ($watchdogSourceItem.PSIsContainer -or ($watchdogSourceItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'WatchdogSourceScript must be a regular file, not a reparse point'
}

if (Test-Path -LiteralPath $root) {
    $rootItem = Get-Item -LiteralPath $root -Force
    if ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Oracle ProgramData root must not be a reparse point'
    }
}
New-Item -ItemType Directory -Force -Path $root | Out-Null
Protect-SystemOnlyPath -LiteralPath $root
$staging = Join-Path $root 'run_wifi_oracle_roundtrip.ps1.new'
Remove-Item -LiteralPath $staging -Force -ErrorAction SilentlyContinue
Copy-Item -LiteralPath $sourceItem.FullName -Destination $staging -Force
Protect-SystemOnlyPath -LiteralPath $staging
Remove-Item -LiteralPath $script -Force -ErrorAction SilentlyContinue
Move-Item -LiteralPath $staging -Destination $script -Force
Protect-SystemOnlyPath -LiteralPath $script
$watchdogStaging = Join-Path $root 'restore_wifi_oracle_watchdog.ps1.new'
Remove-Item -LiteralPath $watchdogStaging -Force -ErrorAction SilentlyContinue
Copy-Item -LiteralPath $watchdogSourceItem.FullName -Destination $watchdogStaging -Force
Protect-SystemOnlyPath -LiteralPath $watchdogStaging
Remove-Item -LiteralPath $watchdogScript -Force -ErrorAction SilentlyContinue
Move-Item -LiteralPath $watchdogStaging -Destination $watchdogScript -Force
Protect-SystemOnlyPath -LiteralPath $watchdogScript

$sourceHash = (Get-FileHash -LiteralPath $sourceItem.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$stagedHash = (Get-FileHash -LiteralPath $script -Algorithm SHA256).Hash.ToLowerInvariant()
$watchdogSourceHash = (Get-FileHash -LiteralPath $watchdogSourceItem.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$watchdogStagedHash = (Get-FileHash -LiteralPath $watchdogScript -Algorithm SHA256).Hash.ToLowerInvariant()
if ($sourceHash -ne $stagedHash) {
    throw 'Staged oracle script hash mismatch'
}
if ($watchdogSourceHash -ne $watchdogStagedHash) {
    throw 'Staged watchdog script hash mismatch'
}
Remove-Item -LiteralPath $result -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $watchdogResult -Force -ErrorAction SilentlyContinue

Remove-StaleTask -Name $taskName
Remove-StaleTask -Name $watchdogTaskName

$quotedScript = Quote-PowerShellLiteral $script
$quotedTestSsid = Quote-PowerShellLiteral $TestSsid
$quotedRestoreSsid = Quote-PowerShellLiteral $RestoreSsid
$quotedInterface = Quote-PowerShellLiteral $WifiInterface
$quotedRouterIp = Quote-PowerShellLiteral $RouterIp
$quotedController = Quote-PowerShellLiteral $ControllerUrl
$quotedResult = Quote-PowerShellLiteral $result
$quotedNetsh = Quote-PowerShellLiteral $netsh
$quotedWatchdogScript = Quote-PowerShellLiteral $watchdogScript
$quotedWatchdogResult = Quote-PowerShellLiteral $watchdogResult

$oracleCommand = "& $quotedScript -TestSsid $quotedTestSsid -RestoreSsid $quotedRestoreSsid " +
    "-WifiInterface $quotedInterface -RouterIp $quotedRouterIp " +
    "-ControllerUrl $quotedController -OutputPath $quotedResult"
$oracleEncoded = ConvertTo-EncodedPowerShell $oracleCommand
$oracleActionArguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $oracleEncoded"
$oracleAction = New-ScheduledTaskAction -Execute $powerShell -Argument $oracleActionArguments

# The trigger is in the past and StartWhenAvailable is disabled. Only the
# explicit Start-ScheduledTask call can launch the one-shot oracle.
$oracleTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(-5)
$oracleSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 8) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest

$restoreCommand = "& $quotedWatchdogScript -RestoreSsid $quotedRestoreSsid " +
    "-WifiInterface $quotedInterface -StatusPath $quotedWatchdogResult"
$restoreEncoded = ConvertTo-EncodedPowerShell $restoreCommand
$restoreActionArguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $restoreEncoded"
$restoreAction = New-ScheduledTaskAction -Execute $powerShell -Argument $restoreActionArguments
$restoreTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes($RestoreWatchdogMinutes) -RepetitionInterval (New-TimeSpan -Minutes 2) -RepetitionDuration (New-TimeSpan -Minutes 20)
$restoreSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -WakeToRun

# Register the independent restore watchdog first. If the oracle process is
# terminated before its finally block, SYSTEM reconnects to the normal SSID.
Register-ScheduledTask -TaskName $watchdogTaskName -Action $restoreAction -Trigger $restoreTrigger -Principal $principal -Settings $restoreSettings -Description "Failsafe restore to $RestoreSsid after Wi-Fi oracle" -Force | Out-Null
Register-ScheduledTask -TaskName $taskName -Action $oracleAction -Trigger $oracleTrigger -Principal $principal -Settings $oracleSettings -Description 'One-shot OpenMitraStar Wi-Fi oracle with guaranteed restore' -Force | Out-Null

# Prove from the actual SYSTEM context that the watchdog can see the all-user
# restore profile before allowing the disruptive oracle to start.
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

[pscustomobject]@{
    schema = 'openmitrastar.windows-wifi-oracle-task/v2'
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
} | ConvertTo-Json -Depth 4
