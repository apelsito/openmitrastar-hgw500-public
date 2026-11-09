[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$ArmStatusPath = "/workspace/user-home\Desktop\MitraStar\outputs\postflash\f96-armed-20260827-121935\status.json",
    [int]$TimeoutSeconds = 21600,
    [int]$PollSeconds = 10,
    [string]$HostAddress = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "$env:USERPROFILE\.ssh\id_ed25519",
    [string]$OracleHost = "192.168.1.63",
    [string]$OracleUser = "AELITA",
    [string]$ControllerUrl = "http://192.168.1.43:8008/speed.bin",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$BuildDir = Join-Path $Root "work\mission-state\q3-persistent-composite-f96-2g-mcs7-sshkey-fix-from-f84\build"
$ExpectedSha256 = "e1090769d106cddcec72a2e7e7580d76d129b0120c031e6ff8aea9c3a6cd3087"
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f96-flash-then-2g-gate-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$statusOut = Join-Path $OutputDir "status.json"
$resultOut = Join-Path $OutputDir "result.json"
$logPath = Join-Path $OutputDir "monitor.log"

function Write-JsonFile([string]$Path, [hashtable]$Payload) {
    $Payload.updated_at = (Get-Date).ToString("o")
    $Payload.output_dir = $OutputDir
    $Payload | ConvertTo-Json -Depth 10 | Set-Content -Encoding ascii -LiteralPath $Path
}

function Write-Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = @{
        schema = "openmitrastar.f96-flash-then-2g-gate-monitor/v1"
        state = $State
        message = $Message
        arm_status_path = $ArmStatusPath
        host = $HostAddress
        poll_seconds = $PollSeconds
        timeout_seconds = $TimeoutSeconds
    }
    foreach ($key in $Extra.Keys) { $payload[$key] = $Extra[$key] }
    Write-JsonFile $statusOut $payload
}

function Read-JsonOrNull([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json } catch { return $null }
}

function Get-Prop($Object, [string]$Name) {
    if ($null -eq $Object) { return $null }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $null }
    return $prop.Value
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

function Test-ProcessAliveById($ProcessId) {
    if ($null -eq $ProcessId) { return $false }
    try { return $null -ne (Get-Process -Id ([int]$ProcessId) -ErrorAction SilentlyContinue) }
    catch { return $false }
}

function Get-LatestFlashResult {
    if (-not (Test-Path -LiteralPath $BuildDir -PathType Container)) { return $null }
    $dirs = @(Get-ChildItem -LiteralPath $BuildDir -Directory -Filter "flash-one-shot-*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending)
    foreach ($dir in $dirs) {
        $resultPath = Join-Path $dir.FullName "result.json"
        $result = Read-JsonOrNull $resultPath
        if ($result -and [string](Get-Prop $result "candidate_sha256") -eq $ExpectedSha256) {
            return [pscustomobject]@{ path = $resultPath; dir = $dir.FullName; result = $result }
        }
    }
    return $null
}

function Invoke-RouterSshProbe {
    $out = Join-Path $OutputDir "ssh-probe.log"
    $cmd = "echo OMF96_SSH_AUTH_PASS; uname -r; cat /etc/openmitrastar/release 2>/dev/null || cat /etc/openmitrastar-release 2>/dev/null || true; ifconfig 2>/dev/null || ip addr 2>/dev/null || true; route -n 2>/dev/null || ip route 2>/dev/null || true; brctl show 2>/dev/null || true"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "ssh_openmitrastar_510.ps1") `
        -HostAddress $HostAddress `
        -User $RouterUser `
        -KeyPath $RouterKey `
        -KnownHostsPath ".codex_tmp\f96_router_known_hosts" `
        -RemoteCommand $cmd *> $out
    $rc = $LASTEXITCODE
    $text = if (Test-Path -LiteralPath $out) { Get-Content -LiteralPath $out -Raw } else { "" }
    return @{
        rc = $rc
        pass = [bool]($rc -eq 0 -and $text -match "OMF96_SSH_AUTH_PASS")
        log = $out
        sample = if ($text.Length -gt 3000) { $text.Substring(0, 3000) } else { $text }
    }
}

function Invoke-TwoGGate {
    $twoGDir = Join-Path $OutputDir "two-g"
    New-Item -ItemType Directory -Force -Path $twoGDir | Out-Null
    $stdout = Join-Path $OutputDir "two-g.stdout.log"
    $stderr = Join-Path $OutputDir "two-g.stderr.log"
    & python (Join-Path $PSScriptRoot "run_aelita_2g_wpa2_speed_router_probe.py") `
        --router-host $HostAddress `
        --router-user $RouterUser `
        --router-key $RouterKey `
        --oracle-host $OracleHost `
        --oracle-user $OracleUser `
        --controller-url $ControllerUrl `
        --output-dir $twoGDir *> $stdout
    $rc = $LASTEXITCODE
    $summary = Join-Path $twoGDir "summary.json"
    $summaryJson = Read-JsonOrNull $summary
    return @{
        rc = $rc
        stdout = $stdout
        stderr = $stderr
        summary = $summary
        summary_json = $summaryJson
    }
}

"F96_FLASH_THEN_2G_MONITOR_START at=$(Get-Date -Format o) arm=$ArmStatusPath" |
    Add-Content -Encoding ascii -LiteralPath $logPath
Write-Status "watching_flash" "waiting for F96 flash result"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    $arm = Read-JsonOrNull $ArmStatusPath
    $stdoutPath = [string](Get-Prop $arm "stdout")
    $watcherPid = Get-Prop $arm "process_id"
    $stdoutText = if ($stdoutPath -and (Test-Path -LiteralPath $stdoutPath -PathType Leaf)) {
        Get-Content -LiteralPath $stdoutPath -Raw
    } else {
        ""
    }
    $latest = Get-LatestFlashResult
    $watcherAlive = Test-ProcessAliveById $watcherPid
    "F96_MONITOR_POLL at=$(Get-Date -Format o) watcher_alive=$watcherAlive latest=$($latest -ne $null)" |
        Add-Content -Encoding ascii -LiteralPath $logPath

    if ($latest -and [string](Get-Prop $latest.result "status") -eq "PASS") {
        Write-Status "flash_pass_waiting_ssh" "F96 flash passed; waiting for SSH auth"
        $sshDeadline = (Get-Date).AddSeconds(240)
        $sshProbe = $null
        while ((Get-Date) -lt $sshDeadline) {
            if (Test-TcpQuiet $HostAddress 22 2500) {
                $sshProbe = Invoke-RouterSshProbe
                if ($sshProbe.pass) { break }
            }
            Start-Sleep -Seconds 5
        }
        if (-not $sshProbe -or -not $sshProbe.pass) {
            Write-JsonFile $resultOut @{
                schema = "openmitrastar.f96-flash-then-2g-gate-result/v1"
                terminal_state = "FAIL_F96_SSH_AUTH"
                flash_result = $latest.path
                ssh_probe = $sshProbe
                flash = $false
                router_mutations = $false
            }
            Write-Status "failed_ssh_auth" "F96 flashed but SSH auth did not pass" @{ result = $resultOut }
            exit 1
        }

        Write-Status "running_2g_gate" "F96 SSH auth passed; running AELITA 2.4 gate" @{
            ssh_probe = $sshProbe.log
        }
        $twoG = Invoke-TwoGGate
        $download = $null
        if ($twoG.summary_json) {
            $download = Get-Prop $twoG.summary_json "controller_download"
        }
        $twoGPass = [bool]($twoG.rc -eq 0)
        $terminal = if ($twoGPass) { "PASS_F96_FLASH_SSH_AND_2G_L3" } else { "FAIL_F96_2G_GATE" }
        Write-JsonFile $resultOut @{
            schema = "openmitrastar.f96-flash-then-2g-gate-result/v1"
            terminal_state = $terminal
            flash_result = $latest.path
            ssh_probe = $sshProbe
            two_g = $twoG
            controller_download = $download
            flash = $false
            router_mutations = $false
        }
        Write-Status $(if ($twoGPass) { "pass" } else { "failed_2g" }) "F96 post-flash 2.4 gate completed" @{
            result = $resultOut
            terminal_state = $terminal
        }
        if ($twoGPass) { exit 0 }
        exit 1
    }

    if ($stdoutText -match "MTD4_FLASH_ONE_SHOT_FAIL|FLASH_BACKEND_TAIL_BEGIN|Exception:|UART timeout|UART_RX_SILENT_ZERO_BYTES") {
        Write-JsonFile $resultOut @{
            schema = "openmitrastar.f96-flash-then-2g-gate-result/v1"
            terminal_state = "FAIL_F96_FLASH_STDOUT_MARKER"
            watcher_stdout = $stdoutPath
            flash = $false
            router_mutations = $false
        }
        Write-Status "failed_flash" "F96 watcher emitted failure marker" @{ result = $resultOut }
        exit 1
    }

    if ($arm -and $watcherPid -and -not $watcherAlive -and -not $latest) {
        Write-JsonFile $resultOut @{
            schema = "openmitrastar.f96-flash-then-2g-gate-result/v1"
            terminal_state = "FAIL_F96_WATCHER_EXITED_NO_RESULT"
            watcher_pid = $watcherPid
            watcher_stdout = $stdoutPath
            flash = $false
            router_mutations = $false
        }
        Write-Status "failed_watcher_stale" "F96 watcher exited without flash result" @{ result = $resultOut }
        exit 1
    }

    Write-Status "watching_flash" "waiting for F96 flash result" @{
        watcher_pid = $watcherPid
        watcher_alive = $watcherAlive
        watcher_stdout = $stdoutPath
    }
    Start-Sleep -Seconds $PollSeconds
}

Write-JsonFile $resultOut @{
    schema = "openmitrastar.f96-flash-then-2g-gate-result/v1"
    terminal_state = "TIMEOUT_WAITING_F96_FLASH"
    arm_status_path = $ArmStatusPath
    flash = $false
    router_mutations = $false
}
Write-Status "timeout" "timeout waiting for F96 flash result" @{ result = $resultOut }
exit 1
