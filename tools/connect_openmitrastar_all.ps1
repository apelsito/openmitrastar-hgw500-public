param(
    [string]$HostAddress = "192.168.1.90",
    [string]$Port = "COM3",
    [int]$UartSeconds = 3600,
    [switch]$NoUart,
    [switch]$UpdateGlobalKnownHosts,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemoteCommand
)

$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$uartOut = Join-Path $Root "outputs\uart-live\combined-$stamp"

if (-not $NoUart) {
    New-Item -ItemType Directory -Force -Path $uartOut | Out-Null
    $uartArgs = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $PSScriptRoot "connect_openmitrastar_uart.ps1"),
        "-Mode", "capture",
        "-Port", $Port,
        "-Seconds", "$UartSeconds",
        "-OutputDirectory", $uartOut
    )
    $uartProc = Start-Process -FilePath "pwsh.exe" -ArgumentList $uartArgs -WindowStyle Hidden -PassThru
    Write-Host "OMCONNECT_UART_CAPTURE_STARTED pid=$($uartProc.Id) port=$Port out=$uartOut"
}

$sshArgs = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot "ssh_openmitrastar_510.ps1"),
    "-HostAddress", $HostAddress
)
if ($UpdateGlobalKnownHosts) {
    $sshArgs += "-UpdateGlobalKnownHosts"
}
if ($RemoteCommand.Count -gt 0) {
    $sshArgs += $RemoteCommand
}

& pwsh.exe @sshArgs
exit $LASTEXITCODE
