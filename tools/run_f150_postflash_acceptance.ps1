[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$HostAddress = "192.168.1.90",
    [string]$RouterKey = "$env:USERPROFILE\.ssh\id_ed25519",
    [ValidateRange(60, 600)]
    [int]$ReadyTimeoutSeconds = 240,
    [ValidateRange(60, 900)]
    [int]$CertificationSeconds = 120
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$requiredAck = "OPENMITRASTAR_F150_POSTFLASH_ACCEPTANCE"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outputRoot = Join-Path $root "outputs\f3-certification\qtn-5g-f150-autostart-$stamp"
$gateDir = Join-Path $outputRoot "postflash-gate"
$certDir = Join-Path $outputRoot "aelita"

if (-not $Execute) {
    [ordered]@{
        schema = "openmitrastar.f150-postflash-acceptance-plan/v1"
        mode = "dry-run"
        router = $HostAddress
        waits_for_autostart = $true
        invokes_radio5_start = $false
        ready_timeout_seconds = $ReadyTimeoutSeconds
        certification_seconds = $CertificationSeconds
        required_ack = $requiredAck
    } | ConvertTo-Json -Depth 5
    exit 0
}
if ($Ack -ne $requiredAck) { throw "Require -Ack $requiredAck" }

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$knownHosts = Join-Path $outputRoot "known_hosts"
$deadline = (Get-Date).AddSeconds($ReadyTimeoutSeconds)
$ready = $false
while ((Get-Date) -lt $deadline) {
    $state = & $ssh -i $RouterKey -o IdentitiesOnly=yes -o BatchMode=yes `
        -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new `
        -o "UserKnownHostsFile=$knownHosts" -o LogLevel=ERROR "root@$HostAddress" `
        "cat /run/openmitrastar/radio5g/state 2>/dev/null || true" 2>$null
    if (($state | Out-String).Trim() -eq "ready") {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 5
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File (Join-Path $root "tools\post_flash_f13x_radio_gate.ps1") `
    -Profile F150 -HostAddress $HostAddress -RouterKey $RouterKey -OutputDir $gateDir
if ($LASTEXITCODE -ne 0) { throw "F150 post-flash gate command failed" }
$gate = Get-Content -Raw -LiteralPath (Join-Path $gateDir "status.json") | ConvertFrom-Json
if (-not $ready -or $gate.state -ne "PASS_F150_5G_AUTOSTART_READY_READONLY") {
    throw "F150 autonomous startup gate failed: ready=$ready state=$($gate.state)"
}

& python (Join-Path $root "tools\run_f142_5g_aelita_certification.py") `
    --execute --ack OPENMITRASTAR_F150_5G_AELITA_CERTIFICATION `
    --profile F150 --router-host $HostAddress --seconds $CertificationSeconds `
    --expected-txpower-dbm 21 --output-dir $certDir
if ($LASTEXITCODE -ne 0) { throw "F150 AELITA certification failed" }

[ordered]@{
    schema = "openmitrastar.f150-postflash-acceptance/v1"
    status = "PASS"
    autonomous_radio5_ready = $true
    postflash_gate = $gateDir
    aelita_certification = $certDir
} | ConvertTo-Json -Depth 5
