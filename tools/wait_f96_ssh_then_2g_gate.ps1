[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$ArmStatusPath = "/workspace/user-home\Desktop\MitraStar\outputs\postflash\f96-armed-20260827-121935\status.json",
    [string]$HostAddress = "192.168.1.90",
    [int]$WaitSeconds = 21600,
    [int]$PollSeconds = 5,
    [string]$RouterKey = "$env:USERPROFILE\.ssh\id_ed25519",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f96-post-powercycle-2g-gate-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$statusPath = Join-Path $OutputDir "wait-status.json"

function Write-Status([string]$State, [string]$Message) {
    [ordered]@{
        schema = "openmitrastar.wait-f96-ssh-then-2g-gate/v1"
        state = $State
        message = $Message
        host = $HostAddress
        output_dir = $OutputDir
        arm_status_path = $ArmStatusPath
        updated_at = (Get-Date).ToString("o")
    } | ConvertTo-Json -Depth 5 | Set-Content -Encoding ascii -LiteralPath $statusPath
}

function Test-TcpQuiet([string]$HostName, [int]$Port, [int]$TimeoutMs = 1500) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

Write-Status "waiting_ssh" "waiting for router SSH after power cycle"
$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $deadline) {
    if (Test-TcpQuiet $HostAddress 22) {
        Write-Status "running_gate" "router SSH is reachable; running F96 SSH and AELITA 2.4 gate"
        & (Join-Path $PSScriptRoot "monitor_f96_flash_then_2g_gate.ps1") `
            -ArmStatusPath $ArmStatusPath `
            -OutputDir $OutputDir `
            -TimeoutSeconds 900 `
            -PollSeconds 5 `
            -RouterKey $RouterKey
        exit $LASTEXITCODE
    }
    Start-Sleep -Seconds $PollSeconds
}

Write-Status "timeout" "timeout waiting for router SSH after power cycle"
exit 1
