param(
    [switch]$Execute,
    [string]$Ack = "OPENMITRASTAR_CHAIN_F70_RESTORE_TO_F73_DD4B4291",
    [string]$F70StatusPath = "/workspace/user-home\Desktop\MitraStar\outputs\postflash\f70-restore-armed-20260826-151126\f70-restore-postgate-status.json",
    [int]$F70ProcessId = 14084,
    [string]$HostAddress = "192.168.1.90",
    [string]$Port = "COM3",
    [ValidateRange(60, 21600)]
    [int]$TimeoutSeconds = 21600,
    [ValidateRange(2, 60)]
    [int]$PollSeconds = 10,
    [ValidateRange(60, 21600)]
    [int]$F73BootWaitSeconds = 900,
    [ValidateRange(600, 1800)]
    [int]$F73FlashTimeoutSeconds = 900,
    [ValidateRange(60, 21600)]
    [int]$F73PostFlashTimeoutSeconds = 1800,
    [switch]$Run2gProbe,
    [switch]$Run5gProbe,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RequiredAck = "OPENMITRASTAR_CHAIN_F70_RESTORE_TO_F73_DD4B4291"
$F73Ack = "OPENMITRASTAR_Q3_F73_QCSAPI_PATH_FIXED_MTD4_FLASH_DD4B4291"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f70-to-f73-chain-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$statusPath = Join-Path $OutputDir "chain-status.json"
$logPath = Join-Path $OutputDir "chain.log"

function Test-TcpPort([string]$HostName, [int]$TcpPort, [int]$TimeoutSeconds = 3) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $TcpPort, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne([TimeSpan]::FromSeconds($TimeoutSeconds))) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Write-ChainStatus([string]$State, [string]$Message, [int]$ExitCode = 0, [string]$F70State = "") {
    [ordered]@{
        schema = "openmitrastar.f70-to-f73-chain/v1"
        state = $State
        message = $Message
        exit_code = $ExitCode
        updated_at = (Get-Date).ToString("o")
        output_dir = $OutputDir
        f70_status_path = $F70StatusPath
        f70_process_id = $F70ProcessId
        f70_state = $F70State
        host = $HostAddress
        port = $Port
        execute = [bool]$Execute
        run_2g_probe = [bool]$Run2gProbe
        run_5g_probe = [bool]$Run5gProbe
    } | ConvertTo-Json -Depth 6 | Set-Content -Encoding ascii -LiteralPath $statusPath
}

function Add-Log([string]$Message) {
    "F70_TO_F73_CHAIN at=$(Get-Date -Format o) $Message" |
        Add-Content -Encoding ascii -LiteralPath $logPath
}

Write-ChainStatus "starting" "validating chain preflight"
Add-Log "start execute=$([bool]$Execute) f70_pid=$F70ProcessId f70_status=$F70StatusPath"

if (-not $Execute) {
    Write-Host "OMF70_TO_F73_CHAIN_READY=1"
    Write-Host "f70_status_path=$F70StatusPath"
    Write-Host "f70_process_id=$F70ProcessId"
    Write-Host "f73_ack=$F73Ack"
    Write-Host "flash=0 reason=missing_-Execute"
    Write-ChainStatus "dry_run_pass" "chain dry-run ready"
    exit 0
}
if ($Ack -ne $RequiredAck) {
    throw "Exact acknowledgement required: $RequiredAck"
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    $f70Process = Get-Process -Id $F70ProcessId -ErrorAction SilentlyContinue
    $f70State = ""
    if (Test-Path -LiteralPath $F70StatusPath -PathType Leaf) {
        try {
            $f70 = Get-Content -LiteralPath $F70StatusPath -Raw | ConvertFrom-Json
            $f70State = [string]$f70.state
        } catch {
            $f70State = "unreadable"
        }
    } else {
        $f70State = "missing-status"
    }

    if ($f70Process) {
        Write-ChainStatus "waiting_f70" "F70 restore watcher still running; not opening COM3" 0 $f70State
        Add-Log "waiting_f70 pid=$F70ProcessId f70_state=$f70State"
        Start-Sleep -Seconds $PollSeconds
        continue
    }

    $tcp22 = Test-TcpPort $HostAddress 22 3
    Add-Log "f70_process_gone f70_state=$f70State tcp22=$tcp22"
    if ($f70State -ne "pass") {
        Write-ChainStatus "blocked_f70_not_pass" "F70 watcher exited without pass; F73 not launched" 1 $f70State
        exit 1
    }
    if (-not $tcp22) {
        Write-ChainStatus "blocked_no_ssh_after_f70" "F70 status passed but TCP/22 is not reachable; F73 not launched" 1 $f70State
        exit 1
    }

    Write-ChainStatus "launching_f73" "F70 restored and SSH reachable; launching F73 via SSH reboot assist" 0 $f70State
    $f73Out = Join-Path $OutputDir "f73-postgate"
    $f73Log = Join-Path $OutputDir "f73-launch.stdout.log"
    $f73Args = @{
        Execute = $true
        Ack = $F73Ack
        Port = $Port
        HostAddress = $HostAddress
        CurrentLiveCrc32 = "9e4e61cb"
        SshRebootFirst = $true
        NoRxAbortSeconds = 0
        BootWaitSeconds = $F73BootWaitSeconds
        FlashTimeoutSeconds = $F73FlashTimeoutSeconds
        PostFlashTimeoutSeconds = $F73PostFlashTimeoutSeconds
        AllowBlindAutobreak = $true
        OutputDir = $f73Out
    }
    if ($Run2gProbe) { $f73Args.Run2gProbe = $true }
    if ($Run5gProbe) { $f73Args.Run5gProbe = $true }

    $rc = 0
    try {
        & (Join-Path $PSScriptRoot "recover_flash_f73_then_postgate.ps1") @f73Args *> $f73Log
        $rc = $LASTEXITCODE
    } catch {
        $_ | Out-String | Add-Content -Encoding ascii -LiteralPath $f73Log
        $rc = 1
    }
    Write-ChainStatus $(if ($rc -eq 0) { "pass" } else { "f73_failed" }) "F73 launcher rc=$rc" $rc $f70State
    exit $rc
}

Write-ChainStatus "timeout" "timeout waiting for F70 restore watcher to finish" 1
exit 1
