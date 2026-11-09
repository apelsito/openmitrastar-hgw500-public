[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$HostAddress = "192.168.1.90",
    [string]$User = "root",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\id_ed25519",
    [int]$Blocks = 128,
    [int]$BlockBytes = 65536,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f5-emac-ssh-throughput-$stamp"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$ssh = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"
$sshKeygen = Join-Path $env:WINDIR "System32\OpenSSH\ssh-keygen.exe"
$sshKeyscan = Join-Path $env:WINDIR "System32\OpenSSH\ssh-keyscan.exe"
$knownHosts = Join-Path $OutputDir "known_hosts"
$before = Join-Path $OutputDir "before.txt"
$after = Join-Path $OutputDir "after.txt"
$sink = Join-Path $OutputDir "download.bin"
$summary = Join-Path $OutputDir "summary.json"

if (Test-Path -LiteralPath $knownHosts) {
    & $sshKeygen -R $HostAddress -f $knownHosts *> $null
}
try {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $scanText = & $sshKeyscan -T 5 -t ed25519,rsa $HostAddress 2>&1
} finally {
    $ErrorActionPreference = $previousErrorActionPreference
}
$scanText |
    ForEach-Object { "$_" } |
    Where-Object { $_ -match '^\S+\s+(ssh-ed25519|ssh-rsa)\s+' } |
    Set-Content -Encoding ascii -LiteralPath $knownHosts

$sshArgs = @(
    "-i", $KeyPath,
    "-o", "IdentitiesOnly=yes",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=8",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "UserKnownHostsFile=$knownHosts",
    "-o", "HostKeyAlgorithms=+ssh-rsa",
    "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa",
    "-o", "LogLevel=ERROR",
    "$User@$HostAddress"
)

$sampleCommand = @'
echo SECTION_UNAME
uname -r
echo SECTION_NETDEV
cat /proc/net/dev
echo SECTION_INTERRUPTS
cat /proc/interrupts
echo SECTION_DMESG_EMAC
dmesg | tail -n 120 | grep -E 'OMEMAC|qtn-topaz-emac|stall|panic|Oops' || true
echo SECTION_DONE
'@

& $ssh @sshArgs $sampleCommand > $before
$beforeRc = $LASTEXITCODE

$downloadCommand = "dd if=/dev/zero bs=$BlockBytes count=$Blocks 2>/dev/null"
$timer = [Diagnostics.Stopwatch]::StartNew()
& $ssh @sshArgs $downloadCommand > $sink
$downloadRc = $LASTEXITCODE
$timer.Stop()

& $ssh @sshArgs $sampleCommand > $after
$afterRc = $LASTEXITCODE

$bytes = 0
if (Test-Path -LiteralPath $sink) {
    $bytes = (Get-Item -LiteralPath $sink).Length
    Remove-Item -LiteralPath $sink -Force
}

$result = [ordered]@{
    schema = "openmitrastar.f5-emac-ssh-throughput/v1"
    host = $HostAddress
    output_dir = $OutputDir
    flash = $false
    reboot = $false
    router_mutations = $false
    before_rc = $beforeRc
    download_rc = $downloadRc
    after_rc = $afterRc
    bytes = $bytes
    elapsed_ms = $timer.ElapsedMilliseconds
    approx_bytes_per_sec = [int]($bytes / [Math]::Max($timer.Elapsed.TotalSeconds, 0.001))
    before = $before
    after = $after
    terminal_state = if ($beforeRc -eq 0 -and $downloadRc -eq 0 -and $afterRc -eq 0 -and $bytes -eq ($Blocks * $BlockBytes)) { "PASS" } else { "FAIL" }
    updated_at = (Get-Date).ToString("o")
}
$result | ConvertTo-Json -Depth 5 | Set-Content -Encoding ascii -LiteralPath $summary
Get-Content -LiteralPath $summary -Raw
if ($result.terminal_state -eq "PASS") { exit 0 }
exit 1
