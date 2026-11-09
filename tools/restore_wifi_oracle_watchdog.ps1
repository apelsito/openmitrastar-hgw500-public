[CmdletBinding()]
param(
    [ValidateLength(1, 32)][string]$RestoreSsid = 'MOVISTAR-WIFI6-A348',
    [ValidateNotNullOrEmpty()][string]$WifiInterface = 'Wi-Fi',
    [ValidateNotNullOrEmpty()][string]$StatusPath = 'C:\ProgramData\OpenMitraStar\oracle\restore-watchdog-result.json',
    [ValidateRange(5, 60)][int]$VerifySeconds = 20
)

$ErrorActionPreference = 'Continue'
$netsh = Join-Path $env:WINDIR 'System32\netsh.exe'

function Test-Restored {
    $profile = Get-NetConnectionProfile -InterfaceAlias $WifiInterface -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq $RestoreSsid } |
        Select-Object -First 1
    return $null -ne $profile
}

function Save-WatchdogStatus {
    param([Parameter(Mandatory)]$Data)
    try {
        $directory = Split-Path -Parent $StatusPath
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
        $temporary = "$StatusPath.tmp"
        $json = $Data | ConvertTo-Json -Depth 4
        [IO.File]::WriteAllText($temporary, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
        Move-Item -LiteralPath $temporary -Destination $StatusPath -Force
    } catch {
        [Console]::Error.WriteLine("Watchdog status write failed: $($_.Exception.Message)")
    }
}

$status = [ordered]@{
    schema = 'openmitrastar.windows-wifi-restore-watchdog/v1'
    attempted_at = (Get-Date).ToString('o')
    restore_ssid = $RestoreSsid
    interface = $WifiInterface
    already_restored = $false
    profile_available = $false
    connect_exit_code = $null
    restored = $false
    error = $null
}

try {
    if (Test-Restored) {
        $status.already_restored = $true
        $status.profile_available = $true
        $status.restored = $true
        Save-WatchdogStatus -Data $status
        exit 0
    }

    $profileOutput = (& $netsh wlan show profile "name=$RestoreSsid" "interface=$WifiInterface" 2>&1 | Out-String).Trim()
    $status.profile_available = $LASTEXITCODE -eq 0
    if (-not $status.profile_available) {
        throw "Restore profile unavailable to SYSTEM: $profileOutput"
    }

    $connectOutput = (& $netsh wlan connect "name=$RestoreSsid" "ssid=$RestoreSsid" "interface=$WifiInterface" 2>&1 | Out-String).Trim()
    $status.connect_exit_code = $LASTEXITCODE
    if ($status.connect_exit_code -ne 0) {
        throw "netsh restore failed: $connectOutput"
    }

    for ($attempt = 0; $attempt -lt $VerifySeconds; $attempt++) {
        if (Test-Restored) {
            $status.restored = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $status.restored) {
        throw "Restore command completed but '$RestoreSsid' was not observed"
    }
} catch {
    $status.error = $_.Exception.Message
} finally {
    $status.finished_at = (Get-Date).ToString('o')
    Save-WatchdogStatus -Data $status
}

if ($status.restored) {
    exit 0
}
exit 20
