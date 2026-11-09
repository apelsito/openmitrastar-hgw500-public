[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$RouterHost = "192.168.1.90",
    [string]$ExpectedVersion = "lyoko-foundation-3.7-f222-device",
    [string]$KnownHostsPath = "$HOME\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f222-device-bound\known_hosts.f222",
    [ValidateRange(1, 3)][int]$Seconds = 1,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$requiredAck = "OPENMITRASTAR_FRONTPANEL_LED_IDENTIFY"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $OutputDir = Join-Path $root "outputs\hardware\frontpanel-led-identify-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
$knownHosts = [IO.Path]::GetFullPath($KnownHostsPath)

[ordered]@{
    schema = "openmitrastar.frontpanel-led-identification-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    router = $RouterHost
    expected_version = $ExpectedVersion
    seconds_per_step = $Seconds
    channels = @("wifi2g", "wifi5g", "signalb", "signalg", "signalr")
    composite_colours = @("blue", "green", "red", "amber", "cyan", "magenta", "white")
    restoration = "mandatory snapshot restore"
    mtd_writes = $false
    radio_changes = $false
} | ConvertTo-Json -Depth 5

if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing LED identification: exact -Ack is required" }
if (-not (Test-Path -LiteralPath $knownHosts)) { throw "known_hosts file is missing" }
$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"

function Invoke-Router([string]$Command) {
    $result = & $ssh -i "$env:USERPROFILE\.ssh\id_ed25519" -o IdentitiesOnly=yes -o BatchMode=yes `
        -o ConnectTimeout=8 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$knownHosts" -o LogLevel=ERROR `
        "root@$RouterHost" $Command 2>&1
    [pscustomobject]@{ Rc = $LASTEXITCODE; Text = ($result -join "`n") }
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$preflight = Invoke-Router 'test -x /usr/sbin/om-ledctl; sed -n "s/^OPENMITRASTAR_PRODUCT_VERSION=//p" /etc/openmitrastar/release; /usr/sbin/om-ledctl status'
if ($preflight.Rc -ne 0 -or $preflight.Text -notmatch [regex]::Escape($ExpectedVersion)) { throw "front-panel preflight failed" }
$before = ($preflight.Text -split "`r?`n" | Where-Object { $_ -match '^\{"schema":"openmitrastar\.led-status/v1"' } | Select-Object -Last 1)
if (-not $before) { throw "LED snapshot before test is missing" }
$preflight.Text | Set-Content -LiteralPath (Join-Path $OutputDir "before.log") -Encoding utf8

$identify = Invoke-Router "/usr/sbin/om-ledctl --diagnostic identify $Seconds"
$identify.Text | Set-Content -LiteralPath (Join-Path $OutputDir "identify.log") -Encoding utf8
if ($identify.Rc -ne 0 -or $identify.Text -notmatch 'OMLED_IDENTIFY_PASS restored=1') { throw "LED identify or restoration failed" }

$post = Invoke-Router '/usr/sbin/om-ledctl status; printf "FATAL_COUNT="; dmesg | grep -Eic "Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|Misaligned Access|Machine Check" || true'
$post.Text | Set-Content -LiteralPath (Join-Path $OutputDir "after.log") -Encoding utf8
$after = ($post.Text -split "`r?`n" | Where-Object { $_ -match '^\{"schema":"openmitrastar\.led-status/v1"' } | Select-Object -Last 1)
$checks = [ordered]@{
    version = $preflight.Text -match [regex]::Escape($ExpectedVersion)
    identify_completed = $identify.Text -match 'OMLED_IDENTIFY_PASS restored=1'
    restored_exactly = [bool]$before -and $before -eq $after
    no_fatal = $post.Text -match 'FATAL_COUNT=0'
}
$result = [ordered]@{
    schema = "openmitrastar.frontpanel-led-identification/v1"
    status = if (($checks.Values -notcontains $false)) { "PASS" } else { "FAIL" }
    checks = $checks
    visual_mapping = "REQUIRES_OBSERVER_CONFIRMATION"
    mtd_writes = $false
    radio_changes = $false
}
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $OutputDir "result.json") -Encoding ascii
$result | ConvertTo-Json -Depth 5
if ($result.status -ne "PASS") { exit 1 }
