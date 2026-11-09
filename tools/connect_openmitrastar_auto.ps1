[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("all", "ssh", "uart", "topaz", "diag")]
    [string]$Mode = "all",
    [string]$HostAddress = "192.168.1.90",
    [string]$User = "root",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\id_ed25519",
    [string]$Port = "COM3",
    [int]$UartSeconds = 3600,
    [switch]$UpdateGlobalKnownHosts,
    [string]$ExpectedHostKeyFingerprint = "",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemoteCommand
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$out = Join-Path $Root "outputs\recovery\connect-auto\$stamp"
$sshDiagOut = Join-Path $Root "outputs\recovery\ssh-management\connect-auto-$stamp"
New-Item -ItemType Directory -Force -Path $out | Out-Null

function Write-Step([string]$Name, [string]$Detail = "") {
    if ($Detail) {
        Write-Host "OMCONNECT_STEP $Name $Detail"
    } else {
        Write-Host "OMCONNECT_STEP $Name"
    }
}

function Invoke-Tool([string]$Script, [string[]]$ArgsList) {
    $scriptPath = Join-Path $PSScriptRoot $Script
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        throw "Missing tool: $scriptPath"
    }
    & pwsh.exe -NoProfile -ExecutionPolicy Bypass -File $scriptPath @ArgsList
    $script:LastToolExitCode = $LASTEXITCODE
}

if (-not (Test-Path -LiteralPath $KeyPath)) {
    Write-Host "OMCONNECT_WARN missing_key=$KeyPath"
}

switch ($Mode) {
    "uart" {
        Write-Step "uart-capture" "port=$Port seconds=$UartSeconds out=$out"
        Invoke-Tool "connect_openmitrastar_uart.ps1" @(
            "-Mode", "capture",
            "-Port", $Port,
            "-Seconds", "$UartSeconds",
            "-OutputDirectory", $out
        )
        exit $script:LastToolExitCode
    }
    "topaz" {
        Write-Step "topaz-autobreak" "port=$Port out=$out"
        Invoke-Tool "connect_openmitrastar_uart.ps1" @(
            "-Mode", "topaz",
            "-Port", $Port,
            "-Seconds", "$UartSeconds",
            "-OutputDirectory", $out
        )
        exit $script:LastToolExitCode
    }
    "diag" {
        Write-Step "ssh-management-diag" "host=$HostAddress out=$sshDiagOut"
        & python (Join-Path $PSScriptRoot "diagnose_hgw500_ssh_management.py") `
            --host $HostAddress `
            --user $User `
            --key $KeyPath `
            --output-dir $sshDiagOut
        exit $LASTEXITCODE
    }
    "ssh" {
        Write-Step "ssh-connect" "host=$HostAddress user=$User"
        $args = @("-HostAddress", $HostAddress, "-User", $User, "-KeyPath", $KeyPath)
        if ($UpdateGlobalKnownHosts) { $args += "-UpdateGlobalKnownHosts" }
        if ($ExpectedHostKeyFingerprint) { $args += @("-ExpectedHostKeyFingerprint", $ExpectedHostKeyFingerprint) }
        if ($RemoteCommand.Count -gt 0) {
            $args += "-RemoteCommand"
            $args += ($RemoteCommand -join " ")
        }
        Invoke-Tool "ssh_openmitrastar_510.ps1" $args
        exit $script:LastToolExitCode
    }
    "all" {
        Write-Step "uart-capture-background" "port=$Port seconds=$UartSeconds out=$out"
        $uartArgs = @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $PSScriptRoot "connect_openmitrastar_uart.ps1"),
            "-Mode", "capture",
            "-Port", $Port,
            "-Seconds", "$UartSeconds",
            "-OutputDirectory", $out
        )
        $uartProc = Start-Process -FilePath "pwsh.exe" -ArgumentList $uartArgs -WindowStyle Hidden -PassThru
        Write-Host "OMCONNECT_UART_CAPTURE_STARTED pid=$($uartProc.Id)"

        Write-Step "ssh-management-diag" "host=$HostAddress"
        & python (Join-Path $PSScriptRoot "diagnose_hgw500_ssh_management.py") `
            --host $HostAddress `
            --user $User `
            --key $KeyPath `
            --output-dir $sshDiagOut
        $diagRc = $LASTEXITCODE
        Write-Host "OMCONNECT_DIAG_RC=$diagRc"

        Write-Step "ssh-connect" "host=$HostAddress user=$User"
        $sshArgs = @("-HostAddress", $HostAddress, "-User", $User, "-KeyPath", $KeyPath)
        if ($UpdateGlobalKnownHosts) { $sshArgs += "-UpdateGlobalKnownHosts" }
        if ($ExpectedHostKeyFingerprint) { $sshArgs += @("-ExpectedHostKeyFingerprint", $ExpectedHostKeyFingerprint) }
        if ($RemoteCommand.Count -gt 0) {
            $sshArgs += "-RemoteCommand"
            $sshArgs += ($RemoteCommand -join " ")
        }
        Invoke-Tool "ssh_openmitrastar_510.ps1" $sshArgs
        exit $script:LastToolExitCode
    }
}
