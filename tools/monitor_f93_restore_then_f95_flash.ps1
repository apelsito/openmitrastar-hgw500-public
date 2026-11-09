[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$F93OutputDir = "",
    [int]$TimeoutSeconds = 21600,
    [int]$PollSeconds = 10,
    [switch]$ExecuteF95,
    [switch]$Run2gGate,
    [string]$HostAddress = "192.168.1.90",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f93-restore-then-f95-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StatusPath = Join-Path $OutputDir "chain-status.json"
$LogPath = Join-Path $OutputDir "chain.log"

function Write-ChainStatus([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f93-restore-then-f95-chain/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        f93_output_dir = $F93OutputDir
        execute_f95 = [bool]$ExecuteF95
        run_2g_gate = [bool]$Run2gGate
        host = $HostAddress
        current_process_id = [int]$PID
    }
    foreach ($key in $Extra.Keys) { $payload[$key] = $Extra[$key] }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $StatusPath
}

function Add-ChainLog([string]$Message) {
    "CHAIN at=$(Get-Date -Format o) $Message" | Add-Content -Encoding ascii -LiteralPath $LogPath
}

function Resolve-F93OutputDir {
    if ($F93OutputDir) {
        $resolved = [IO.Path]::GetFullPath($F93OutputDir)
        if (-not (Test-Path -LiteralPath $resolved -PathType Container)) {
            throw "F93OutputDir not found: $resolved"
        }
        return $resolved
    }
    $latest = Get-ChildItem -LiteralPath (Join-Path $Root "outputs\flash-watch") -Directory |
        Where-Object { $_.Name -like "f93-restore-*" -or $_.Name -like "f93-2g-ht40sgi-hostapd-compat-fixedsize-after-f92-*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $latest) {
        throw "No F93 restore watcher directory found"
    }
    return $latest.FullName
}

function Get-JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutSeconds = 3) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne([TimeSpan]::FromSeconds($TimeoutSeconds))) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Start-F95Flash {
    $pwsh = (Get-Process -Id $PID).Path
    if (-not $pwsh) { $pwsh = "pwsh.exe" }
    $f95Out = Join-Path $OutputDir "f95-flash"
    $stdout = Join-Path $OutputDir "f95-flash.stdout.log"
    $stderr = Join-Path $OutputDir "f95-flash.stderr.log"
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "flash_f95_2g_mcs15_ht40sgi_descfix_fixedsize_after_f93.ps1"),
        "-Execute",
        "-Ack", "OPENMITRASTAR_Q3_F95_2G_MCS15_HT40SGI_DESCFIX_FIXEDSIZE_AFTER_F93_MTD4_FLASH",
        "-CurrentLiveCrc32", "b68554e2",
        "-SshRebootFirst",
        "-NoRxAbortSeconds", "0",
        "-AllowInfiniteNoRxWait",
        "-AllowBlindAutobreak",
        "-OutputDir", $f95Out
    )
    Add-ChainLog "launching_f95_flash output=$f95Out"
    $proc = Start-Process -FilePath $pwsh -WindowStyle Hidden -WorkingDirectory $Root `
        -ArgumentList $args -RedirectStandardOutput $stdout -RedirectStandardError $stderr -Wait -PassThru
    return @{
        output_dir = $f95Out
        stdout = $stdout
        stderr = $stderr
        exit_code = [int]$proc.ExitCode
    }
}

function Start-F93FallbackFromF95 {
    $pwsh = (Get-Process -Id $PID).Path
    if (-not $pwsh) { $pwsh = "pwsh.exe" }
    $fallbackOut = Join-Path $OutputDir "f93-fallback-after-f95"
    $stdout = Join-Path $OutputDir "f93-fallback.stdout.log"
    $stderr = Join-Path $OutputDir "f93-fallback.stderr.log"
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "flash_f93_2g_ht40sgi_hostapd_compat_fixedsize_after_f92.ps1"),
        "-Execute",
        "-Ack", "OPENMITRASTAR_Q3_F93_2G_HT40SGI_HOSTAPD_COMPAT_FIXEDSIZE_AFTER_F92_MTD4_FLASH",
        "-CurrentLiveCrc32", "418c9e28",
        "-NoRxAbortSeconds", "0",
        "-AllowInfiniteNoRxWait",
        "-AllowBlindAutobreak",
        "-OutputDir", $fallbackOut
    )
    Add-ChainLog "launching_f93_fallback_after_f95 output=$fallbackOut"
    $proc = Start-Process -FilePath $pwsh -WindowStyle Hidden -WorkingDirectory $Root `
        -ArgumentList $args -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    return @{
        pid = [int]$proc.Id
        output_dir = $fallbackOut
        stdout = $stdout
        stderr = $stderr
    }
}

function Start-2gGate {
    $pwsh = (Get-Process -Id $PID).Path
    if (-not $pwsh) { $pwsh = "pwsh.exe" }
    $gateOut = Join-Path $OutputDir "f95-2g-gate"
    $stdout = Join-Path $OutputDir "f95-2g-gate.stdout.log"
    $stderr = Join-Path $OutputDir "f95-2g-gate.stderr.log"
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "post_flash_f65_radio_gate.ps1"),
        "-HostAddress", $HostAddress,
        "-Run2gProbe",
        "-OutputDir", $gateOut,
        "-Min2gMbps", "5.0",
        "-Diag2gMbps", "20.0"
    )
    Add-ChainLog "launching_2g_gate output=$gateOut"
    $proc = Start-Process -FilePath $pwsh -WindowStyle Hidden -WorkingDirectory $Root `
        -ArgumentList $args -RedirectStandardOutput $stdout -RedirectStandardError $stderr -Wait -PassThru
    return @{
        output_dir = $gateOut
        stdout = $stdout
        stderr = $stderr
        exit_code = [int]$proc.ExitCode
    }
}

$F93OutputDir = Resolve-F93OutputDir
Add-ChainLog "start f93_output=$F93OutputDir execute_f95=$ExecuteF95 run_2g_gate=$Run2gGate"
Write-ChainStatus "watching_f93" "waiting for F93 restore watcher to pass"

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    $f93StatusPath = Join-Path $F93OutputDir "status.json"
    $f93Status = Get-JsonFile $f93StatusPath
    $state = if ($f93Status) { [string]$f93Status.state } else { "missing_status" }
    $tcp22 = Test-TcpPort $HostAddress 22 2
    Write-ChainStatus "watching_f93" "waiting for F93 restore watcher to pass" @{
        f93_state = $state
        router_tcp22 = $tcp22
    }

    if ($state -eq "pass") {
        Add-ChainLog "f93_pass_seen"
        if (-not $ExecuteF95) {
            Write-ChainStatus "f93_pass_waiting_f95_ack" "F93 restored; ExecuteF95 not set" @{ f93_state = $state }
            exit 0
        }
        Write-ChainStatus "f93_pass_launching_f95" "F93 restored; launching F95 flash"
        $f95 = Start-F95Flash
        if ($f95.exit_code -ne 0) {
            $fallback = Start-F93FallbackFromF95
            Write-ChainStatus "f95_failed_f93_fallback_armed" "F95 flash failed; F93 fallback watcher armed" @{
                f95 = $f95
                fallback = $fallback
            }
            exit 1
        }
        if ($Run2gGate) {
            $gate = Start-2gGate
            Write-ChainStatus $(if ($gate.exit_code -eq 0) { "pass" } else { "f95_pass_2g_gate_failed" }) "F95 flash complete; 2G gate finished" @{
                f95 = $f95
                gate = $gate
            }
            exit $gate.exit_code
        }
        Write-ChainStatus "pass" "F95 flash complete" @{ f95 = $f95 }
        exit 0
    }

    if ($state -match "failed|uart_rx_zero|preflight_failed|build_not_pass|ack_required") {
        Write-ChainStatus "f93_failed" "F93 restore watcher failed" @{ f93_state = $state }
        exit 1
    }

    Start-Sleep -Seconds $PollSeconds
}

Write-ChainStatus "timeout" "timeout waiting for F93 restore"
exit 1
