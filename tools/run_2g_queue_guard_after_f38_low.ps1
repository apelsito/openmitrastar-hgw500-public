[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("apply", "restore")]
    [string]$Action = "apply",
    [string]$RouterHost = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "$env:USERPROFILE\.ssh\id_ed25519",
    [double]$Min2gMbps = 5.0,
    [string]$OutputDir = "",
    [switch]$Execute,
    [string]$Ack = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$triageScript = Join-Path $PSScriptRoot "triage_f38_postflash.ps1"
$remoteScript = Join-Path $PSScriptRoot "apply_2g_queue_guard_rootfs_remote.sh"
$postGateScript = Join-Path $PSScriptRoot "post_flash_f5_radio_gate.ps1"
$requiredAck = "OPENMITRASTAR_2G_QUEUE_GUARD_AFTER_F38_LOW"

if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\2g-queue-guard-after-f38-low-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Invoke-Triage {
    $raw = & pwsh.exe -NoProfile -ExecutionPolicy Bypass -File $triageScript `
        -RouterHost $RouterHost -Min2gMbps $Min2gMbps
    if ($LASTEXITCODE -ne 0) {
        throw "triage_f38_postflash.ps1 failed rc=$LASTEXITCODE"
    }
    return ($raw | ConvertFrom-Json)
}

function New-SshArgs([string]$KnownHosts) {
    return @(
        "-i", $RouterKey,
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=$KnownHosts",
        "-o", "HostKeyAlgorithms=+ssh-rsa",
        "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa",
        "-o", "LogLevel=ERROR"
    )
}

function Refresh-KnownHosts([string]$KnownHosts) {
    $sshKeygen = Join-Path $env:WINDIR "System32\OpenSSH\ssh-keygen.exe"
    $sshKeyscan = Join-Path $env:WINDIR "System32\OpenSSH\ssh-keyscan.exe"
    if (Test-Path -LiteralPath $KnownHosts) {
        & $sshKeygen -R $RouterHost -f $KnownHosts *> $null
    }
    $scan = & $sshKeyscan -T 5 -t ed25519,rsa $RouterHost 2>$null |
        Where-Object { $_ -and -not $_.StartsWith("#") }
    if (-not $scan) {
        throw "ssh-keyscan returned no host key for $RouterHost"
    }
    $scan | Set-Content -Encoding ascii -LiteralPath $KnownHosts
}

$triage = Invoke-Triage
$readyLow = [string]$triage.terminal_state -eq "READY_2G_LOW_ANALYZE_BE_QUEUE"
$readyRestore = [string]$triage.terminal_state -in @("READY_2G_PASS", "READY_2G_LOW_ANALYZE_BE_QUEUE", "READY_2G_FAIL_ANALYZE_EVIDENCE")
$allowed = if ($Action -eq "apply") { $readyLow } else { $readyRestore }

$result = [ordered]@{
    schema = "openmitrastar.f38-2g-queue-guard/v1"
    checked_at = (Get-Date).ToString("o")
    action = $Action
    execute = [bool]$Execute
    allowed = $allowed
    triage_terminal_state = $triage.terminal_state
    triage_next_action = $triage.next_action
    two_g_speed_Mbps = $triage.postflash_result.two_g_speed_Mbps
    two_g_meets_min = $triage.postflash_result.two_g_meets_min
    output_dir = $OutputDir
    remote_script = "/tmp/om-2g-queue-guard.sh"
    expected_params = [ordered]@{
        hgw500_tx_queue_guard = if ($Action -eq "apply") { "Y" } else { "N" }
        hgw500_tx_queue_guard_high = if ($Action -eq "apply") { 16 } else { $null }
        hgw500_tx_queue_guard_low = if ($Action -eq "apply") { 8 } else { $null }
        hgw500_tx_reclaim_poll = if ($Action -eq "apply") { "Y" } else { "N" }
    }
    safety = [ordered]@{
        opens_uart = $false
        flash = $false
        mtd = $false
        bootenv = $false
        requires_stable_ssh = $true
        apply_requires_ready_2g_low = $true
    }
}

if (-not $allowed) {
    $result.state = "NOT_READY"
    $result | ConvertTo-Json -Depth 8
    exit 2
}

if (-not $Execute) {
    $result.state = "READY_DRY_RUN"
    $result.next_command = "pwsh -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath -Action $Action -Execute -Ack $requiredAck"
    $result | ConvertTo-Json -Depth 8
    exit 0
}

if ($Ack -ne $requiredAck) {
    throw "execute requires -Ack $requiredAck"
}
if (-not (Test-Path -LiteralPath $remoteScript -PathType Leaf)) {
    throw "missing remote script: $remoteScript"
}

$knownHosts = Join-Path $OutputDir "known_hosts"
$stdout = Join-Path $OutputDir "queue-guard.stdout.log"
$stderr = Join-Path $OutputDir "queue-guard.stderr.log"
$postStdout = Join-Path $OutputDir "post-gate.stdout.log"
$postStderr = Join-Path $OutputDir "post-gate.stderr.log"
$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$scp = Join-Path $env:WINDIR "System32\OpenSSH\scp.exe"

Refresh-KnownHosts $knownHosts
$common = New-SshArgs $knownHosts
& $scp @common $remoteScript "$RouterUser@$RouterHost`:/tmp/om-2g-queue-guard.sh" > $stdout 2> $stderr
if ($LASTEXITCODE -ne 0) {
    throw "scp queue guard failed rc=$LASTEXITCODE"
}
& $ssh @common "$RouterUser@$RouterHost" "chmod 0700 /tmp/om-2g-queue-guard.sh && /tmp/om-2g-queue-guard.sh $Action" >> $stdout 2>> $stderr
$applyRc = $LASTEXITCODE
$postArgs = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", $postGateScript,
    "-HostAddress", $RouterHost,
    "-RouterUser", $RouterUser,
    "-RouterKey", $RouterKey,
    "-Run2gProbe",
    "-Min2gMbps", "$Min2gMbps",
    "-OutputDir", (Join-Path $OutputDir "post-gate")
)
& pwsh.exe @postArgs > $postStdout 2> $postStderr
$postRc = $LASTEXITCODE

$result.state = if ($applyRc -eq 0 -and $postRc -eq 0) { "PASS" } else { "FAIL" }
$result.apply_rc = $applyRc
$result.post_gate_rc = $postRc
$result.stdout = $stdout
$result.stderr = $stderr
$result.post_stdout = $postStdout
$result.post_stderr = $postStderr
$result | ConvertTo-Json -Depth 8 | Tee-Object -FilePath (Join-Path $OutputDir "result.json")
exit $(if ($applyRc -eq 0 -and $postRc -eq 0) { 0 } else { 1 })
