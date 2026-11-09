[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$RouterHost = "192.168.1.90",
    [string]$KeyPath = "$HOME\.ssh\id_ed25519",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if ($Execute) {
    throw "F235 is superseded and must not be tested on hardware; use the F237 gate"
}

$requiredAck = "OPENMITRASTAR_F235_DUAL_RADIO_CONTROL_PHYSICAL"
$expectedVersion = "lyoko-foundation-4.4-f235-device"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
if (-not $OutputDir) {
    $OutputDir = Join-Path $root "outputs\postflash\f235-dual-radio-control-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$key = [IO.Path]::GetFullPath($KeyPath)

function Invoke-Router([string]$Command) {
    $output = & $ssh -i $key -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 `
        -o StrictHostKeyChecking=yes -o LogLevel=ERROR "root@$RouterHost" $Command 2>&1
    $rc = $LASTEXITCODE
    [pscustomobject]@{ Rc = $rc; Text = ($output -join "`n") }
}

function Read-JsonBody([string]$Text) {
    $line = ($Text -split "`r?`n" | Where-Object { $_ -match '^\{' } | Select-Object -Last 1)
    if (-not $line) { throw "No JSON payload in router response" }
    $line | ConvertFrom-Json
}

function Get-RadioContract([string]$Band) {
    $result = Invoke-Router "/usr/sbin/om-radioctl contract $Band"
    if ($result.Rc -ne 0) { throw "Cannot read $Band contract: $($result.Text)" }
    Read-JsonBody $result.Text
}

function Assert-PlatformHealthy {
    $result = Invoke-Router 'test -e /sys/class/net/br0/brif/eth0 -a -e /sys/class/net/br0/brif/wlan0 -a -e /sys/class/net/br0/brif/wifi0 && /usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 ping && /usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping && test "$(cat /run/openmitrastar/boot-state)" = ready && test "$(dmesg | grep -Eic "MuC:.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|Misaligned Access")" = 0'
    if ($result.Rc -ne 0 -or $result.Text -notmatch 'PONG') { throw "Platform health gate failed: $($result.Text)" }
}

function Invoke-RadioCycle([string]$Band, [int]$Channel, [int]$Bandwidth) {
    $before = Get-RadioContract $Band
    $owner = -join ((1..64) | ForEach-Object { '0123456789abcdef'[(Get-Random -Maximum 16)] })
    $body = "channel=$Channel&bandwidth=$Bandwidth"
    $stageCommand = "printf '%s' '$body' | OM_CONFIG_OWNER=$owner /usr/sbin/om-radioctl stage_config $Band"
    $stageResult = Invoke-Router $stageCommand
    if ($stageResult.Rc -ne 0) { throw "$Band stage failed: $($stageResult.Text)" }
    $stage = Read-JsonBody $stageResult.Text
    $transactionId = [string]$stage.transaction_id
    if ($transactionId -notmatch '^[0-9a-f]{64}$') { throw "$Band transaction id invalid" }

    try {
        $applyResult = Invoke-Router "OM_CONFIG_OWNER=$owner OM_CONFIG_TXN_ID=$transactionId /usr/sbin/om-radioctl apply_config"
        if ($applyResult.Rc -ne 0) { throw "$Band apply failed: $($applyResult.Text)" }
        $apply = Read-JsonBody $applyResult.Text
        if ($apply.verified -ne $true) { throw "$Band apply was not verified" }
        Start-Sleep -Seconds 8
        Assert-PlatformHealthy
        $after = Get-RadioContract $Band
        if ([int]$after.snapshot.status.channel -ne $Channel -or [int]$after.snapshot.status.bandwidth -ne $Bandwidth) {
            throw "$Band readback mismatch"
        }
    } finally {
        $rollbackResult = Invoke-Router "OM_CONFIG_OWNER=$owner OM_CONFIG_TXN_ID=$transactionId /usr/sbin/om-radioctl rollback_config"
        $rollback = Read-JsonBody $rollbackResult.Text
        if ($rollbackResult.Rc -ne 0 -or $rollback.verified -ne $true) {
            throw "$Band rollback failed: $($rollbackResult.Text)"
        }
    }

    Start-Sleep -Seconds 8
    Assert-PlatformHealthy
    $restored = Get-RadioContract $Band
    if ([int]$restored.snapshot.status.channel -ne [int]$before.snapshot.status.channel -or
        [int]$restored.snapshot.status.bandwidth -ne [int]$before.snapshot.status.bandwidth) {
        throw "$Band rollback readback mismatch"
    }
    [ordered]@{
        band = $Band
        before = @{ channel = $before.snapshot.status.channel; bandwidth = $before.snapshot.status.bandwidth }
        tested = @{ channel = $Channel; bandwidth = $Bandwidth }
        restored = @{ channel = $restored.snapshot.status.channel; bandwidth = $restored.snapshot.status.bandwidth }
        status = "PASS"
    }
}

$plan = [ordered]@{
    schema = "openmitrastar.f235-dual-radio-control-gate-plan/v1"
    mode = if ($Execute) { "execute" } else { "dry-run" }
    router = $RouterHost
    required_firmware = $expectedVersion
    mutations = @("2g channel/bandwidth", "5g non-DFS channel/bandwidth")
    rollback = "mandatory after each band"
    flash = $false
    uart = $false
}
$plan | ConvertTo-Json -Depth 5
if (-not $Execute) { exit 0 }
if ($Ack -ne $requiredAck) { throw "Refusing physical gate: exact -Ack is required" }

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$release = Invoke-Router "sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release"
if ($release.Rc -ne 0 -or $release.Text.Trim() -ne $expectedVersion) {
    throw "F235 is not installed: $($release.Text.Trim())"
}
Assert-PlatformHealthy
$radio2 = Get-RadioContract "2g"
$radio5 = Get-RadioContract "5g"
$channel2 = if ([int]$radio2.snapshot.status.channel -eq 6) { 1 } else { 6 }
$bandwidth2 = if ([int]$radio2.snapshot.status.bandwidth -eq 40) { 20 } else { 40 }
$channel5 = if ([int]$radio5.snapshot.status.channel -eq 44) { 36 } else { 44 }
$bandwidth5 = if ([int]$radio5.snapshot.status.bandwidth -eq 40) { 80 } else { 40 }

$result = [ordered]@{
    schema = "openmitrastar.f235-dual-radio-control-gate/v1"
    started_at = [DateTime]::UtcNow.ToString("o")
    firmware = $expectedVersion
    radio2 = Invoke-RadioCycle "2g" $channel2 $bandwidth2
    radio5 = Invoke-RadioCycle "5g" $channel5 $bandwidth5
    final_platform = "PASS"
    status = "PASS"
    hardware_actions = @{ flash = $false; uart = $false; radio_mutation = $true }
}
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDir "result.json") -Encoding ascii
Write-Output "OMF235_DUAL_RADIO_CONTROL_PASS=1 output=$OutputDir"
