param(
    [switch]$ExecuteRam,
    [switch]$KeepApOnPass,
    [string]$AckRamOnly = "",
    [string]$AckKeepRamState = "",
    [string]$HostAddress = "192.168.1.200",
    [string]$Ssid = "OpenMitraStar-Lab",
    [string]$PskFile = "",
    [string]$ClientMac = "",
    [switch]$AutoDiscoverClient,
    [int]$AssociationTimeoutSeconds = 180,
    [int]$WatchdogSeconds = 300,
    [string]$BundleDirectory = ""
)

$ErrorActionPreference = "Stop"
$AckValue = "OPENMITRASTAR_RAM_ONLY_AP_ISOLATED_GATE"
$KeepAckValue = "OPENMITRASTAR_KEEP_RAM_AP_AFTER_PASS"
$WatchdogAck = "OPENMITRASTAR_RAM_ONLY_AP_LOCAL_WATCHDOG"
$Root = Split-Path -Parent $PSScriptRoot
$FixedHost = "192.168.1.200"
$FixedWlan = "192.168.2.1"
$FixedClient = "192.168.2.2"
$RemoteRoot = "/tmp/openmitrastar-ap/bundle"
$RemoteState = "/tmp/openmitrastar-ap"
$RemoteWatchdog = "/tmp/openmitrastar-ap-isolated-watchdog.sh"
$RemoteWatchdogState = "/tmp/openmitrastar-ap-isolated-watchdog"
$UploadTool = Join-Path $PSScriptRoot "ramssh_upload.py"
$ExecTool = Join-Path $PSScriptRoot "ramssh_exec.py"
$WatchdogSource = Join-Path $PSScriptRoot "openmitrastar_ap_isolated_watchdog.sh"

if (-not $BundleDirectory) {
    $BundleDirectory = Join-Path $Root "outputs\kernel-port\realtek-ap-bundle"
}
$BundleDirectory = [IO.Path]::GetFullPath($BundleDirectory)
$ManifestPath = Join-Path $BundleDirectory "manifest.json"
$HashPath = Join-Path $BundleDirectory "SHA256SUMS.target"

if ($HostAddress -ne $FixedHost) { throw "Isolated gate requires exact RAM management host $FixedHost" }
if ($Ssid -notmatch '^[A-Za-z0-9_.-]{1,32}$') { throw "Invalid SSID" }
if ($AssociationTimeoutSeconds -lt 30 -or $AssociationTimeoutSeconds -gt 900) {
    throw "AssociationTimeoutSeconds must be 30..900"
}
if ($WatchdogSeconds -lt ($AssociationTimeoutSeconds + 60) -or $WatchdogSeconds -gt 1800) {
    throw "WatchdogSeconds must be at least AssociationTimeoutSeconds+60 and no more than 1800"
}
foreach ($required in @($ManifestPath, $HashPath, $WatchdogSource, $UploadTool, $ExecTool)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required artifact: $required" }
}
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
if ($Manifest.classification -ne "RAM-ONLY-NO-FLASH" -or
    [bool]$Manifest.candidate_eligible -or
    [bool]$Manifest.flash_supported -or
    [bool]$Manifest.persistent_writes_supported) {
    throw "AP bundle is not RAM-only/fail-closed"
}
$isolated = $Manifest.topology.modes.isolated
if ($isolated.eth0_ipv4_preserved -ne "$FixedHost/24" -or
    $isolated.wlan0_ipv4 -ne "$FixedWlan/24" -or
    $isolated.client_ipv4 -ne "$FixedClient/24" -or
    $null -ne $isolated.bridge) {
    throw "Bundle isolated topology does not match the fixed gate contract"
}

$Plan = [ordered]@{
    schema = "openmitrastar.ap-isolated-gate/v1"
    mode = if ($ExecuteRam) { "EXECUTE_RAM" } else { "DRY_RUN" }
    classification = "RAM-ONLY-NO-FLASH"
    band = "2.4GHz-ONLY"
    topology = "isolated"
    bridge_allowed = $false
    eth0 = "$FixedHost/24 (preserved)"
    wlan0 = "$FixedWlan/24"
    client = "$FixedClient/24 (static)"
    client_selection = if ($AutoDiscoverClient) { "auto-discover-single-authorized" } else { "explicit-mac" }
    hostapd_gate = "state=ENABLED"
    association_gate = "flags=[AUTHORIZED]"
    ping_gate = "router-to-client 3/3"
    watchdog = [ordered]@{
        scope = "router-local"
        timeout_seconds = $WatchdogSeconds
        rollback_transport = "none"
        rollback_target = "eth0=$FixedHost,wlan0=down,hostapd=stopped"
    }
    keep_ap_on_pass = [bool]$KeepApOnPass
    flash_supported = $false
    persistent_writes_supported = $false
    five_ghz_touched = $false
}

if (-not $ExecuteRam) {
    $Plan | ConvertTo-Json -Depth 6
    Write-Output "OMAP_ISOLATED_DRY_RUN_PASS=1"
    exit 0
}

if ($AckRamOnly -ne $AckValue) { throw "Execution requires exact -AckRamOnly $AckValue" }
if ($KeepApOnPass -and $AckKeepRamState -ne $KeepAckValue) {
    throw "Keeping the AP active requires exact -AckKeepRamState $KeepAckValue"
}
if (-not $PskFile -or -not (Test-Path -LiteralPath $PskFile -PathType Leaf)) {
    throw "-PskFile must name a local file; its contents are never logged"
}
if ($AutoDiscoverClient -and $ClientMac) {
    throw "Use either -ClientMac or -AutoDiscoverClient, never both"
}
if (-not $AutoDiscoverClient -and $ClientMac -notmatch '^(?i:[0-9a-f]{2}:){5}[0-9a-f]{2}$') {
    throw "Explicit mode requires -ClientMac as a six-octet MAC address"
}
$ResolvedClientMac = if ($AutoDiscoverClient) { "" } else { $ClientMac.ToLowerInvariant() }

function Invoke-Remote([string]$Command, [string]$Label, [int]$Timeout = 30) {
    $saved = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & python $ExecTool $Command --host $FixedHost --timeout $Timeout 2>&1
        $rc = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $saved
    }
    if ($rc -ne 0) { throw "$Label failed (exit $rc): $($output -join ' ')" }
    return @($output)
}

function Upload-FileQuiet([string]$Source, [string]$Destination, [string]$Mode) {
    $saved = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & python $UploadTool $Source $Destination --host $FixedHost --mode $Mode *> $null
        $rc = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $saved
    }
    if ($rc -ne 0) { throw "Sequential upload failed (exit $rc): $Destination" }
}

function New-WatchdogToken {
    $bytes = New-Object byte[] 16
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return (($bytes | ForEach-Object { $_.ToString("x2") }) -join '')
}

function Invoke-Watchdog([string]$Mode, [string]$Token, [int]$Timeout = 30) {
    $command = "$RemoteWatchdog --$Mode --timeout $WatchdogSeconds --token $Token --ack $WatchdogAck"
    return Invoke-Remote $command "watchdog-$Mode" $Timeout
}

function Get-HostapdStationSnapshot([object[]]$Lines) {
    $stations = [ordered]@{}
    $current = $null
    foreach ($rawLine in @($Lines)) {
        $line = ([string]$rawLine).Trim()
        if ($line -match '^(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$') {
            $current = $line.ToLowerInvariant()
            if (-not $stations.Contains($current)) { $stations[$current] = $false }
            continue
        }
        if ($current -and $line -match '^flags=.*\[AUTHORIZED\]') {
            $stations[$current] = $true
        }
    }
    $all = @($stations.Keys)
    $authorized = @($stations.GetEnumerator() | Where-Object { [bool]$_.Value } | ForEach-Object { [string]$_.Key })
    return [pscustomobject]@{
        All = $all
        Authorized = $authorized
    }
}

$Evidence = Join-Path $Root ("outputs\kernel-port\realtek-ap-runtime\isolated-gate-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Force -Path $Evidence | Out-Null
$Transcript = Join-Path $Evidence "orchestrator.log"
$Token = New-WatchdogToken
$WatchdogArmed = $false
$Passed = $false

try {
    $preflight = "test ! -e /sys/class/net/br0; ! pidof hostapd >/dev/null 2>&1; if ifconfig wlan0 2>/dev/null | grep -q '192.168.2.1'; then exit 42; fi; rm -rf $RemoteState; mkdir -p $RemoteRoot/bin $RemoteRoot/firmware $RemoteRoot/runtime $RemoteRoot/provenance"
    Invoke-Remote $preflight "isolated-preflight-and-staging" | Out-File $Transcript

    $entries = foreach ($line in Get-Content -LiteralPath $HashPath) {
        if ($line -notmatch '^([0-9a-f]{64})\s+(.+)$') { throw "Malformed target hash line" }
        [pscustomobject]@{ Hash = $Matches[1]; Relative = $Matches[2] }
    }
    foreach ($entry in $entries) {
        if ($entry.Relative -eq "bin/busybox") { continue }
        $source = Join-Path $BundleDirectory ($entry.Relative.Replace('/', '\'))
        $destination = "$RemoteRoot/$($entry.Relative)"
        $parent = $destination.Substring(0, $destination.LastIndexOf('/'))
        Invoke-Remote "mkdir -p $parent" "mkdir-$($entry.Relative)" | Out-Null
        $mode = if ($entry.Relative.StartsWith("bin/") -or $entry.Relative.StartsWith("runtime/")) { "0700" } else { "0600" }
        Upload-FileQuiet $source $destination $mode
    }
    Upload-FileQuiet $HashPath "$RemoteRoot/SHA256SUMS.target" "0600"
    Upload-FileQuiet $ManifestPath "$RemoteRoot/manifest.json" "0600"
    Upload-FileQuiet $WatchdogSource $RemoteWatchdog "0700"
    Invoke-Remote "cd $RemoteRoot/bin && rm -f busybox && ln -s ap_tools busybox; cd $RemoteRoot && ./bin/busybox sha256sum -c SHA256SUMS.target" "remote-hash-gate" 40 | Out-File $Transcript -Append

    # Secret-bearing uploader output is intentionally discarded.
    Upload-FileQuiet ([IO.Path]::GetFullPath($PskFile)) "$RemoteState/secret.psk" "0600"

    $watchdogLaunch = "$RemoteRoot/bin/detach_exec $RemoteState/watchdog.launch.log $RemoteWatchdog --arm --timeout $WatchdogSeconds --token $Token --ack $WatchdogAck"
    Invoke-Remote $watchdogLaunch "watchdog-arm-launch" 20 | Out-File $Transcript -Append
    $WatchdogArmed = $true
    Start-Sleep -Seconds 1
    $armed = Invoke-Remote "cat $RemoteWatchdogState/watchdog.log; test -r $RemoteWatchdogState/token" "watchdog-arm-readback" 20
    $armed | Out-File $Transcript -Append
    if (($armed -join "`n") -notmatch 'OMAP_WATCHDOG_ARMED') { throw "Router-local watchdog did not arm" }

    $launch = "$RemoteRoot/bin/detach_exec $RemoteState/ap-start.log $RemoteRoot/runtime/ap-start.sh --apply --topology isolated --ssid $Ssid --psk-file $RemoteState/secret.psk --expected-kernel $($Manifest.expected_kernel_release) --control-plane uart --ack OPENMITRASTAR_RAM_ONLY_24GHZ_AP"
    Invoke-Remote $launch "isolated-ap-launch" 20 | Out-File $Transcript -Append

    $deadline = (Get-Date).AddSeconds($AssociationTimeoutSeconds)
    $enabled = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $status = Invoke-Remote "$RemoteRoot/bin/hostapd_cli -p $RemoteState/ctrl -i wlan0 status" "hostapd-enabled-probe" 15
            $status | Out-File $Transcript -Append
            if (($status -join "`n") -match '(?m)^state=ENABLED$') { $enabled = $true; break }
        } catch {
            $_.Exception.Message | Out-File $Transcript -Append
        }
        Start-Sleep -Seconds 2
    }
    if (-not $enabled) { throw "hostapd did not reach ENABLED before timeout" }

    $authorized = $false
    while ((Get-Date) -lt $deadline) {
        $probe = $null
        try {
            if ($AutoDiscoverClient) {
                $probe = Invoke-Remote "$RemoteRoot/bin/hostapd_cli -p $RemoteState/ctrl -i wlan0 all_sta" "station-discovery" 15
            } else {
                $probe = Invoke-Remote "$RemoteRoot/bin/hostapd_cli -p $RemoteState/ctrl -i wlan0 sta $ResolvedClientMac" "station-probe" 15
            }
        } catch {
            $_.Exception.Message | Out-File $Transcript -Append
        }
        if ($probe) {
            $probe | Out-File $Transcript -Append
            if ($AutoDiscoverClient) {
                $snapshot = Get-HostapdStationSnapshot $probe
                if ($snapshot.All.Count -gt 1) {
                    throw "Auto-discovery refused multiple stations: $($snapshot.All -join ',')"
                }
                if ($snapshot.Authorized.Count -eq 1) {
                    $candidate = [string]$snapshot.Authorized[0]
                    if ($candidate -notmatch '^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$') {
                        throw "Auto-discovery returned an invalid station MAC"
                    }
                    $ResolvedClientMac = $candidate
                    $authorized = $true
                    break
                }
            } elseif (($probe -join "`n") -match '(?m)^flags=.*\[AUTHORIZED\]') {
                $authorized = $true
                break
            }
        }
        Start-Sleep -Seconds 2
    }
    if (-not $authorized) { throw "Client did not reach AUTHORIZED before timeout" }

    $smokeCommand = "$RemoteRoot/runtime/ap-smoke.sh --client-mac $ResolvedClientMac --client-ip $FixedClient --ack OPENMITRASTAR_RAM_ONLY_AP_SMOKE"
    $smoke = Invoke-Remote $smokeCommand "isolated-client-smoke" 40
    $smoke | Out-File $Transcript -Append

    if ($AutoDiscoverClient) {
        $finalStations = Invoke-Remote "$RemoteRoot/bin/hostapd_cli -p $RemoteState/ctrl -i wlan0 all_sta" "station-final-uniqueness" 20
        $finalStations | Out-File $Transcript -Append
        $finalSnapshot = Get-HostapdStationSnapshot $finalStations
        if ($finalSnapshot.All.Count -ne 1 -or
            $finalSnapshot.Authorized.Count -ne 1 -or
            $finalSnapshot.Authorized[0] -ne $ResolvedClientMac) {
            throw "Auto-discovered station set changed before final readback"
        }
    }

    $readback = "echo ===AP_LOG===; $RemoteRoot/bin/busybox tail -n 160 $RemoteState/ap-start.log; echo ===HOSTAPD===; $RemoteRoot/bin/hostapd_cli -p $RemoteState/ctrl -i wlan0 status; echo ===STATION===; $RemoteRoot/bin/hostapd_cli -p $RemoteState/ctrl -i wlan0 sta $ResolvedClientMac; echo ===IW===; $RemoteRoot/bin/iw dev wlan0 info; echo ===ETH0===; $RemoteRoot/bin/busybox ifconfig eth0; echo ===WLAN0===; $RemoteRoot/bin/busybox ifconfig wlan0; echo ===TOPOLOGY===; if test -e /sys/class/net/br0; then echo OMAP_BRIDGE_ABSENT=0; else echo OMAP_BRIDGE_ABSENT=1; fi; cat $RemoteState/runtime.env"
    $state = Invoke-Remote $readback "isolated-readback" 40
    $state | Out-File $Transcript -Append
    $text = (($smoke + $state) -join "`n")
    foreach ($requiredPattern in @(
        'state=ENABLED',
        '(?m)^flags=.*\[AUTHORIZED\]',
        'OMAP_SMOKE_PASS topology=isolated.*ping=3/3',
        'OMAP_BRIDGE_ABSENT=1',
        'inet (addr:)?192\.168\.1\.200',
        'inet (addr:)?192\.168\.2\.1',
        'type AP',
        'channel 1 \(2412 MHz\).*width: 20 MHz'
    )) {
        if ($text -notmatch $requiredPattern) { throw "Missing isolated PASS marker: $requiredPattern" }
    }
    "client_mac=$ResolvedClientMac selection=$(if ($AutoDiscoverClient) { 'auto' } else { 'explicit' })" | Out-File $Transcript -Append
    $Passed = $true

    if ($KeepApOnPass) {
        Invoke-Watchdog "disarm" $Token 20 | Out-File $Transcript -Append
        $WatchdogArmed = $false
        Write-Output "OMAP_ISOLATED_GATE_PASS keep_ap=1 evidence=$Evidence"
    } else {
        Invoke-Watchdog "trigger" $Token 40 | Out-File $Transcript -Append
        $WatchdogArmed = $false
        $rollback = Invoke-Remote "cat $RemoteWatchdogState/watchdog.log; test ! -e /sys/class/net/br0; $RemoteRoot/bin/busybox ifconfig eth0" "rollback-readback" 30
        $rollback | Out-File $Transcript -Append
        $rollbackText = $rollback -join "`n"
        if ($rollbackText -notmatch 'OMAP_WATCHDOG_ROLLBACK_PASS' -or
            $rollbackText -notmatch 'inet (addr:)?192\.168\.1\.200') {
            throw "Router-local rollback readback failed"
        }
        Write-Output "OMAP_ISOLATED_GATE_PASS keep_ap=0 rollback=PASS evidence=$Evidence"
    }
} catch {
    "failure=$($_.Exception.Message) watchdog_armed=$WatchdogArmed watchdog_timeout_s=$WatchdogSeconds" | Out-File $Transcript -Append
    if ($WatchdogArmed) {
        try { Invoke-Watchdog "trigger" $Token 20 | Out-File $Transcript -Append } catch { $_.Exception.Message | Out-File $Transcript -Append }
    }
    throw
} finally {
    if ($Passed) {
        "result=PASS keep_ap=$([bool]$KeepApOnPass)" | Out-File $Transcript -Append
    }
}
