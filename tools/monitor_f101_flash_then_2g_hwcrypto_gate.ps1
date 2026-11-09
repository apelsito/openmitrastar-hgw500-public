[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$ArmStatusPath = "",
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
$BuildDir = Join-Path $Root "work\mission-state\q3-persistent-composite-f101-2g-hwcrypto-from-f100\build"
$ExpectedSha256 = "cc863436cc751680fe8cdf01f6ebcffe43fc53a8e3584ad9876de0b142cde5f1"
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f101-flash-then-2g-hwcrypto-gate-$stamp"
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
        schema = "openmitrastar.f101-flash-then-2g-hwcrypto-gate-monitor/v1"
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
    $out = Join-Path $OutputDir "ssh-hwcrypto-probe.log"
    $cmd = "echo OMF101_SSH_AUTH_PASS; uname -r; printf 'SWENC='; cat /sys/module/rtl8192ee/parameters/swenc 2>/dev/null || echo MISSING; printf 'MCS7='; cat /sys/module/rtl8192ee/parameters/hgw500_force_data_mcs7 2>/dev/null || echo MISSING; printf 'RECLAIM_POLL='; cat /sys/module/rtl_pci/parameters/hgw500_tx_reclaim_poll 2>/dev/null || echo MISSING; cat /etc/openmitrastar/release 2>/dev/null || cat /etc/openmitrastar-release 2>/dev/null || true; dmesg | grep -E 'Linux version|rtl8192ee|swenc|hgw500_force_data_mcs7|hgw500_tx_reclaim_poll|OMRTL' | tail -n 120"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "ssh_openmitrastar_510.ps1") `
        -HostAddress $HostAddress `
        -User $RouterUser `
        -KeyPath $RouterKey `
        -KnownHostsPath ".codex_tmp\f101_router_known_hosts" `
        -RemoteCommand $cmd *> $out
    $rc = $LASTEXITCODE
    $text = if (Test-Path -LiteralPath $out) { Get-Content -LiteralPath $out -Raw } else { "" }
    $sshPass = [bool]($rc -eq 0 -and $text -match "OMF101_SSH_AUTH_PASS" -and $text -match "5\.10\.260-openmitrastar-radiohw")
    $swencPass = [bool]($text -match "SWENC=N")
    $mcs7Pass = [bool]($text -match "MCS7=Y")
    $reclaimPass = [bool]($text -match "RECLAIM_POLL=Y")
    return @{
        rc = $rc
        ssh_pass = $sshPass
        swenc_disabled = $swencPass
        mcs7_enabled = $mcs7Pass
        reclaim_poll_enabled = $reclaimPass
        pass = [bool]($sshPass -and $swencPass -and $mcs7Pass -and $reclaimPass)
        log = $out
        sample = if ($text.Length -gt 3000) { $text.Substring(0, 3000) } else { $text }
    }
}

function Invoke-TwoGGate {
    $twoGDir = Join-Path $OutputDir "two-g"
    New-Item -ItemType Directory -Force -Path $twoGDir | Out-Null
    $stdout = Join-Path $OutputDir "two-g.stdout.log"
    & python (Join-Path $PSScriptRoot "run_aelita_2g_wpa2_speed_router_probe.py") `
        --router-host $HostAddress `
        --router-user $RouterUser `
        --router-key $RouterKey `
        --oracle-host $OracleHost `
        --oracle-user $OracleUser `
        --controller-url $ControllerUrl `
        --traffic-direction both `
        --output-dir $twoGDir *> $stdout
    $rc = $LASTEXITCODE
    $summary = Join-Path $twoGDir "summary.json"
    return @{
        rc = $rc
        stdout = $stdout
        summary = $summary
        summary_json = Read-JsonOrNull $summary
    }
}

"F101_FLASH_THEN_2G_HWCRYPTO_MONITOR_START at=$(Get-Date -Format o) arm=$ArmStatusPath" |
    Add-Content -Encoding ascii -LiteralPath $logPath
Write-Status "watching_flash" "waiting for F101 flash result"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    $arm = Read-JsonOrNull $ArmStatusPath
    $stdoutPath = [string](Get-Prop $arm "stdout")
    $watcherPid = Get-Prop $arm "pid"
    if ($null -eq $watcherPid) { $watcherPid = Get-Prop $arm "process_id" }
    $stdoutText = if ($stdoutPath -and (Test-Path -LiteralPath $stdoutPath -PathType Leaf)) {
        Get-Content -LiteralPath $stdoutPath -Raw
    } else {
        ""
    }
    $latest = Get-LatestFlashResult
    $watcherAlive = Test-ProcessAliveById $watcherPid
    "F101_MONITOR_POLL at=$(Get-Date -Format o) watcher_alive=$watcherAlive latest=$($latest -ne $null)" |
        Add-Content -Encoding ascii -LiteralPath $logPath

    if ($latest -and [string](Get-Prop $latest.result "status") -eq "PASS") {
        Write-Status "flash_pass_waiting_ssh" "F101 flash passed; waiting for SSH and hwcrypto proof"
        $sshDeadline = (Get-Date).AddSeconds(300)
        $sshProbe = $null
        while ((Get-Date) -lt $sshDeadline) {
            if (Test-TcpQuiet $HostAddress 22 2500) {
                $sshProbe = Invoke-RouterSshProbe
                if ($sshProbe.pass) { break }
            }
            Start-Sleep -Seconds 5
        }
        if (-not $sshProbe -or -not $sshProbe.ssh_pass) {
            Write-JsonFile $resultOut @{
                schema = "openmitrastar.f101-flash-then-2g-hwcrypto-gate-result/v1"
                terminal_state = "FAIL_F101_SSH_AUTH"
                flash_result = $latest.path
                ssh_probe = $sshProbe
            }
            Write-Status "failed_ssh_auth" "F101 flashed but SSH auth did not pass" @{ result = $resultOut }
            exit 1
        }
        if (-not $sshProbe.swenc_disabled) {
            Write-JsonFile $resultOut @{
                schema = "openmitrastar.f101-flash-then-2g-hwcrypto-gate-result/v1"
                terminal_state = "FAIL_F101_SWENC_STILL_ENABLED"
                flash_result = $latest.path
                ssh_probe = $sshProbe
            }
            Write-Status "failed_swenc" "F101 flashed but swenc is not N" @{ result = $resultOut }
            exit 1
        }

        Write-Status "running_2g_gate" "F101 SSH and hwcrypto proof passed; running AELITA 2.4 speed gate" @{
            ssh_probe = $sshProbe.log
        }
        $twoG = Invoke-TwoGGate
        $twoGPass = [bool]($twoG.rc -eq 0)
        $terminal = if ($twoGPass) { "PASS_F101_FLASH_SSH_HWCRYPTO_AND_2G_L3" } else { "FAIL_F101_2G_GATE" }
        Write-JsonFile $resultOut @{
            schema = "openmitrastar.f101-flash-then-2g-hwcrypto-gate-result/v1"
            terminal_state = $terminal
            flash_result = $latest.path
            ssh_probe = $sshProbe
            two_g = $twoG
        }
        Write-Status $(if ($twoGPass) { "pass" } else { "failed_2g" }) "F101 post-flash 2.4 hwcrypto gate completed" @{
            result = $resultOut
            terminal_state = $terminal
        }
        if ($twoGPass) { exit 0 }
        exit 1
    }

    if ($stdoutText -match "MTD4_FLASH_ONE_SHOT_FAIL|FLASH_BACKEND_TAIL_BEGIN|Exception:|UART timeout|UART_RX_SILENT_ZERO_BYTES") {
        Write-JsonFile $resultOut @{
            schema = "openmitrastar.f101-flash-then-2g-hwcrypto-gate-result/v1"
            terminal_state = "FAIL_F101_FLASH_STDOUT_MARKER"
            watcher_stdout = $stdoutPath
        }
        Write-Status "failed_flash" "F101 watcher emitted failure marker" @{ result = $resultOut }
        exit 1
    }

    if ($arm -and $watcherPid -and -not $watcherAlive -and -not $latest) {
        Write-JsonFile $resultOut @{
            schema = "openmitrastar.f101-flash-then-2g-hwcrypto-gate-result/v1"
            terminal_state = "FAIL_F101_WATCHER_EXITED_NO_RESULT"
            watcher_pid = $watcherPid
            watcher_stdout = $stdoutPath
        }
        Write-Status "failed_watcher_stale" "F101 watcher exited without flash result" @{ result = $resultOut }
        exit 1
    }

    Write-Status "watching_flash" "waiting for F101 flash result" @{
        watcher_pid = $watcherPid
        watcher_alive = $watcherAlive
        watcher_stdout = $stdoutPath
    }
    Start-Sleep -Seconds $PollSeconds
}

Write-JsonFile $resultOut @{
    schema = "openmitrastar.f101-flash-then-2g-hwcrypto-gate-result/v1"
    terminal_state = "TIMEOUT_WAITING_F101_FLASH"
    arm_status_path = $ArmStatusPath
}
Write-Status "timeout" "timeout waiting for F101 flash result" @{ result = $resultOut }
exit 1
