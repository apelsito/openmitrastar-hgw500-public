[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$FlashStatusPath = "/workspace/user-home\Desktop\MitraStar\outputs\flash-watch\f87-armed-powercycle-20260826-231449\status.json",
    [string]$HostAddress = "192.168.1.90",
    [string]$RouterUser = "root",
    [string]$RouterKey = "/workspace/user-home\Desktop\MitraStar\.codex_tmp\openmitrastar_ramssh_client_ed25519",
    [string]$OracleHost = "192.168.1.63",
    [string]$OracleUser = "AELITA",
    [string]$ControllerUrl = "http://192.168.1.43:8008/speed.bin",
    [double]$Min2gMbps = 5.0,
    [double]$Diag2gMbps = 20.0,
    [int]$TimeoutSeconds = 21600,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f87-current-watch-pass-then-stage-gate-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Resolve-PowerShellHost {
    $pwshInHome = Join-Path $PSHOME "pwsh.exe"
    if (Test-Path -LiteralPath $pwshInHome -PathType Leaf) { return $pwshInHome }
    $pwsh = Get-Command pwsh.exe -ErrorAction SilentlyContinue
    if ($pwsh) { return $pwsh.Source }
    return (Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe")
}

$pshost = Resolve-PowerShellHost
$args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot "monitor_f87_flash_then_stage_gate.ps1"),
    "-FlashStatusPath", $FlashStatusPath,
    "-TimeoutSeconds", [string]$TimeoutSeconds,
    "-HostAddress", $HostAddress,
    "-RouterUser", $RouterUser,
    "-RouterKey", $RouterKey,
    "-OracleHost", $OracleHost,
    "-OracleUser", $OracleUser,
    "-ControllerUrl", $ControllerUrl,
    "-Min2gMbps", [string]$Min2gMbps,
    "-Diag2gMbps", [string]$Diag2gMbps,
    "-OutputDir", $OutputDir
)

$proc = Start-Process -FilePath $pshost -WindowStyle Hidden `
    -ArgumentList $args `
    -RedirectStandardOutput (Join-Path $OutputDir "stdout.log") `
    -RedirectStandardError (Join-Path $OutputDir "stderr.log") `
    -PassThru

$status = [ordered]@{
    schema = "openmitrastar.f87-current-monitor-launch/v1"
    state = "launched"
    updated_at = (Get-Date).ToString("o")
    output_dir = $OutputDir
    monitor_pid = [int]$proc.Id
    flash_status_path = $FlashStatusPath
    pshost = $pshost
}
$status | ConvertTo-Json -Depth 6 | Set-Content -Encoding ascii -LiteralPath (Join-Path $OutputDir "launch-status.json")
Write-Host "OMF87_CURRENT_MONITOR_LAUNCHED=1 pid=$($proc.Id) output_dir=$OutputDir"
