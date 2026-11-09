[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$TriggerStatusPath = "",
    [ValidateSet("F133", "F134", "F135")]
    [string]$Profile = "F133",
    [int]$TimeoutSeconds = 21600,
    [int]$PollSeconds = 10,
    [string]$HostAddress = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "$env:USERPROFILE\.ssh\id_ed25519",
    [int]$PostGateWaitSeconds = 300,
    [switch]$RunRadio5Start,
    [switch]$StopRadio5First,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f13x-rx-trigger-monitor-$($Profile.ToLowerInvariant())-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StatusOut = Join-Path $OutputDir "monitor-status.json"
$ResultOut = Join-Path $OutputDir "result.json"
$LogPath = Join-Path $OutputDir "monitor.log"

function Write-Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f13x-rx-trigger-postgate-monitor/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        trigger_status_path = $TriggerStatusPath
        profile = $Profile
        host = $HostAddress
        timeout_seconds = $TimeoutSeconds
        poll_seconds = $PollSeconds
        run_radio5_start = [bool]$RunRadio5Start
        stop_radio5_first = [bool]$StopRadio5First
        flashes = $false
        touches_uart = $false
    }
    foreach ($key in $Extra.Keys) { $payload[$key] = $Extra[$key] }
    $payload | ConvertTo-Json -Depth 10 | Set-Content -Encoding ascii -LiteralPath $StatusOut
}

function Read-JsonOrNull([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json } catch { return $null }
}

function Get-Prop($Object, [string]$Name) {
    if ($null -eq $Object) { return $null }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $null }
    return $prop.Value
}

function Test-TcpQuick([string]$HostName, [int]$PortNumber, [int]$TimeoutMs = 900) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $PortNumber, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Find-LatestTriggerStatus {
    $latest = Get-ChildItem -LiteralPath (Join-Path $Root "outputs\flash-watch") -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "^f13x-rx-trigger-$($Profile.ToLowerInvariant())-" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latest) {
        $path = Join-Path $latest.FullName "trigger-status.json"
        if (Test-Path -LiteralPath $path -PathType Leaf) { return $path }
    }
    return ""
}

if (-not $TriggerStatusPath) {
    $TriggerStatusPath = Find-LatestTriggerStatus
}
if (-not $TriggerStatusPath) {
    Write-Status "missing_trigger_status" "no F13x RX trigger status path found"
    throw "no F13x RX trigger status path found"
}
$TriggerStatusPath = [IO.Path]::GetFullPath($TriggerStatusPath)

"F13X_RX_TRIGGER_MONITOR_START at=$(Get-Date -Format o) trigger=$TriggerStatusPath profile=$Profile" |
    Add-Content -Encoding ascii -LiteralPath $LogPath
Write-Status "watching" "waiting for F13x RX-trigger flash pass"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    $trigger = Read-JsonOrNull $TriggerStatusPath
    $state = [string](Get-Prop $trigger "state")
    if (-not $state) { $state = "missing" }
    $tcp22 = Test-TcpQuick $HostAddress 22
    "F13X_RX_TRIGGER_MONITOR_POLL at=$(Get-Date -Format o) state=$state tcp22=$tcp22 trigger=$TriggerStatusPath" |
        Add-Content -Encoding ascii -LiteralPath $LogPath
    Write-Status "watching" "trigger state=$state tcp22=$tcp22" @{ trigger = $trigger; tcp22 = $tcp22 }

    if ($state -eq "flash_pass") {
        $gateDir = Join-Path $OutputDir "post-flash-radio-gate"
        Write-Status "running_post_flash_gate" "F13x flash passed; running post-flash radio gate" @{
            trigger = $trigger
            gate_dir = $gateDir
        }
        $gateArgs = @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $PSScriptRoot "post_flash_f13x_radio_gate.ps1"),
            "-Profile", $Profile,
            "-HostAddress", $HostAddress,
            "-RouterUser", $RouterUser,
            "-RouterKey", $RouterKey,
            "-WaitSeconds", "$PostGateWaitSeconds",
            "-OutputDir", $gateDir
        )
        if ($RunRadio5Start) { $gateArgs += "-RunRadio5Start" }
        if ($StopRadio5First) { $gateArgs += "-StopRadio5First" }
        $stdout = Join-Path $OutputDir "post-flash-radio-gate.stdout.log"
        $stderr = Join-Path $OutputDir "post-flash-radio-gate.stderr.log"
        & powershell.exe @gateArgs > $stdout 2> $stderr
        $gateRc = $LASTEXITCODE
        $gateStatusPath = Join-Path $gateDir "status.json"
        $gate = Read-JsonOrNull $gateStatusPath
        $gateState = [string](Get-Prop $gate "state")
        $terminal = if ($gateRc -eq 0 -and $gateState -like "PASS_*") {
            "PASS_F13X_FLASH_AND_POST_GATE"
        } elseif ($gateState) {
            "FAIL_F13X_POST_GATE_$gateState"
        } else {
            "FAIL_F13X_POST_GATE_NO_STATUS"
        }
        [ordered]@{
            schema = "openmitrastar.f13x-rx-trigger-postgate-result/v1"
            terminal_state = $terminal
            updated_at = (Get-Date).ToString("o")
            output_dir = $OutputDir
            trigger_status_path = $TriggerStatusPath
            trigger = $trigger
            post_gate = $gate
            post_gate_status_path = $gateStatusPath
            post_gate_exit_code = $gateRc
            post_gate_stdout = $stdout
            post_gate_stderr = $stderr
            flashes = $false
            touches_uart = $false
        } | ConvertTo-Json -Depth 12 | Set-Content -Encoding ascii -LiteralPath $ResultOut
        Write-Status $(if ($terminal -like "PASS_*") { "pass" } else { "post_gate_failed" }) "post-flash gate completed" @{
            terminal_state = $terminal
            result = $ResultOut
        }
        if ($terminal -like "PASS_*") { exit 0 }
        exit 1
    }

    if ($tcp22) {
        $gateDir = Join-Path $OutputDir "ssh-recovered-readonly-gate"
        Write-Status "running_ssh_recovered_readonly_gate" "router SSH recovered before trigger flash pass; running read-only baseline gate" @{
            trigger = $trigger
            gate_dir = $gateDir
        }
        $gateArgs = @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $PSScriptRoot "post_flash_f13x_radio_gate.ps1"),
            "-Profile", $Profile,
            "-HostAddress", $HostAddress,
            "-RouterUser", $RouterUser,
            "-RouterKey", $RouterKey,
            "-WaitSeconds", "0",
            "-OutputDir", $gateDir
        )
        $stdout = Join-Path $OutputDir "ssh-recovered-readonly-gate.stdout.log"
        $stderr = Join-Path $OutputDir "ssh-recovered-readonly-gate.stderr.log"
        & powershell.exe @gateArgs > $stdout 2> $stderr
        $gateRc = $LASTEXITCODE
        $gateStatusPath = Join-Path $gateDir "status.json"
        $gate = Read-JsonOrNull $gateStatusPath
        $gateState = [string](Get-Prop $gate "state")
        $terminal = if ($gateRc -eq 0 -and $gateState -eq "PASS_READ_ONLY_BASELINE") {
            "PASS_SSH_RECOVERED_READ_ONLY_BASELINE"
        } elseif ($gateState) {
            "SSH_RECOVERED_READ_ONLY_GATE_$gateState"
        } else {
            "SSH_RECOVERED_READ_ONLY_GATE_NO_STATUS"
        }
        [ordered]@{
            schema = "openmitrastar.f13x-rx-trigger-postgate-result/v1"
            terminal_state = $terminal
            updated_at = (Get-Date).ToString("o")
            output_dir = $OutputDir
            trigger_status_path = $TriggerStatusPath
            trigger = $trigger
            post_gate = $gate
            post_gate_status_path = $gateStatusPath
            post_gate_exit_code = $gateRc
            post_gate_stdout = $stdout
            post_gate_stderr = $stderr
            ssh_recovered_before_flash_pass = $true
            flashes = $false
            touches_uart = $false
        } | ConvertTo-Json -Depth 12 | Set-Content -Encoding ascii -LiteralPath $ResultOut
        Write-Status $(if ($terminal -like "PASS_*") { "pass" } else { "ssh_recovered_gate_failed" }) "SSH recovered read-only gate completed" @{
            terminal_state = $terminal
            result = $ResultOut
        }
        if ($terminal -like "PASS_*") { exit 0 }
        exit 1
    }

    if ($state -in @("flash_failed", "trigger_timeout_no_rx")) {
        [ordered]@{
            schema = "openmitrastar.f13x-rx-trigger-postgate-result/v1"
            terminal_state = "BLOCKED_BY_TRIGGER_$($state.ToUpperInvariant())"
            updated_at = (Get-Date).ToString("o")
            output_dir = $OutputDir
            trigger_status_path = $TriggerStatusPath
            trigger = $trigger
            flashes = $false
            touches_uart = $false
        } | ConvertTo-Json -Depth 12 | Set-Content -Encoding ascii -LiteralPath $ResultOut
        Write-Status "blocked_by_trigger" "trigger ended without flash pass" @{
            trigger = $trigger
            result = $ResultOut
        }
        exit 1
    }

    Start-Sleep -Seconds $PollSeconds
}

[ordered]@{
    schema = "openmitrastar.f13x-rx-trigger-postgate-result/v1"
    terminal_state = "TIMEOUT_WAITING_TRIGGER"
    updated_at = (Get-Date).ToString("o")
    output_dir = $OutputDir
    trigger_status_path = $TriggerStatusPath
    flashes = $false
    touches_uart = $false
} | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $ResultOut
Write-Status "timeout" "timeout waiting for trigger flash pass" @{ result = $ResultOut }
exit 1
