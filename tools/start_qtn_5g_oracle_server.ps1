[CmdletBinding()]
param(
    [switch]$Execute,
    [string]$Ack = '',
    [string]$BindAddress = '192.168.1.43',
    [int]$Port = 8081,
    [int]$DownloadMiB = 32,
    [int]$MaxUploadMiB = 64,
    [string]$OutputDirectory = ''
)

$ErrorActionPreference = 'Stop'
$requiredAck = 'OPENMITRASTAR_QTN_5G_ORACLE_SERVER_LOCAL_ONLY'
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $PSScriptRoot '..\outputs\kernel-port\quantenna-5g-windows-oracle-server'
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)

if (-not $Execute) {
    [ordered]@{
        schema = 'openmitrastar.qtn-5g-oracle-server-plan/v1'
        execute = $false
        bind = $BindAddress
        port = $Port
        download_mib = $DownloadMiB
        max_upload_mib = $MaxUploadMiB
        endpoints = @('/speed.bin', '/upload.bin')
        firewall_changes = $false
    } | ConvertTo-Json -Depth 4
    Write-Output 'OMQTN5G_ORACLE_SERVER_DRY_RUN_PASS=1 execute=0 firewall=unchanged'
    exit 0
}
if ($Ack -ne $requiredAck) { throw "Require -Ack $requiredAck" }
if ($DownloadMiB -lt 8 -or $DownloadMiB -gt 256) { throw 'DownloadMiB must be 8..256' }
if ($MaxUploadMiB -lt 8 -or $MaxUploadMiB -gt 256) { throw 'MaxUploadMiB must be 8..256' }

$serverScript = Join-Path $PSScriptRoot 'openmitrastar_l2_speed_server.py'
if (-not (Test-Path -LiteralPath $serverScript)) { throw "Missing server: $serverScript" }
$existing = Get-NetTCPConnection -LocalAddress $BindAddress -LocalPort $Port `
    -State Listen -ErrorAction SilentlyContinue
if ($existing) { throw "Port already has a listener: $BindAddress`:$Port" }

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$python = (Get-Command python.exe -ErrorAction Stop).Source
$stdout = Join-Path $OutputDirectory 'server.stdout.log'
$stderr = Join-Path $OutputDirectory 'server.stderr.log'
$pidFile = Join-Path $OutputDirectory 'server.pid'
$process = Start-Process -FilePath $python -ArgumentList @(
    $serverScript, '--bind', $BindAddress, '--port', $Port,
    '--mib', $DownloadMiB, '--max-upload-mib', $MaxUploadMiB
) -WindowStyle Hidden -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr -PassThru
Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ascii

$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 200
    if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
        throw "Oracle server exited; inspect $stderr"
    }
    if ((Test-Path -LiteralPath $stdout) -and
        (Get-Content -LiteralPath $stdout -Raw) -match 'OML2_HTTP_READY') {
        $ready = $true
        break
    }
}
if (-not $ready) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw 'Oracle server did not emit readiness marker'
}

[ordered]@{
    schema = 'openmitrastar.qtn-5g-oracle-server/v1'
    pid = $process.Id
    bind = $BindAddress
    port = $Port
    download_url = "http://$BindAddress`:$Port/speed.bin"
    upload_url = "http://$BindAddress`:$Port/upload.bin"
    pid_file = $pidFile
    stdout = $stdout
    stderr = $stderr
    firewall_changes = $false
} | ConvertTo-Json -Depth 4
