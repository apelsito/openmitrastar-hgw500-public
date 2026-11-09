[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$HostAddress = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "/workspace/user-home\Desktop\MitraStar\.codex_tmp\openmitrastar_ramssh_client_ed25519",
    [string]$OracleHost = "192.168.1.63",
    [string]$OracleUser = "AELITA",
    [string]$ControllerUrl = "http://192.168.1.43:8008/speed.bin",
    [double]$Min2gMbps = 5.0,
    [ValidateRange(20, 600)]
    [int]$SshTimeoutSeconds = 180,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f76-stage-gate-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$resultPath = Join-Path $OutputDir "result.json"
$twoGDir = Join-Path $OutputDir "two-g"
$stageOut = Join-Path $OutputDir "five-g-stage-modules.stdout.log"
$stageErr = Join-Path $OutputDir "five-g-stage-modules.stderr.log"

function Write-JsonFile([string]$Path, [hashtable]$Payload) {
    $Payload.updated_at = (Get-Date).ToString("o")
    $Payload.output_dir = $OutputDir
    $Payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $Path
}

function Test-TcpQuiet([string]$HostName, [int]$Port, [int]$TimeoutMs = 2000) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Read-JsonOrNull([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json } catch { return $null }
}

function Invoke-StageModules {
    $ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
    $knownHosts = Join-Path $OutputDir "known_hosts"
    $sshKeyscan = Join-Path $env:WINDIR "System32\OpenSSH\ssh-keyscan.exe"

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $scanText = & $sshKeyscan -T 5 -t ed25519,rsa $HostAddress 2>&1
    $ErrorActionPreference = $previousErrorActionPreference
    $scan = @($scanText | ForEach-Object { [string]$_ } | Where-Object { $_ -and -not $_.StartsWith("#") })
    if ($scan) { $scan | Set-Content -Encoding ascii -LiteralPath $knownHosts }

    $remote = @'
set -u
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH
echo OMF76_STAGE_MODULES_BEGIN
echo SECTION_PRE
uname -a
brctl show 2>/dev/null || true
ls -1 /sys/class/net/br0/brif 2>/dev/null || true
echo SECTION_STAGE_STOP
OM_RADIO5_STAGE_STOP=modules /usr/sbin/om-radio5-start
stage_rc=$?
echo OMF76_STAGE_MODULES_RC="$stage_rc"
echo SECTION_POST_MODULES
lsmod 2>/dev/null | grep -E 'qdrv|wlan|hbm|switch_tqe|switch_emac|board_compat|topaz_congest_queue|emac_lib|qtn' || true
if [ -e /sys/class/net/br0/brif ]; then ls -1 /sys/class/net/br0/brif 2>/dev/null || true; fi
echo SECTION_DMESG_QTN
dmesg | grep -E 'OMRADIO5|OMQDRV|RAM_INSMOD|qdrv|wifi0|MuC|HLINK|EV_TLB|EV_ProtV|Oops|BUG|panic' | tail -n 220 || true
echo SECTION_STOP_FINAL
/usr/sbin/om-radio5-stop f76-stage-gate-final >/dev/null 2>&1 || true
echo OMF76_STAGE_MODULES_END
exit "$stage_rc"
'@
    $sshArgs = @(
        "-i", $RouterKey,
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=$knownHosts",
        "-o", "HostKeyAlgorithms=+ssh-rsa",
        "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa",
        "-o", "LogLevel=ERROR",
        "$RouterUser@$HostAddress",
        $remote
    )
    $proc = Start-Process -FilePath $ssh -ArgumentList $sshArgs -NoNewWindow -PassThru `
        -RedirectStandardOutput $stageOut -RedirectStandardError $stageErr
    if (-not $proc.WaitForExit($SshTimeoutSeconds * 1000)) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        return @{
            terminal_state = "F76_STAGE_MODULES_SSH_TIMEOUT"
            ssh_exit_code = 124
            stdout = $stageOut
            stderr = $stageErr
            management_tcp22_after = Test-TcpQuiet $HostAddress 22
        }
    }

    $proc.Refresh()
    $text = if (Test-Path -LiteralPath $stageOut) { Get-Content -LiteralPath $stageOut -Raw } else { "" }
    $complete = $text.Contains("OMF76_STAGE_MODULES_BEGIN") -and $text.Contains("OMF76_STAGE_MODULES_END")
    $stageRc = $null
    if ($text -match "OMF76_STAGE_MODULES_RC=([0-9]+)") { $stageRc = [int]$Matches[1] }
    $stagePass = [bool]($text -match "OMRADIO5_STAGE_STOP_PASS stage=modules")
    $controlEntered = [bool]($text -match "OMRADIO5_CONTROL_BEGIN")
    $fatal = [bool]($text -match "MuC exception|HLINK MSG timed out|EV_TLB|EV_ProtV|Oops|BUG|kernel panic|panic:")
    $wifi0InBr0 = [bool]($text -match "(?m)^wifi0$")
    $ramInsmok = @($text | Select-String -AllMatches -Pattern "RAM_INSMOD_OK" | ForEach-Object { $_.Matches.Value }).Count
    $tcp22After = Test-TcpQuiet $HostAddress 22
    $terminal = if (-not $complete) {
        "F76_STAGE_MODULES_INCOMPLETE"
    } elseif ($fatal) {
        "F76_STAGE_MODULES_FATAL_MARKER"
    } elseif ($wifi0InBr0) {
        "F76_STAGE_MODULES_WIFI0_BRIDGED"
    } elseif (-not $tcp22After) {
        "F76_STAGE_MODULES_MANAGEMENT_LOST"
    } elseif ($stagePass -and $stageRc -eq 0 -and -not $controlEntered) {
        "PASS_F76_STAGE_MODULES"
    } elseif ($controlEntered) {
        "F76_STAGE_MODULES_OVERSHOT_CONTROL_PATH"
    } else {
        "F76_STAGE_MODULES_FAIL"
    }
    return @{
        terminal_state = $terminal
        ssh_exit_code = [int]$proc.ExitCode
        transcript_complete = $complete
        stage_rc = $stageRc
        stage_pass_marker = $stagePass
        control_entered = $controlEntered
        ram_insmod_ok_count = $ramInsmok
        wifi0_in_br0 = $wifi0InBr0
        fatal_marker = $fatal
        management_tcp22_after = $tcp22After
        stdout = $stageOut
        stderr = $stageErr
    }
}

$pingOk = [bool](Test-Connection -ComputerName $HostAddress -Count 2 -Quiet -ErrorAction SilentlyContinue)
$tcp22 = Test-TcpQuiet $HostAddress 22
if (-not $pingOk -or -not $tcp22) {
    Write-JsonFile $resultPath @{
        schema = "openmitrastar.f76-stage-gate/v1"
        terminal_state = "NO_MANAGEMENT"
        ping = $pingOk
        tcp22 = $tcp22
        flash = $false
        router_mutations = $false
    }
    Get-Content -LiteralPath $resultPath -Raw
    exit 1
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "post_flash_f65_radio_gate.ps1") `
    -HostAddress $HostAddress `
    -RouterUser $RouterUser `
    -RouterKey $RouterKey `
    -OracleHost $OracleHost `
    -OracleUser $OracleUser `
    -ControllerUrl $ControllerUrl `
    -Run2gProbe `
    -Allow5gManualOff `
    -Min2gMbps $Min2gMbps `
    -OutputDir $twoGDir *> (Join-Path $OutputDir "two-g-gate.stdout.log")
$twoGRc = $LASTEXITCODE
$twoGResult = Read-JsonOrNull (Join-Path $twoGDir "result.json")
$twoGTerminal = if ($twoGResult) { [string]$twoGResult.terminal_state } else { "missing" }
if ($twoGRc -ne 0 -or $twoGTerminal -ne "PASS_TOPOLOGY_AND_2G_SPEED") {
    Write-JsonFile $resultPath @{
        schema = "openmitrastar.f76-stage-gate/v1"
        terminal_state = "FAIL_2G_BASELINE"
        two_g_exit_code = $twoGRc
        two_g_terminal_state = $twoGTerminal
        two_g_result = (Join-Path $twoGDir "result.json")
        flash = $false
        router_mutations = $false
    }
    Get-Content -LiteralPath $resultPath -Raw
    exit 1
}

$stage = Invoke-StageModules
$terminal = if ($stage.terminal_state -eq "PASS_F76_STAGE_MODULES") {
    "PASS_F76_2G_AND_5G_MODULE_STAGE"
} else {
    $stage.terminal_state
}
Write-JsonFile $resultPath @{
    schema = "openmitrastar.f76-stage-gate/v1"
    terminal_state = $terminal
    two_g_exit_code = $twoGRc
    two_g_terminal_state = $twoGTerminal
    two_g_result = (Join-Path $twoGDir "result.json")
    five_g_stage_modules = $stage
    flash = $false
    router_mutations = $true
}
Get-Content -LiteralPath $resultPath -Raw
if ($terminal -eq "PASS_F76_2G_AND_5G_MODULE_STAGE") { exit 0 }
exit 1
