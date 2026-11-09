param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Command,
    [string]$QueuePath = "outputs\uart-live\uart-command-queue"
)

$ErrorActionPreference = "Stop"
if ($Command.Contains("`r") -or $Command.Contains("`n")) {
    throw "Command must be one UART line"
}
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$queue = [IO.Path]::GetFullPath((Join-Path $root $QueuePath))
New-Item -ItemType Directory -Force -Path $queue | Out-Null
$name = "{0:yyyyMMddHHmmssfffffff}-{1}.uart" -f [DateTime]::UtcNow, $PID
$temp = Join-Path $queue ($name + ".tmp")
$final = Join-Path $queue $name
[IO.File]::WriteAllText($temp, $Command, [Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $temp -Destination $final
$visibleCommand = if ($Command -match '^seed_') {
    'seed_<redacted>'
} else {
    $Command
}
Write-Output "UART_COMMAND_QUEUED=$visibleCommand"
