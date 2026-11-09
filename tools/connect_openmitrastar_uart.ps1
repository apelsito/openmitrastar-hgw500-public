param(
    [ValidateSet("interactive", "capture", "topaz")]
    [string]$Mode = "interactive",
    [string]$Port = "COM3",
    [int]$Baud = 115200,
    [int]$Seconds = 1200,
    [string]$OutputDirectory = "",
    [string]$RunId = ""
)

$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $Root "outputs\uart-live\connect-$Mode-$stamp"
} else {
    $OutputDirectory = [IO.Path]::GetFullPath((Join-Path $Root $OutputDirectory))
}
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

function Get-WorkspaceRelativePath([string]$BasePath, [string]$TargetPath) {
    if ([IO.Path].GetMethod("GetRelativePath", [type[]]@([string], [string]))) {
        return [IO.Path]::GetRelativePath($BasePath, $TargetPath)
    }
    $baseUri = [Uri](([IO.Path]::GetFullPath($BasePath).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar))
    $targetUri = [Uri]([IO.Path]::GetFullPath($TargetPath))
    return [Uri]::UnescapeDataString($baseUri.MakeRelativeUri($targetUri).ToString()).Replace('/', [IO.Path]::DirectorySeparatorChar)
}

switch ($Mode) {
    "interactive" {
        $log = Join-Path $OutputDirectory "interactive-uart.log"
        & (Join-Path $PSScriptRoot "interactive_uart_terminal.ps1") `
            -Port $Port `
            -Baud $Baud `
            -LogPath (Get-WorkspaceRelativePath $Root $log)
        exit $LASTEXITCODE
    }
    "capture" {
        if (-not $RunId) { $RunId = "uart-capture-$stamp" }
        & (Join-Path $PSScriptRoot "capture_topaz_uart_resilient.ps1") `
            -Port $Port `
            -Baud $Baud `
            -Seconds $Seconds `
            -OutputDirectory $OutputDirectory `
            -RunId $RunId
        exit $LASTEXITCODE
    }
    "topaz" {
        $log = Join-Path $OutputDirectory "topaz-autoboot-break.log"
        & (Join-Path $PSScriptRoot "interrupt_topaz_autoboot.ps1") `
            -Port $Port `
            -LogPath ([IO.Path]::GetRelativePath($Root, $log)) `
            -TimeoutSeconds $Seconds
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        $topazLog = Join-Path $OutputDirectory "zhal-to-topaz.log"
        & (Join-Path $PSScriptRoot "reboot_to_topaz_prompt_sysrq.ps1") `
            -Port $Port `
            -NoReboot `
            -LogPath ([IO.Path]::GetRelativePath($Root, $topazLog)) `
            -TimeoutSeconds 90
        exit $LASTEXITCODE
    }
}
