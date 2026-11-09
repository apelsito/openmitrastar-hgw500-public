[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateRange(5, 300)][int]$PollSeconds = 15,
    [ValidateRange(60, 43200)][int]$MaxWaitSeconds = 21600,
    [ValidateRange(60, 900)][int]$TestSeconds = 120,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $OutputDir = Join-Path $Root "outputs\watchdogs\f141-aelita-5g-certification-active"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$StatusPath = Join-Path $OutputDir "status.json"
$LogPath = Join-Path $OutputDir "watchdog.log"

function Write-Status([string]$State, [string]$Message, [hashtable]$Extra = @{}) {
    $payload = [ordered]@{
        schema = "openmitrastar.f141-aelita-watchdog/v1"
        state = $State
        message = $Message
        updated_at = (Get-Date).ToString("o")
        pid = $PID
        output_dir = $OutputDir
        poll_seconds = $PollSeconds
        max_wait_seconds = $MaxWaitSeconds
        test_seconds = $TestSeconds
        router_flash = $false
        router_mutations = $false
    }
    foreach ($key in $Extra.Keys) { $payload[$key] = $Extra[$key] }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -Encoding ascii -LiteralPath $StatusPath
    "[$((Get-Date).ToString('o'))] $State $Message" | Add-Content -Encoding ascii -LiteralPath $LogPath
}

function Test-Tcp([string]$Address, [int]$Port, [int]$TimeoutMs = 750) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($Address, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

$deadline = [DateTime]::UtcNow.AddSeconds($MaxWaitSeconds)
Write-Status "waiting_aelita" "waiting for AELITA SSH at 192.168.1.63"
while ([DateTime]::UtcNow -lt $deadline) {
    $routerUp = Test-Tcp "192.168.1.90" 22
    $aelitaUp = Test-Tcp "192.168.1.63" 22
    if ($routerUp -and $aelitaUp) {
        Write-Status "running_gate" "AELITA and router reachable; starting F141 certification"
        $resultDir = Join-Path $Root "outputs\f3-certification\qtn-5g-f141-aelita"
        & python.exe (Join-Path $Root "tools\run_f141_5g_aelita_certification.py") `
            --execute --ack OPENMITRASTAR_F141_5G_AELITA_CERTIFICATION `
            --seconds $TestSeconds --output-dir $resultDir *> (Join-Path $OutputDir "certification.log")
        $rc = $LASTEXITCODE
        if ($rc -eq 0) {
            Write-Status "pass" "F141 AELITA association and traffic certification passed" @{
                certification_log = (Join-Path $OutputDir "certification.log")
            }
            exit 0
        }
        Write-Status "gate_failed" "F141 AELITA certification ran and failed" @{
            exit_code = $rc
            certification_log = (Join-Path $OutputDir "certification.log")
        }
        exit $rc
    }
    Write-Status "waiting_aelita" "AELITA SSH unavailable; router remains untouched" @{
        router_ssh = $routerUp
        aelita_ssh = $aelitaUp
    }
    Start-Sleep -Seconds $PollSeconds
}

Write-Status "timeout" "AELITA did not become reachable before timeout"
exit 3
