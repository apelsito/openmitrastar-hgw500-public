param(
    [string]$RouterHost = "192.168.1.90",
    [string]$RecoveryHost = "192.168.1.200",
    [string]$GatewayHost = "192.168.1.1",
    [int]$F70ProcessId = 14084,
    [int]$ChainProcessId = 20192,
    [string]$F70StatusPath = "/workspace/user-home\Desktop\MitraStar\outputs\postflash\f70-restore-armed-20260826-151126\f70-restore-postgate-status.json",
    [string]$ChainStatusPath = "/workspace/user-home\Desktop\MitraStar\outputs\postflash\f70-to-f73-chain-armed-20260826-1526\chain-status.json",
    [string]$UartLogPath = "/workspace/user-home\Desktop\MitraStar\outputs\uart-live\q3-f45-radio5-powerselect-nonfatal-openlab-autostart-autoboot-atgu-flash-20260826-151127.log",
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputPath) {
    $OutputPath = Join-Path $Root "outputs\postflash\latest-f70-f73-goal-status.json"
}
New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($OutputPath)) | Out-Null

function Read-JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    } catch {
        return [ordered]@{ unreadable = $true; error = $_.Exception.Message; path = $Path }
    }
}

function Test-TcpPortFast([string]$HostName, [int]$Port, [int]$TimeoutMs = 500) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne([TimeSpan]::FromMilliseconds($TimeoutMs))) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Get-ProcState([int]$ProcId) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcId" -ErrorAction SilentlyContinue
    if (-not $proc) {
        return [ordered]@{ pid = $ProcId; running = $false; command_line = "" }
    }
    return [ordered]@{
        pid = $ProcId
        running = $true
        name = $proc.Name
        command_line = $proc.CommandLine
    }
}

$f70 = Read-JsonFile $F70StatusPath
$chain = Read-JsonFile $ChainStatusPath
$uartBytes = 0
$uartUpdated = ""
if (Test-Path -LiteralPath $UartLogPath -PathType Leaf) {
    $uartItem = Get-Item -LiteralPath $UartLogPath
    $uartBytes = [int64]$uartItem.Length
    $uartUpdated = $uartItem.LastWriteTime.ToString("o")
}

$routerTcp22 = Test-TcpPortFast $RouterHost 22
$routerPing = [bool](Test-Connection -ComputerName $RouterHost -Count 1 -Quiet -ErrorAction SilentlyContinue)
$recoveryTcp22 = Test-TcpPortFast $RecoveryHost 22
$recoveryPing = [bool](Test-Connection -ComputerName $RecoveryHost -Count 1 -Quiet -ErrorAction SilentlyContinue)
$gatewayTcp22 = Test-TcpPortFast $GatewayHost 22
$gatewayPing = [bool](Test-Connection -ComputerName $GatewayHost -Count 1 -Quiet -ErrorAction SilentlyContinue)

$f70State = if ($f70 -and $f70.state) { [string]$f70.state } else { "unknown" }
$chainState = if ($chain -and $chain.state) { [string]$chain.state } else { "unknown" }
$f70Proc = Get-ProcState $F70ProcessId
$chainProc = Get-ProcState $ChainProcessId

$decision = "UNKNOWN"
if ($routerTcp22 -and -not $f70Proc.running -and $f70State -eq "pass") {
    $decision = "F70_RESTORED_WAIT_CHAIN_OR_F73"
} elseif ($chainState -eq "launching_f73") {
    $decision = "F73_LAUNCHING"
} elseif ($chainState -eq "pass") {
    $decision = "F73_POSTGATE_PASS"
} elseif ($chainState -eq "f73_failed") {
    $decision = "F73_FAILED_INSPECT_OUTPUT"
} elseif ($f70Proc.running -and $uartBytes -eq 0 -and -not $routerTcp22) {
    $decision = "WAIT_PHYSICAL_UART_RX_OR_ROUTER_POWER_CYCLE"
} elseif ($f70Proc.running -and $uartBytes -gt 0) {
    $decision = "F70_RESTORE_UART_ACTIVE"
} elseif (-not $f70Proc.running -and $f70State -ne "pass") {
    $decision = "F70_RESTORE_NOT_PASS_INSPECT"
} elseif ($routerTcp22) {
    $decision = "ROUTER_SSH_UP_IDENTIFY_SLOT"
}

$status = [ordered]@{
    schema = "openmitrastar.f70-f73-goal-status/v1"
    checked_at = (Get-Date).ToString("o")
    decision = $decision
    router = [ordered]@{
        host = $RouterHost
        ping = $routerPing
        tcp22 = $routerTcp22
    }
    recovery_host = [ordered]@{
        host = $RecoveryHost
        ping = $recoveryPing
        tcp22 = $recoveryTcp22
    }
    gateway_non_target = [ordered]@{
        host = $GatewayHost
        ping = $gatewayPing
        tcp22 = $gatewayTcp22
    }
    f70_restore = [ordered]@{
        process = $f70Proc
        status_path = $F70StatusPath
        state = $f70State
        status = $f70
    }
    f70_to_f73_chain = [ordered]@{
        process = $chainProc
        status_path = $ChainStatusPath
        state = $chainState
        status = $chain
    }
    uart = [ordered]@{
        log_path = $UartLogPath
        bytes = $uartBytes
        last_write = $uartUpdated
        rx_seen = [bool]($uartBytes -gt 0)
    }
}

$status | ConvertTo-Json -Depth 12 | Set-Content -Encoding ascii -LiteralPath $OutputPath
$status | ConvertTo-Json -Depth 12
