[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$HostAddress = "192.168.1.90",
    [ValidateRange(5, 3600)]
    [int]$PollSeconds = 30,
    [ValidateRange(60, 86400)]
    [int]$TimeoutSeconds = 21600,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$WatchScript = Join-Path $PSScriptRoot "watch_f93_f95_chain_status.ps1"

function Get-ExistingWatchProcess {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -in @("powershell.exe", "pwsh.exe") -and
            [string]$_.CommandLine -match "watch_f93_f95_chain_status\.ps1" -and
            [string]$_.CommandLine -match "\-File" -and
            [string]$_.CommandLine -notmatch "Get-CimInstance|pytest|scriptblock|PARSE_OK|ensure_f93_f95_status_watch"
        } |
        Sort-Object CreationDate |
        Select-Object -First 1
}

function Get-OutputDirFromCommand([AllowNull()][string]$CommandLine) {
    if ([string]::IsNullOrWhiteSpace($CommandLine)) { return "" }
    if ($CommandLine -match '(?i)-OutputDir\s+("?)([^"\s]+)\1') {
        return $Matches[2]
    }
    return ""
}

if (-not $OutputDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputDir = Join-Path $Root "outputs\postflash\f93-f95-status-watch-$stamp"
}
$OutputDir = [IO.Path]::GetFullPath($OutputDir)

$existing = Get-ExistingWatchProcess
if ($existing) {
    $existingOutputDir = Get-OutputDirFromCommand ([string]$existing.CommandLine)
    [ordered]@{
        schema = "openmitrastar.ensure-f93-f95-status-watch/v1"
        state = "already_running"
        pid = [int]$existing.ProcessId
        output_dir = $existingOutputDir
        command = [string]$existing.CommandLine
    } | ConvertTo-Json -Depth 4
    exit 0
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$stdout = Join-Path $OutputDir "watch.stdout.log"
$stderr = Join-Path $OutputDir "watch.stderr.log"
$pwsh = (Get-Process -Id $PID -ErrorAction SilentlyContinue).Path
if (-not $pwsh) { $pwsh = "pwsh.exe" }

$args = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", $WatchScript,
    "-HostAddress", $HostAddress,
    "-PollSeconds", [string]$PollSeconds,
    "-TimeoutSeconds", [string]$TimeoutSeconds,
    "-OutputDir", $OutputDir
)
$proc = Start-Process -FilePath $pwsh -WindowStyle Hidden -WorkingDirectory $Root `
    -ArgumentList $args -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru

[ordered]@{
    schema = "openmitrastar.ensure-f93-f95-status-watch/v1"
    state = "started"
    pid = [int]$proc.Id
    output_dir = $OutputDir
    stdout = $stdout
    stderr = $stderr
} | ConvertTo-Json -Depth 4
