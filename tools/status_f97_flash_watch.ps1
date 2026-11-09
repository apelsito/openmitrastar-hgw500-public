[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$FlashStatusPath = "",
    [string]$PostStatusPath = "",
    [int]$Tail = 40
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $FlashStatusPath) {
    $latestFlash = Get-ChildItem -LiteralPath (Join-Path $Root "outputs\flash-watch") -Directory -Filter "f97-emac-periodic-rxrestart-*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latestFlash) { $FlashStatusPath = Join-Path $latestFlash.FullName "status.json" }
}
if (-not $PostStatusPath) {
    $postRoot = Join-Path $Root "outputs\postflash"
    $latestPost = @(
        Get-ChildItem -LiteralPath $postRoot -Directory -Filter "f97-flash-then-2g-gate-*" -ErrorAction SilentlyContinue
        Get-ChildItem -LiteralPath $postRoot -Directory -Filter "f97-consoleassist-flash-then-2g-gate-*" -ErrorAction SilentlyContinue
        Get-ChildItem -LiteralPath $postRoot -Directory -Filter "f97-pulsereset-flash-then-2g-gate-*" -ErrorAction SilentlyContinue
    ) |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latestPost) { $PostStatusPath = Join-Path $latestPost.FullName "status.json" }
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

function Test-Alive($PidValue) {
    if ($null -eq $PidValue) { return $false }
    try { return $null -ne (Get-Process -Id ([int]$PidValue) -ErrorAction SilentlyContinue) }
    catch { return $false }
}

function Get-ProcessStartIso($PidValue) {
    if ($null -eq $PidValue) { return $null }
    try {
        $proc = Get-Process -Id ([int]$PidValue) -ErrorAction SilentlyContinue
        if ($null -eq $proc) { return $null }
        return $proc.StartTime.ToString("o")
    } catch { return $null }
}

function Get-ProcessAgeSeconds($PidValue) {
    if ($null -eq $PidValue) { return $null }
    try {
        $proc = Get-Process -Id ([int]$PidValue) -ErrorAction SilentlyContinue
        if ($null -eq $proc) { return $null }
        return [int]((Get-Date) - $proc.StartTime).TotalSeconds
    } catch { return $null }
}

function Count-Matches([string]$Text, [string]$Pattern) {
    if (-not $Text) { return 0 }
    return [regex]::Matches($Text, $Pattern).Count
}

$flash = Read-JsonOrNull $FlashStatusPath
$post = Read-JsonOrNull $PostStatusPath
$flashStdout = [string](Get-Prop $flash "stdout")
$postOut = [string](Get-Prop $post "output_dir")
$postResult = if ($postOut) { Join-Path $postOut "result.json" } else { $null }
$flashPid = Get-Prop $flash "pid"
$flashAlive = Test-Alive $flashPid
$logText = ""
if ($flashStdout -and (Test-Path -LiteralPath $flashStdout -PathType Leaf)) {
    try { $logText = Get-Content -LiteralPath $flashStdout -Raw -ErrorAction Stop } catch { $logText = "" }
}

$markers = [ordered]@{
    bootbase_seen = [bool]($logText -match "Bootbase|ZyNOS|ZLD|ZHAL|=>")
    topaz_ready = [bool]($logText -match "OMQ3_F45_AUTOBREAK_TOPAZ_READY=1|topaz>\s*$")
    atgu_sent = [bool]($logText -match "OMQ3_F45_AUTOBREAK_ATGU_SENT")
    flash_pass = [bool]($logText -match "MTD4_FLASH_ONE_SHOT_PASS=1|FLASH_PASS=1|_FLASH_PASS")
    linux_console_seen = [bool]($logText -match "qtn-topaz-emac|rtl8192ee:|Linux version")
    sysrq_reboot_sent = Count-Matches $logText "OMQ3_F45_AUTOBREAK_SYSRQ_REBOOT_SENT"
    console_reboot_probe_sent = Count-Matches $logText "OMQ3_F45_AUTOBREAK_CONSOLE_REBOOT_PROBE_SENT"
    blind_space_sent = Count-Matches $logText "OMQ3_F45_AUTOBREAK_BLIND_SPACE_SENT"
}

$classification = "UNKNOWN"
$nextAction = "inspect F97 status and watcher logs"
if ($postResult -and (Test-Path -LiteralPath $postResult -PathType Leaf)) {
    $classification = "POSTFLASH_RESULT_EXISTS"
    $nextAction = "inspect F97 postflash result and continue SSH/2.4 validation"
} elseif (-not $flashAlive) {
    $classification = "WATCHER_NOT_ALIVE_NO_RESULT"
    $nextAction = "inspect stderr/stdout; rearm F97 only if no flash result exists"
} elseif ($markers.flash_pass) {
    $classification = "FLASH_MARKER_SEEN_WAITING_POSTFLASH"
    $nextAction = "wait for postflash monitor or inspect latest flash-one-shot result"
} elseif ($markers.topaz_ready -or $markers.atgu_sent) {
    $classification = "BOOTBASE_CAPTURED_OR_FLASH_ACTIVE"
    $nextAction = "do not open COM3; wait for flash/readback/boot markers"
} elseif ($markers.bootbase_seen) {
    $classification = "BOOTBASE_SEEN_AUTOBREAK_IN_PROGRESS"
    $nextAction = "do not open COM3; watcher should send space/ATGU/topaz sequence"
} elseif ($markers.linux_console_seen -and $markers.sysrq_reboot_sent -gt 3 -and $markers.console_reboot_probe_sent -gt 3) {
    $classification = "WAITING_REAL_POWER_CYCLE_KERNEL_STILL_RUNNING"
    $nextAction = "physical power-cycle HGW while keeping COM3 connected; existing watcher will catch Bootbase"
} elseif ($markers.linux_console_seen) {
    $classification = "WATCHER_RUNNING_LINUX_CONSOLE_NO_BOOTBASE"
    $nextAction = "keep watcher running; if no Bootbase appears, physical power-cycle target"
} else {
    $classification = "WATCHER_RUNNING_NO_BOOTBASE_MARKERS"
    $nextAction = "keep watcher running and inspect UART cabling if no RX bytes appear"
}

$summary = [ordered]@{
    schema = "openmitrastar.f97-flash-watch-status/v1"
    flash_status_path = $FlashStatusPath
    flash_state = Get-Prop $flash "state"
    flash_pid = $flashPid
    flash_alive = $flashAlive
    flash_started_at = Get-ProcessStartIso $flashPid
    flash_age_seconds = Get-ProcessAgeSeconds $flashPid
    classification = $classification
    next_action = $nextAction
    markers = $markers
    candidate_sha256 = Get-Prop $flash "candidate_sha256"
    current_live_crc32 = Get-Prop $flash "current_live_crc32"
    post_status_path = $PostStatusPath
    post_state = Get-Prop $post "state"
    post_pid = Get-Prop $post "watcher_pid"
    post_watcher_alive = Get-Prop $post "watcher_alive"
    post_result = $postResult
    post_result_exists = [bool]($postResult -and (Test-Path -LiteralPath $postResult -PathType Leaf))
    updated_at = (Get-Date).ToString("o")
}

$summary | ConvertTo-Json -Depth 6
if ($flashStdout -and (Test-Path -LiteralPath $flashStdout -PathType Leaf)) {
    "---- flash stdout tail ----"
    Get-Content -Tail $Tail -LiteralPath $flashStdout
}
