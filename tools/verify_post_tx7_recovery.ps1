param(
    [string]$HostAddress = "192.168.1.90",
    [int]$Timeout = 20,
    [switch]$Execute,
    [string]$Ack,
    [string]$OutputDir
)

$ErrorActionPreference = "Stop"
$AckRequired = "OPENMITRASTAR_POST_TX7_RECOVERY_READONLY"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$StateFile = Join-Path $Root "work\mission-state\HARDWARE_STATE.json"
$RamSsh = Join-Path $PSScriptRoot "ramssh_exec.py"
$ResultVerifier = Join-Path $PSScriptRoot "verify_post_tx7_recovery_result.py"
$Python = "python"

if (-not (Test-Path -LiteralPath $RamSsh -PathType Leaf)) {
    throw "Missing ramssh_exec.py: $RamSsh"
}
if (-not (Test-Path -LiteralPath $ResultVerifier -PathType Leaf)) {
    throw "Missing verify_post_tx7_recovery_result.py: $ResultVerifier"
}
if (-not (Test-Path -LiteralPath $StateFile -PathType Leaf)) {
    throw "Missing hardware state: $StateFile"
}

$State = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $Root "outputs\recovery\post-tx7-5g-hang-$Stamp-READONLY"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
$AllowedRoot = [IO.Path]::GetFullPath((Join-Path $Root "outputs\recovery"))
$AllowedPrefix = $AllowedRoot.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (($OutputDir -ne $AllowedRoot) -and
    (-not $OutputDir.StartsWith($AllowedPrefix, [StringComparison]::OrdinalIgnoreCase))) {
    throw "OutputDir must stay under $AllowedRoot"
}

$RemoteCommand = @'
set +e
echo OMPOSTTX7_RECOVERY_BEGIN
echo OMPOSTTX7_RECOVERY_UNAME_BEGIN
uname -a
echo OMPOSTTX7_RECOVERY_UNAME_END
echo OMPOSTTX7_RECOVERY_UPTIME_BEGIN
cat /proc/uptime
echo OMPOSTTX7_RECOVERY_UPTIME_END
echo OMPOSTTX7_RECOVERY_CMDLINE_BEGIN
cat /proc/cmdline
echo OMPOSTTX7_RECOVERY_CMDLINE_END
echo OMPOSTTX7_RECOVERY_ETH0_BEGIN
cat /sys/class/net/eth0/operstate 2>/dev/null
cat /sys/class/net/eth0/carrier 2>/dev/null
cat /sys/class/net/eth0/statistics/rx_packets 2>/dev/null
cat /sys/class/net/eth0/statistics/tx_packets 2>/dev/null
echo OMPOSTTX7_RECOVERY_ETH0_END
echo OMPOSTTX7_RECOVERY_INTERRUPTS_BEGIN
cat /proc/interrupts
echo OMPOSTTX7_RECOVERY_INTERRUPTS_END
echo OMPOSTTX7_RECOVERY_DMESG_BEGIN
dmesg | tail -n 120
echo OMPOSTTX7_RECOVERY_DMESG_END
echo OMPOSTTX7_RECOVERY_END
'@

$Plan = [ordered]@{
    schema = "openmitrastar.post-tx7-recovery-gate/v1"
    mode = if ($Execute) { "execute" } else { "plan-only" }
    host = $HostAddress
    ack_required = $AckRequired
    output_dir = $OutputDir
    hardware_state = [ordered]@{
        boot_state = $State.current_observation.boot_state
        current_access = $State.current_observation.current_access
        latest_ready_image_sha256 = $State.current_observation.latest_ready_image_sha256
    }
    operations = @(
        "ping IPv4 management address",
        "run one authenticated SSH command through tools/ramssh_exec.py",
        "capture uname/uptime/cmdline/eth0 counters/interrupts/dmesg tail",
        "validate recovery-result.json against captured evidence with tools/verify_post_tx7_recovery_result.py",
        "write local evidence JSON and raw stdout/stderr under outputs/recovery"
    )
    uart_opened = $false
    reboot = $false
    bootenv = $false
    mtd = $false
    flash = $false
}

if (-not $Execute) {
    $Plan | ConvertTo-Json -Depth 6
    Write-Output "OMPOSTTX7_RECOVERY_PLAN_PASS=1"
    exit 0
}

if ($Ack -ne $AckRequired) {
    throw "Execution requires -Ack $AckRequired"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$PingOut = Join-Path $OutputDir "ping.txt"
$SshOut = Join-Path $OutputDir "ssh.stdout.txt"
$SshErr = Join-Path $OutputDir "ssh.stderr.txt"
$ResultVerifierOut = Join-Path $OutputDir "recovery-result-verifier.stdout.json"
$ResultVerifierErr = Join-Path $OutputDir "recovery-result-verifier.stderr.txt"
$ResultJson = Join-Path $OutputDir "recovery-result.json"

$PingExit = 1
try {
    & ping -n 4 $HostAddress *> $PingOut
    $PingExit = $LASTEXITCODE
} catch {
    $_ | Out-String | Set-Content -LiteralPath $PingOut -Encoding UTF8
    $PingExit = 1
}
$PingText = ""
if (Test-Path -LiteralPath $PingOut -PathType Leaf) {
    $PingText = Get-Content -LiteralPath $PingOut -Raw
}
if ($null -eq $PingText) { $PingText = "" }
$PingOk = (
    ($PingExit -eq 0) -and
    ($PingText -match "\bTTL=") -and
    ($PingText -notmatch "unreachable|timed out|inaccesible|agotado|error general|general failure")
)

$SshExit = 1
try {
    & $Python $RamSsh $RemoteCommand --host $HostAddress --timeout $Timeout > $SshOut 2> $SshErr
    $SshExit = $LASTEXITCODE
} catch {
    $_ | Out-String | Set-Content -LiteralPath $SshErr -Encoding UTF8
    $SshExit = 1
}

$Stdout = ""
if (Test-Path -LiteralPath $SshOut -PathType Leaf) {
    $Stdout = Get-Content -LiteralPath $SshOut -Raw
}
if ($null -eq $Stdout) { $Stdout = "" }
$Stderr = ""
if (Test-Path -LiteralPath $SshErr -PathType Leaf) {
    $Stderr = Get-Content -LiteralPath $SshErr -Raw
}
if ($null -eq $Stderr) { $Stderr = "" }

$FatalPattern = "Kernel panic|Oops|BUG:|Unable to handle|EV_TLB|EV_ProtV|Misaligned Access|Misaligned r/w|Invalid Read|Invalid Write|MuC:.*exception|MuC exception|MuC has halted|forcing reboot"
$HasSshMarker = $Stdout -match "OMPOSTTX7_RECOVERY_BEGIN" -and $Stdout -match "OMPOSTTX7_RECOVERY_END"
$KernelOk = $Stdout -match "5\.10\.260-openmitrastar-radiohw"
$Eth0Ok = $false
$Eth0Match = [regex]::Match(
    $Stdout,
    "OMPOSTTX7_RECOVERY_ETH0_BEGIN\r?\n(?<body>.*?)\r?\nOMPOSTTX7_RECOVERY_ETH0_END",
    [System.Text.RegularExpressions.RegexOptions]::Singleline
)
if ($Eth0Match.Success) {
    $Eth0Lines = @(
        $Eth0Match.Groups["body"].Value -split "\r?\n" |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ -ne "" }
    )
    $Eth0Ok = (
        ($Eth0Lines.Count -ge 4) -and
        ($Eth0Lines[0] -in @("up", "unknown")) -and
        ($Eth0Lines[1] -eq "1") -and
        ($Eth0Lines[2] -match "^\d+$") -and
        ($Eth0Lines[3] -match "^\d+$")
    )
}
$FatalFound = $Stdout -match $FatalPattern
$Pass = $PingOk -and ($SshExit -eq 0) -and $HasSshMarker -and $KernelOk -and $Eth0Ok -and (-not $FatalFound)

$Result = [ordered]@{
    schema = "openmitrastar.post-tx7-recovery-result/v1"
    status = if ($Pass) { "RECOVERY_PROVEN_READONLY" } else { "RECOVERY_NOT_PROVEN" }
    pass = [bool]$Pass
    host = $HostAddress
    ping_exit = $PingExit
    ping_ok = [bool]$PingOk
    ssh_exit = $SshExit
    ssh_marker = [bool]$HasSshMarker
    kernel_ok = [bool]$KernelOk
    eth0_ok = [bool]$Eth0Ok
    fatal_found = [bool]$FatalFound
    evidence = [ordered]@{
        output_dir = $OutputDir
        ping = $PingOut
        ssh_stdout = $SshOut
        ssh_stderr = $SshErr
        result_verifier_stdout = $ResultVerifierOut
        result_verifier_stderr = $ResultVerifierErr
        result_json = $ResultJson
    }
    mutations = [ordered]@{
        uart_opened = $false
        reboot = $false
        bootenv = $false
        mtd = $false
        flash = $false
    }
}

$Result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ResultJson -Encoding UTF8
$ResultVerifierExit = 1
try {
    & $Python $ResultVerifier `
        $ResultJson `
        --output-dir $OutputDir > $ResultVerifierOut 2> $ResultVerifierErr
    $ResultVerifierExit = $LASTEXITCODE
} catch {
    $_ | Out-String | Set-Content -LiteralPath $ResultVerifierErr -Encoding UTF8
    $ResultVerifierExit = 1
}

$ResultVerifierOk = $false
$ResultVerifierStatus = "POST_TX7_RECOVERY_RESULT_UNPARSEABLE"
try {
    $ResultVerifierStdout = Get-Content -LiteralPath $ResultVerifierOut -Raw
    $ResultVerifierReport = $ResultVerifierStdout | ConvertFrom-Json
    $ResultVerifierOk = [bool]$ResultVerifierReport.ok
    $ResultVerifierStatus = if ($ResultVerifierOk) { "POST_TX7_RECOVERY_RESULT_VERIFIED_READONLY" } else { "POST_TX7_RECOVERY_RESULT_NOT_VERIFIED" }
} catch {
    $ResultVerifierOk = $false
}

$Result["result_verifier_exit"] = $ResultVerifierExit
$Result["result_verifier_ok"] = [bool]$ResultVerifierOk
$Result["result_verifier_status"] = $ResultVerifierStatus
$Result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ResultJson -Encoding UTF8
$Result | ConvertTo-Json -Depth 6
$FinalPass = $Pass -and ($ResultVerifierExit -eq 0) -and $ResultVerifierOk
if ($FinalPass) {
    Write-Output "OMPOSTTX7_RECOVERY_PASS=1 evidence=$OutputDir"
    exit 0
}
Write-Output "OMPOSTTX7_RECOVERY_PASS=0 evidence=$OutputDir"
exit 2
