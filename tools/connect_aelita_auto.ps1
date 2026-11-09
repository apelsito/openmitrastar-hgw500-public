[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("all", "connect", "preflight", "ssh", "2g", "5g")]
    [string]$Mode = "all",
    [string]$HostAddress = "192.168.1.63",
    [string]$User = "AELITA",
    [string]$KeyPath = "outputs\kernel-port\realtek-loop\wifi-oracle-control\oracle_rsa_unencrypted",
    [string]$KnownHostsPath = "outputs\kernel-port\realtek-loop\wifi-oracle-control\known_hosts",
    [string]$OutputDirectory = "outputs\recovery\aelita-connect-auto",
    [string]$RouterHost = "192.168.1.90",
    [string]$ControllerIp = "192.168.1.43",
    [string]$WifiInterface = "Wi-Fi",
    [int]$WaitSeconds = 0,
    [int]$RetrySeconds = 3,
    [switch]$UpdateGlobalKnownHosts,
    [switch]$OpenShell,
    [switch]$Execute,
    [switch]$WaitResult,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemoteCommand = @()
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runDir = [IO.Path]::GetFullPath((Join-Path $Root (Join-Path $OutputDirectory $stamp)))
$key = [IO.Path]::GetFullPath((Join-Path $Root $KeyPath))
$knownHosts = [IO.Path]::GetFullPath((Join-Path $Root $KnownHostsPath))
$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$sshKeygen = Join-Path $env:WINDIR "System32\OpenSSH\ssh-keygen.exe"
$sshKeyscan = Join-Path $env:WINDIR "System32\OpenSSH\ssh-keyscan.exe"
$globalKnownHosts = Join-Path $env:USERPROFILE ".ssh\known_hosts"

function Write-Step([string]$Name, [string]$Detail = "") {
    if ($Detail) {
        Write-Host "OMAELITA_STEP $Name $Detail"
    } else {
        Write-Host "OMAELITA_STEP $Name"
    }
}

function Refresh-KnownHosts {
    New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($knownHosts)) | Out-Null
    if (Test-Path -LiteralPath $knownHosts) {
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & $sshKeygen -R $HostAddress -f $knownHosts *> $null
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $scanOutput = & $sshKeyscan -T 5 -t rsa,ed25519 $HostAddress 2>$null
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $scan = @($scanOutput | Where-Object {
        $_ -and
        -not $_.StartsWith("#") -and
        $_ -match '^\S+\s+(ssh-ed25519|ssh-rsa)\s+'
    })
    if ($scan) {
        Add-Content -LiteralPath $knownHosts -Value $scan -Encoding ascii
        Write-Host "OMAELITA_HOSTKEY_REFRESH_OK host=$HostAddress file=$knownHosts entries=$($scan.Count)"
        if ($UpdateGlobalKnownHosts) {
            New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($globalKnownHosts)) | Out-Null
            if (Test-Path -LiteralPath $globalKnownHosts) {
                & $sshKeygen -R $HostAddress -f $globalKnownHosts *> $null
            }
            Add-Content -LiteralPath $globalKnownHosts -Value $scan -Encoding ascii
            Write-Host "OMAELITA_GLOBAL_HOSTKEY_REFRESH_OK host=$HostAddress file=$globalKnownHosts entries=$($scan.Count)"
        }
    } else {
        Write-Host "OMAELITA_HOSTKEY_REFRESH_SKIPPED host=$HostAddress reason=ssh-keyscan-empty"
    }
}

function Test-AelitaTcp {
    $tcp = Test-NetConnection -ComputerName $HostAddress -Port 22 -InformationLevel Quiet -WarningAction SilentlyContinue
    if ($tcp) {
        Write-Host "OMAELITA_TCP_OK host=$HostAddress port=22"
    } else {
        Write-Host "OMAELITA_TCP_FAIL host=$HostAddress port=22"
    }
    return [bool]$tcp
}

function Wait-AelitaTcp([int]$TimeoutSeconds, [int]$SleepSeconds) {
    if ($TimeoutSeconds -le 0) {
        return (Test-AelitaTcp)
    }
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $attempt = 0
    while ((Get-Date) -lt $deadline) {
        $attempt += 1
        Write-Host "OMAELITA_WAIT_ATTEMPT attempt=$attempt host=$HostAddress port=22 remaining=$([int]($deadline - (Get-Date)).TotalSeconds)"
        if (Test-AelitaTcp) {
            Write-Host "OMAELITA_WAIT_OK host=$HostAddress attempts=$attempt"
            return $true
        }
        Start-Sleep -Seconds ([Math]::Max(1, $SleepSeconds))
    }
    Write-Host "OMAELITA_WAIT_TIMEOUT host=$HostAddress seconds=$TimeoutSeconds"
    return $false
}

function Invoke-AelitaSsh([string]$Command = "") {
    if (-not (Test-Path -LiteralPath $key)) {
        throw "Missing AELITA key: $key"
    }
    $args = @(
        "-i", $key,
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=$knownHosts",
        "-o", "LogLevel=ERROR",
        "$User@$HostAddress"
    )
    if ($Command) { $args += $Command }
    & $ssh @args
    $script:LastSshExitCode = $LASTEXITCODE
}

function Invoke-AelitaSshProbe {
    $probe = @'
$ProgressPreference = "SilentlyContinue"
$ErrorActionPreference = "Stop"
[ordered]@{
  schema = "openmitrastar.aelita-ssh-probe/v1"
  computer = $env:COMPUTERNAME
  user = $env:USERNAME
  now = (Get-Date).ToString("o")
  ssh = "ok"
} | ConvertTo-Json -Depth 3
'@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($probe))
    Invoke-AelitaSsh "powershell.exe -NoProfile -NonInteractive -OutputFormat Text -EncodedCommand $encoded"
}

function Invoke-AelitaPreflight {
    $remote = @'
$ProgressPreference = "SilentlyContinue"
$ErrorActionPreference = "Continue"
$svc = Get-Service -Name WlanSvc -ErrorAction SilentlyContinue
$adapters = Get-NetAdapter -ErrorAction SilentlyContinue |
  Where-Object { $_.InterfaceDescription -match "Wireless|Wi-Fi|802\.11|Intel.*Wi|Realtek.*Wi" -or $_.Name -match "Wi-Fi|Wireless" } |
  Select-Object Name, Status, InterfaceDescription, LinkSpeed
$current = (& "$env:WINDIR\System32\netsh.exe" wlan show interfaces 2>&1 | Out-String).Trim()
[ordered]@{
  schema = "openmitrastar.aelita-preflight/v1"
  computer = $env:COMPUTERNAME
  user = $env:USERNAME
  wlan_service = if ($svc) { $svc.Status.ToString() } else { "missing" }
  wifi_adapters = $adapters
  netsh_interfaces = $current
} | ConvertTo-Json -Depth 6
'@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($remote))
    Invoke-AelitaSsh "powershell.exe -NoProfile -NonInteractive -OutputFormat Text -EncodedCommand $encoded"
}

if ($HostAddress -ne "192.168.1.63" -or $User -ne "AELITA") {
    throw "This wrapper is pinned to AELITA@192.168.1.63 unless edited deliberately."
}

New-Item -ItemType Directory -Force -Path $runDir | Out-Null
Refresh-KnownHosts

switch ($Mode) {
    "connect" {
        Write-Step "connect" "host=$HostAddress user=$User wait=$WaitSeconds out=$runDir"
        $tcpOk = Wait-AelitaTcp $WaitSeconds $RetrySeconds
        if (-not $tcpOk) {
            [ordered]@{
                schema = "openmitrastar.aelita-connect/v1"
                host = $HostAddress
                user = $User
                mode = $Mode
                tcp22 = "fail"
                ssh = "not-run"
                run_dir = $runDir
                created_at = (Get-Date).ToString("o")
            } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDir "result.json") -Encoding ascii
            exit 20
        }

        Refresh-KnownHosts

        Write-Step "ssh-probe" "host=$HostAddress user=$User"
        $probeOutput = Invoke-AelitaSshProbe 2>&1
        $probeRc = $script:LastSshExitCode
        $probeOutput | Set-Content -LiteralPath (Join-Path $runDir "ssh-probe.log") -Encoding utf8
        Write-Host $probeOutput
        Write-Host "OMAELITA_SSH_PROBE_RC=$probeRc"
        if ($probeRc -ne 0) {
            [ordered]@{
                schema = "openmitrastar.aelita-connect/v1"
                host = $HostAddress
                user = $User
                mode = $Mode
                tcp22 = "ok"
                ssh = "fail"
                ssh_rc = $probeRc
                run_dir = $runDir
                created_at = (Get-Date).ToString("o")
            } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDir "result.json") -Encoding ascii
            exit $probeRc
        }

        Write-Step "preflight" "host=$HostAddress user=$User"
        $preflightOutput = Invoke-AelitaPreflight 2>&1
        $preflightRc = $script:LastSshExitCode
        $preflightOutput | Set-Content -LiteralPath (Join-Path $runDir "preflight.json") -Encoding utf8
        Write-Host $preflightOutput
        Write-Host "OMAELITA_PREFLIGHT_RC=$preflightRc"

        [ordered]@{
            schema = "openmitrastar.aelita-connect/v1"
            host = $HostAddress
            user = $User
            mode = $Mode
            tcp22 = "ok"
            ssh = "ok"
            ssh_rc = $probeRc
            preflight_rc = $preflightRc
            key = $key
            known_hosts = $knownHosts
            run_dir = $runDir
            created_at = (Get-Date).ToString("o")
        } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runDir "result.json") -Encoding ascii

        if ($preflightRc -ne 0) { exit $preflightRc }

        if ($OpenShell -or $RemoteCommand.Count -gt 0) {
            $cmd = if ($RemoteCommand.Count -gt 0) { $RemoteCommand -join " " } else { "" }
            Write-Step "ssh" "host=$HostAddress user=$User shell=$([int]$OpenShell.IsPresent)"
            Invoke-AelitaSsh $cmd
            exit $script:LastSshExitCode
        }

        Write-Host "OMAELITA_CONNECT_PASS=1 result=$(Join-Path $runDir "result.json")"
        exit 0
    }
    "all" {
        Write-Step "all" "host=$HostAddress user=$User router=$RouterHost controller=$ControllerIp"
        $tcpOk = Wait-AelitaTcp $WaitSeconds $RetrySeconds
        if (-not $tcpOk) { exit 20 }

        Write-Step "ssh-probe" "host=$HostAddress user=$User"
        Invoke-AelitaSshProbe
        if ($script:LastSshExitCode -ne 0) { exit $script:LastSshExitCode }

        Write-Step "preflight" "host=$HostAddress user=$User"
        Invoke-AelitaPreflight
        $preflightRc = $script:LastSshExitCode
        Write-Host "OMAELITA_PREFLIGHT_RC=$preflightRc"
        if ($preflightRc -ne 0) { exit $preflightRc }

        Write-Step "2g-oracle-dry-run" "router=$RouterHost"
        & python (Join-Path $PSScriptRoot "run_aelita_2g_wpa2_runtime_psk_once.py") `
            --router-host $RouterHost `
            --oracle-host $HostAddress `
            --oracle-user $User `
            --test-ssid "OpenMitraStar-Lab" `
            --wifi-interface $WifiInterface
        $twoGRc = $LASTEXITCODE
        Write-Host "OMAELITA_2G_DRY_RUN_RC=$twoGRc"
        if ($twoGRc -ne 0) { exit $twoGRc }

        Write-Step "5g-oracle-dry-run" "router=$RouterHost controller=$ControllerIp"
        & python (Join-Path $PSScriptRoot "run_qtn_5g_aelita_one_shot.py") `
            --router-host $RouterHost `
            --oracle-host $HostAddress `
            --oracle-user $User `
            --controller-ip $ControllerIp `
            --restore-ssid "MOVISTAR-WIFI6-A348" `
            --seconds "120" `
            --v6-scheduler-diag
        $fiveGRc = $LASTEXITCODE
        Write-Host "OMAELITA_5G_DRY_RUN_RC=$fiveGRc"
        exit $fiveGRc
    }
    "preflight" {
        Write-Step "preflight" "host=$HostAddress user=$User"
        Invoke-AelitaPreflight
        exit $script:LastSshExitCode
    }
    "ssh" {
        $cmd = if ($RemoteCommand.Count -gt 0) { $RemoteCommand -join " " } else { "" }
        Write-Step "ssh" "host=$HostAddress user=$User"
        Invoke-AelitaSsh $cmd
        exit $script:LastSshExitCode
    }
    "2g" {
        Write-Step "2g-oracle" "router=$RouterHost execute=$([int]$Execute.IsPresent) wait=$([int]$WaitResult.IsPresent)"
        $args = @(
            (Join-Path $PSScriptRoot "run_aelita_2g_wpa2_runtime_psk_once.py"),
            "--router-host", $RouterHost,
            "--oracle-host", $HostAddress,
            "--oracle-user", $User,
            "--test-ssid", "OpenMitraStar-Lab",
            "--wifi-interface", $WifiInterface
        )
        if ($Execute) {
            $args += @("--execute", "--ack", "OPENMITRASTAR_AELITA_2G_WPA2_RUNTIME_PSK")
        }
        if ($WaitResult) {
            $args += @("--wait-result", "240")
        }
        & python @args
        exit $LASTEXITCODE
    }
    "5g" {
        Write-Step "5g-oracle" "router=$RouterHost controller=$ControllerIp execute=$([int]$Execute.IsPresent)"
        $args = @(
            (Join-Path $PSScriptRoot "run_qtn_5g_aelita_one_shot.py"),
            "--router-host", $RouterHost,
            "--oracle-host", $HostAddress,
            "--oracle-user", $User,
            "--controller-ip", $ControllerIp,
            "--restore-ssid", "MOVISTAR-WIFI6-A348",
            "--seconds", "120",
            "--v6-scheduler-diag"
        )
        if ($Execute) {
            $args += @(
                "--execute",
                "--ack", "OPENMITRASTAR_QTN_5G_AELITA_ONE_SHOT_RAM_ONLY",
                "--stable-2g-ack", "OPENMITRASTAR_2G_STABLE_FOR_QTN5G"
            )
        }
        & python @args
        exit $LASTEXITCODE
    }
}
