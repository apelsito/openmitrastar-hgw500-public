[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RunDir = "",
    [string]$RouterHost = "192.168.1.90",
    [string]$AelitaHost = "192.168.1.63",
    [string]$AelitaUser = "AELITA",
    [int]$TcpTimeoutSeconds = 3,
    [switch]$SkipAelita,
    [switch]$IncludeAelitaScan
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutSeconds = 3) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne([TimeSpan]::FromSeconds($TimeoutSeconds))
        if (-not $ok) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Invoke-JsonScript([string]$ScriptPath, [string[]]$ArgsList) {
    $raw = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @ArgsList
    if ($LASTEXITCODE -ne 0) {
        throw "$ScriptPath failed rc=$LASTEXITCODE"
    }
    return ($raw | ConvertFrom-Json)
}

$statusArgs = @("-TailLines", "40")
if ($RunDir) {
    $statusArgs += @("-RunDir", $RunDir)
}
$watcher = Invoke-JsonScript (Join-Path $PSScriptRoot "status_f65_isolated_5g_flash_watch.ps1") $statusArgs

$routerPing = [bool](Test-Connection -ComputerName $RouterHost -Count 1 -Quiet -ErrorAction SilentlyContinue)
$routerTcp22 = [bool](Test-TcpPort $RouterHost 22 $TcpTimeoutSeconds)

$aelita = [ordered]@{
    skipped = [bool]$SkipAelita
    host = $AelitaHost
    tcp22 = $null
    ssh = $null
    result = $null
    scan = $null
}
if (-not $SkipAelita) {
    $aelita.tcp22 = [bool](Test-TcpPort $AelitaHost 22 $TcpTimeoutSeconds)
    $connectOut = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "connect_aelita_auto.ps1") `
        -Mode connect `
        -HostAddress $AelitaHost `
        -User $AelitaUser `
        -WaitSeconds 1 2>&1
    $aelita.ssh = [bool]($LASTEXITCODE -eq 0 -and (($connectOut -join "`n") -match "OMAELITA_CONNECT_PASS=1"))
    $aelita.result = ($connectOut -join "`n")

    if ($IncludeAelitaScan -and $aelita.ssh) {
        $scanOut = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "connect_aelita_auto.ps1") `
            -Mode ssh `
            -HostAddress $AelitaHost `
            -User $AelitaUser `
            -RemoteCommand "netsh wlan show networks mode=bssid" 2>&1
        $aelita.scan = ($scanOut -join "`n")
    }
}

$flashPass = [bool]$watcher.markers.flash_pass
$topazReady = [bool]$watcher.markers.topaz_ready
$bootbaseSeen = [bool]$watcher.markers.bootbase_seen
$uartSilent = [bool]($watcher.diagnostics.uart_rx_state -eq "silent_zero_bytes")
$aelitaReady = [bool]($SkipAelita -or $aelita.ssh)

$decision = if ($flashPass -and $routerTcp22 -and $aelitaReady) {
    "RUN_POST_FLASH_GATE"
} elseif ($flashPass -and -not $routerTcp22) {
    "WAIT_ROUTER_SSH_AFTER_FLASH"
} elseif ($topazReady) {
    "FLASH_ATTEMPT_SHOULD_BE_IN_PROGRESS"
} elseif ($bootbaseSeen) {
    "WAIT_FOR_TOPAZ_OR_ATGU_SEQUENCE"
} elseif ($uartSilent) {
    "PHYSICAL_UART_RX_OR_RESET_WINDOW_BLOCKING_FLASH"
} else {
    "WAITING_FOR_BOOTBASE"
}

[ordered]@{
    schema = "openmitrastar.f65-ops-status/v1"
    checked_at = (Get-Date).ToString("o")
    decision = $decision
    router = [ordered]@{
        host = $RouterHost
        ping = $routerPing
        tcp22 = $routerTcp22
    }
    watcher = $watcher
    aelita = $aelita
    evidence = [ordered]@{
        no_flash_without_topaz = -not ($topazReady -or $flashPass)
        uart_rx_state = $watcher.diagnostics.uart_rx_state
        uart_rx_bytes = $watcher.diagnostics.uart_rx_bytes
        latest_uart_log = $watcher.diagnostics.latest_uart_log.path
        latest_attempt_stdout = $watcher.diagnostics.latest_attempt_stdout.path
    }
} | ConvertTo-Json -Depth 14
