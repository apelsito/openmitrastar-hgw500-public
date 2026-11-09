[CmdletBinding()]
param(
    [string]$BindAddress = '192.168.1.43',
    [int]$Port = 8081,
    [int]$FileSizeMiB = 32
)

$ErrorActionPreference = 'Stop'
$root = Join-Path $PSScriptRoot '..\outputs\kernel-port\realtek-loop\wifi-oracle-server'
$root = [IO.Path]::GetFullPath($root)
New-Item -ItemType Directory -Force -Path $root | Out-Null

$payload = Join-Path $root 'downlink.bin'
if (-not (Test-Path -LiteralPath $payload) -or
    (Get-Item -LiteralPath $payload).Length -ne ($FileSizeMiB * 1MB)) {
    $stream = [IO.File]::Open($payload, [IO.FileMode]::Create,
        [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try { $stream.SetLength($FileSizeMiB * 1MB) } finally { $stream.Dispose() }
}

$existing = Get-NetTCPConnection -LocalAddress $BindAddress -LocalPort $Port `
    -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Output "OM2G_ORACLE_SERVER_ALREADY_LISTENING=$BindAddress`:$Port"
    exit 0
}

$python = (Get-Command python.exe -ErrorAction Stop).Source
$stdout = Join-Path $root 'http.stdout.log'
$stderr = Join-Path $root 'http.stderr.log'
$process = Start-Process -FilePath $python `
    -ArgumentList @('-m', 'http.server', "$Port", '--bind', $BindAddress, '--directory', $root) `
    -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru

Start-Sleep -Milliseconds 700
if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
    throw "Oracle HTTP server failed to start; inspect $stderr"
}

[pscustomobject]@{
    schema = 'openmitrastar.wifi-oracle-server/v1'
    pid = $process.Id
    address = $BindAddress
    port = $Port
    payload = $payload
    bytes = (Get-Item -LiteralPath $payload).Length
    url = "http://$BindAddress`:$Port/downlink.bin"
} | ConvertTo-Json

