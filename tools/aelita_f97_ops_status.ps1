[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$RouterHost = "192.168.1.90",
    [string]$AelitaHost = "192.168.1.63",
    [switch]$SkipNetwork,
    [int]$TcpTimeoutMs = 1200
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

function Read-JsonFile([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json } catch { return $null }
}

function Test-TcpQuiet([string]$HostAddress, [int]$Port, [int]$TimeoutMsValue) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect($HostAddress, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMsValue, $false)) { return $false }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-PingQuiet([string]$HostAddress, [int]$TimeoutMsValue) {
    $ping = [Net.NetworkInformation.Ping]::new()
    try {
        $reply = $ping.Send($HostAddress, $TimeoutMsValue)
        return ($reply.Status -eq [Net.NetworkInformation.IPStatus]::Success)
    } catch {
        return $false
    } finally {
        $ping.Dispose()
    }
}

function Invoke-F97Status {
    $raw = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "status_f97_flash_watch.ps1") -Tail 0
    if ($LASTEXITCODE -ne 0) { throw "status_f97_flash_watch.ps1 failed rc=$LASTEXITCODE" }
    $text = ($raw -join "`n")
    $marker = $text.IndexOf("---- flash stdout tail ----")
    if ($marker -ge 0) { $text = $text.Substring(0, $marker) }
    $text = $text.Trim()
    if (-not $text.StartsWith("{")) { throw "status_f97_flash_watch.ps1 did not return JSON" }
    return ($text | ConvertFrom-Json)
}

function Get-F98Readiness {
    $build = Join-Path $Root "work\mission-state\q3-persistent-composite-f98-2g-reclaim-poll-from-f97\build"
    $manifestPath = Join-Path $build "manifest.json"
    $resultPath = Join-Path $build "build-result.json"
    $manifest = Read-JsonFile $manifestPath
    $result = Read-JsonFile $resultPath
    [ordered]@{
        build_dir = $build
        manifest_exists = [bool]$manifest
        result_exists = [bool]$result
        status = if ($result -and $result.PSObject.Properties["status"]) { $result.status } else { $null }
        candidate = if ($result -and $result.PSObject.Properties["candidate"]) { $result.candidate } else { $null }
        candidate_sha256 = if ($result -and $result.PSObject.Properties["candidate_sha256"]) { $result.candidate_sha256 } else { $null }
        candidate_crc32 = if ($result -and $result.PSObject.Properties["candidate_crc32"]) { $result.candidate_crc32 } else { $null }
        bootbase_contract = if ($manifest -and $manifest.PSObject.Properties["bootbase_contract"]) { $manifest.bootbase_contract.result } else { $null }
        persistent_entry_contract = if ($manifest -and $manifest.PSObject.Properties["persistent_entry_contract"]) { $manifest.persistent_entry_contract.result } else { $null }
        flash = if ($result -and $result.PSObject.Properties["flash"]) { [bool]$result.flash } else { $null }
    }
}

$f97 = Invoke-F97Status
$routerPing = $null
$routerTcp22 = $null
$aelitaTcp22 = $null
if (-not $SkipNetwork) {
    $routerPing = Test-PingQuiet $RouterHost $TcpTimeoutMs
    $routerTcp22 = Test-TcpQuiet $RouterHost 22 $TcpTimeoutMs
    $aelitaTcp22 = Test-TcpQuiet $AelitaHost 22 $TcpTimeoutMs
}

$terminal = switch ([string]$f97.classification) {
    "POSTFLASH_RESULT_EXISTS" { "F97_POSTFLASH_RESULT_READY" }
    "FLASH_MARKER_SEEN_WAITING_POSTFLASH" { "F97_FLASH_DONE_WAITING_POSTFLASH" }
    "BOOTBASE_CAPTURED_OR_FLASH_ACTIVE" { "F97_BOOTBASE_CAPTURED_OR_FLASH_ACTIVE" }
    "BOOTBASE_SEEN_AUTOBREAK_IN_PROGRESS" { "F97_BOOTBASE_AUTOBREAK_IN_PROGRESS" }
    "WAITING_REAL_POWER_CYCLE_KERNEL_STILL_RUNNING" { "F97_WAITING_REAL_POWER_CYCLE_KERNEL_STILL_RUNNING" }
    "WATCHER_RUNNING_LINUX_CONSOLE_NO_BOOTBASE" { "F97_WATCHER_RUNNING_LINUX_CONSOLE_NO_BOOTBASE" }
    "WATCHER_NOT_ALIVE_NO_RESULT" { "F97_WATCHER_NOT_ALIVE_NO_RESULT" }
    default { "F97_STATUS_UNKNOWN" }
}

$next = switch ($terminal) {
    "F97_POSTFLASH_RESULT_READY" { "inspect F97 result; if SSH and 2.4 passed, arm F98 only for speed/reclaim validation" }
    "F97_FLASH_DONE_WAITING_POSTFLASH" { "wait for postflash monitor or inspect latest flash-one-shot result" }
    "F97_BOOTBASE_CAPTURED_OR_FLASH_ACTIVE" { "do not open COM3; wait for flash/readback/reboot markers" }
    "F97_BOOTBASE_AUTOBREAK_IN_PROGRESS" { "do not open COM3; watcher is driving Bootbase autobreak" }
    "F97_WAITING_REAL_POWER_CYCLE_KERNEL_STILL_RUNNING" { "physical power-cycle HGW while keeping COM3 connected; existing watcher should catch Bootbase" }
    "F97_WATCHER_RUNNING_LINUX_CONSOLE_NO_BOOTBASE" { "keep watcher running; physical power-cycle if Bootbase does not appear" }
    "F97_WATCHER_NOT_ALIVE_NO_RESULT" { "inspect F97 stdout/stderr; rearm only if no flash-one-shot result exists" }
    default { "inspect F97 status and logs" }
}

[ordered]@{
    schema = "openmitrastar.aelita-f97-ops-status/v1"
    checked_at = (Get-Date).ToString("o")
    terminal_state = $terminal
    next_action = $next
    router = [ordered]@{
        host = $RouterHost
        ping = $routerPing
        tcp22 = $routerTcp22
    }
    aelita_oracle = [ordered]@{
        host = $AelitaHost
        tcp22 = $aelitaTcp22
    }
    f97 = [ordered]@{
        classification = $f97.classification
        state = $f97.flash_state
        pid = $f97.flash_pid
        alive = $f97.flash_alive
        age_seconds = $f97.flash_age_seconds
        candidate_sha256 = $f97.candidate_sha256
        current_live_crc32 = $f97.current_live_crc32
        markers = $f97.markers
        post_state = $f97.post_state
        post_result = $f97.post_result
        post_result_exists = $f97.post_result_exists
    }
    f98_ready_next = Get-F98Readiness
} | ConvertTo-Json -Depth 10
