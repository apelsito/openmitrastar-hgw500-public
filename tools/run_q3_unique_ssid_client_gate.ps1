param(
    [string]$Port = "COM3",
    [string]$Image = "linux510-q3-pm0-calibration-v1-RAM-TEST-NO-FLASH.bin",
    [string]$ServerIp = "192.168.1.43",
    [string]$RouterIp = "192.168.1.90",
    [int]$DurationSeconds = 180
)

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$raw = Join-Path $root "outputs\uart-live\q3-client-light-$stamp.log"

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    (Join-Path $PSScriptRoot "reboot_boot_ramssh.ps1") `
    -Port $Port -Filename $Image -ServerIp $ServerIp `
    -ClientIp $RouterIp -SshHost $RouterIp -AutonomousEntropy `
    -TimeoutSeconds 420 -AutobootWaitSeconds 120
if ($LASTEXITCODE -ne 0) {
    throw "Q3 RAM boot failed"
}

& python.exe (Join-Path $PSScriptRoot "q3_client_stream_single_session.py") `
    --host $RouterIp --seconds $DurationSeconds --interval 1 --output $raw
if ($LASTEXITCODE -ne 0) {
    throw "Q3 client monitor detected management loss; evidence: $raw"
}

Write-Host "OMQ3_UNIQUE_CLIENT_GATE_PASS image=$Image telemetry=$raw"
