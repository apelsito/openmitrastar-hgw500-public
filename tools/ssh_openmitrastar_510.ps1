param(
    [string]$HostAddress = "192.168.1.90",
    [string]$User = "root",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\id_ed25519",
    [string]$KnownHostsPath = "NUL",
    [switch]$NoHostKeyRefresh,
    [switch]$UpdateGlobalKnownHosts,
    [string]$ExpectedHostKeyFingerprint = "",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemoteCommand
)

$ErrorActionPreference = "Stop"
if ($RemoteCommand.Count -eq 0 -and $HostAddress -match '[\s;&|]') {
    $RemoteCommand = @($HostAddress)
    $HostAddress = "192.168.1.90"
}
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
if ($KnownHostsPath -ieq "NUL") {
    $knownHosts = "NUL"
} else {
    $knownHosts = [IO.Path]::GetFullPath((Join-Path $root $KnownHostsPath))
    New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($knownHosts)) | Out-Null
}

$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$sshKeygen = Join-Path $env:WINDIR "System32\OpenSSH\ssh-keygen.exe"
$sshKeyscan = Join-Path $env:WINDIR "System32\OpenSSH\ssh-keyscan.exe"

function Update-KnownHostsFile([string]$Path) {
    New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($Path)) | Out-Null
    if (Test-Path -LiteralPath $Path) {
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & $sshKeygen -R $HostAddress -f $Path *> $null
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
    }
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $scanOutput = & $sshKeyscan -T 5 -t ed25519,rsa $HostAddress 2>$null
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $scan = @($scanOutput | Where-Object {
        $_ -and
        -not $_.StartsWith("#") -and
        $_ -match '^\S+\s+(ssh-ed25519|ssh-rsa)\s+'
    })
    if ($LASTEXITCODE -ne 0 -or -not $scan) {
        Write-Host "OMSSH_HOSTKEY_REFRESH_SKIPPED host=$HostAddress reason=ssh-keyscan-empty"
        return
    }
    if ($ExpectedHostKeyFingerprint) {
        $tempScan = Join-Path $env:TEMP ("openmitrastar-hostkey-{0}.scan" -f ([Guid]::NewGuid().ToString("N")))
        try {
            Set-Content -LiteralPath $tempScan -Value $scan -Encoding ascii
            $fingerprints = @(& $sshKeygen -lf $tempScan -E sha256 2>$null)
            if (-not ($fingerprints | Where-Object { $_ -match [regex]::Escape($ExpectedHostKeyFingerprint) })) {
                throw "SSH host key fingerprint mismatch for $HostAddress"
            }
        } finally {
            Remove-Item -LiteralPath $tempScan -Force -ErrorAction SilentlyContinue
        }
    }
    Add-Content -LiteralPath $Path -Value $scan -Encoding ascii
    Write-Host "OMSSH_HOSTKEY_REFRESH_OK host=$HostAddress file=$Path entries=$($scan.Count)"
}

if ($knownHosts -ne "NUL" -and -not $NoHostKeyRefresh) {
    Update-KnownHostsFile $knownHosts
}
if ($UpdateGlobalKnownHosts) {
    Update-KnownHostsFile (Join-Path $env:USERPROFILE ".ssh\known_hosts")
}

$args = @(
    "-i", $KeyPath,
    "-o", "IdentitiesOnly=yes",
    "-o", $(if ($knownHosts -eq "NUL") { "StrictHostKeyChecking=no" } else { "StrictHostKeyChecking=accept-new" }),
    "-o", "UserKnownHostsFile=$knownHosts",
    "-o", "HostKeyAlgorithms=+ssh-rsa",
    "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa",
    "-o", "LogLevel=ERROR",
    "$User@$HostAddress"
)
if ($RemoteCommand.Count -gt 0) {
    $args += ($RemoteCommand -join " ")
}

& $ssh @args
exit $LASTEXITCODE
