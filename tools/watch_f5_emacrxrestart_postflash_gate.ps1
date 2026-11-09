[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RunDir = "",
    [string]$HostAddress = "192.168.1.90",
    [int]$PollSeconds = 5,
    [int]$TimeoutSeconds = 28800,
    [switch]$Run2gProbe,
    [double]$Min2gMbps = 5.0,
    [switch]$Execute
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $RunDir) {
    $latest = Get-ChildItem -LiteralPath (Join-Path $Root "outputs\flash-watch") -Directory |
        Where-Object { $_.Name -like "f5-safe2g-emacrxrestart-*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $latest) {
        throw "No f5-safe2g-emacrxrestart flash-watch directory found"
    }
    $RunDir = $latest.FullName
}

$RunDir = [IO.Path]::GetFullPath($RunDir)
$watchLog = Join-Path $RunDir "watch.log"
$watchStatus = Join-Path $RunDir "status.json"
$postState = Join-Path $RunDir "postflash-gate-state.json"
$postStdout = Join-Path $RunDir "postflash-gate.stdout.log"
$postStderr = Join-Path $RunDir "postflash-gate.stderr.log"

function Write-State([string]$State, [string]$Detail = "", [int]$ExitCode = 0) {
    [ordered]@{
        schema = "openmitrastar.f5-emacrxrestart.postflash-watch/v1"
        state = $State
        detail = $Detail
        exit_code = $ExitCode
        updated_at = (Get-Date).ToString("o")
        run_dir = $RunDir
        host = $HostAddress
        run_2g_probe = [bool]$Run2gProbe
        watch_log = $watchLog
        post_stdout = $postStdout
        post_stderr = $postStderr
    } | ConvertTo-Json -Depth 5 | Set-Content -Encoding ascii -LiteralPath $postState
}

if (-not $Execute) {
    Write-Output "OMF5_POSTFLASH_WATCH_DRY_RUN_PASS=1 run_dir=$RunDir flash=0 reboot=0 uart=0"
    exit 0
}

if (-not (Test-Path -LiteralPath $watchLog -PathType Leaf)) {
    throw "watch.log not found: $watchLog"
}

Write-State "watching" "waiting for F38 flash pass marker"
$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
while ([DateTime]::UtcNow -lt $deadline) {
    $logText = Get-Content -LiteralPath $watchLog -Raw -ErrorAction SilentlyContinue
    $statusText = ""
    if (Test-Path -LiteralPath $watchStatus -PathType Leaf) {
        $statusText = Get-Content -LiteralPath $watchStatus -Raw
    }

    if ($logText -match "OMF5_AUTONOMOUS_MTD4_FLASH_AND_READBACK_PASS=1" -or
        $statusText -match '"state"\s*:\s*"pass"') {
        Write-State "flash_pass_seen" "launching post-flash gate"
        $args = @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $PSScriptRoot "post_flash_f5_radio_gate.ps1"),
            "-HostAddress", $HostAddress,
            "-Min2gMbps", "$Min2gMbps",
            "-OutputDir", (Join-Path $Root ("outputs\postflash\f5-emacrxrestart-auto-" + (Get-Date -Format "yyyyMMdd-HHmmss")))
        )
        if ($Run2gProbe) { $args += "-Run2gProbe" }
        & pwsh.exe @args > $postStdout 2> $postStderr
        $gateRc = $LASTEXITCODE
        if ($gateRc -eq 0) {
            Write-State "postflash_gate_pass" "post-flash gate completed" 0
            Write-Output "OMF5_POSTFLASH_GATE_PASS=1 run_dir=$RunDir stdout=$postStdout"
            exit 0
        }
        Write-State "postflash_gate_fail" "post-flash gate exit=$gateRc" $gateRc
        Write-Output "OMF5_POSTFLASH_GATE_FAIL=1 run_dir=$RunDir stdout=$postStdout stderr=$postStderr"
        exit $gateRc
    }

    if ($statusText -match '"state"\s*:\s*"(timeout|failed|error)"') {
        Write-State "watcher_terminal_without_flash" "watcher status is terminal without flash pass" 1
        Write-Output "OMF5_POSTFLASH_WATCH_NO_FLASH_PASS=1 run_dir=$RunDir"
        exit 1
    }

    Start-Sleep -Seconds $PollSeconds
}

Write-State "timeout" "timed out waiting for flash pass" 1
Write-Output "OMF5_POSTFLASH_WATCH_TIMEOUT=1 run_dir=$RunDir"
exit 1
