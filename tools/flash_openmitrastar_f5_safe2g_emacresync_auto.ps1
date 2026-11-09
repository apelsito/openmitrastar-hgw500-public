[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Execute,
    [string]$Ack = "",
    [string]$Port = "COM3",
    [string]$ServerIp = "192.168.1.43",
    [string]$ClientIp = "192.168.1.90",
    [string]$HostAddress = "192.168.1.90",
    [int]$BootWaitSeconds = 600,
    [int]$FlashTimeoutSeconds = 900,
    [string]$CurrentLiveCrc32 = "05674ac6",
    [switch]$SysRqRebootFirst,
    [switch]$PulseResetLinesFirst,
    [switch]$KeepExistingTftp,
    [switch]$SkipPostSsh
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RequiredAck = "OPENMITRASTAR_F5_SAFE2G_EMACRESYNC_MTD4_FLASH_REQUIRESBUILD"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runDir = Join-Path $Root "outputs\flash-auto\f5-safe2g-emacresync-$stamp"
$sshDiagOut = Join-Path $Root "outputs\recovery\ssh-management\f5-safe2g-emacresync-postflash-$stamp"
$transcript = Join-Path $runDir "flash-openmitrastar-f5-auto.transcript.log"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

function Write-Phase([string]$Name, [string]$Detail = "") {
    if ($Detail) {
        Write-Host "OMFLASH_PHASE $Name $Detail"
    } else {
        Write-Host "OMFLASH_PHASE $Name"
    }
}

function Fail-Phase([string]$Name, [object]$ErrorObject) {
    Write-Host "OMFLASH_FAIL phase=$Name error=$ErrorObject"
    Write-Host "OMFLASH_EVIDENCE_DIR=$runDir"
}

Start-Transcript -LiteralPath $transcript -Force | Out-Null
try {
    Write-Phase "preflight" "run=$runDir port=$Port host=$HostAddress"
    if (-not $Execute) {
        throw "Use -Execute -Ack $RequiredAck to arm physical flash."
    }
    if ($Ack -ne $RequiredAck) {
        throw "Exact ack required: $RequiredAck"
    }
    if ($CurrentLiveCrc32 -notmatch '^[0-9a-fA-F]{8}$') {
        throw "CurrentLiveCrc32 must be 8 hex characters"
    }
    $ports = [IO.Ports.SerialPort]::GetPortNames()
    if ($ports -notcontains $Port) {
        throw "UART port $Port not visible. Visible ports: $($ports -join ',')"
    }

    Write-Phase "bootbase-autobreak" "sequence=space_ATGU_space_topaz"
    $args = @(
        "-Execute",
        "-Ack", $RequiredAck,
        "-Port", $Port,
        "-ServerIp", $ServerIp,
        "-ClientIp", $ClientIp,
        "-HostAddress", $HostAddress,
        "-BootWaitSeconds", "$BootWaitSeconds",
        "-FlashTimeoutSeconds", "$FlashTimeoutSeconds",
        "-CurrentLiveCrc32", $CurrentLiveCrc32
    )
    if ($KeepExistingTftp) { $args += "-KeepExistingTftp" }
    if ($SysRqRebootFirst) { $args += "-SysRqRebootFirst" }
    if ($PulseResetLinesFirst) { $args += "-PulseResetLinesFirst" }

    & pwsh.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "f5_safe2g_emacresync_autoboot_atgu_flash.ps1") @args
    $flashRc = $LASTEXITCODE
    Write-Host "OMFLASH_BACKEND_RC=$flashRc"
    if ($flashRc -ne 0) {
        throw "F5 flash backend returned $flashRc"
    }

    if (-not $SkipPostSsh) {
        Write-Phase "post-ssh-diagnostic" "host=$HostAddress out=$sshDiagOut"
        & python (Join-Path $PSScriptRoot "diagnose_hgw500_ssh_management.py") `
            --host $HostAddress `
            --output-dir $sshDiagOut
        $diagRc = $LASTEXITCODE
        Write-Host "OMFLASH_POST_SSH_DIAG_RC=$diagRc"
        if ($diagRc -ne 0) {
            throw "post SSH diagnostic returned $diagRc"
        }

        Write-Phase "post-ssh-smoke" "host=$HostAddress"
        & pwsh.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "ssh_openmitrastar_510.ps1") `
            -HostAddress $HostAddress `
            -RemoteCommand "echo OMFLASH_POST_SSH_OK; uname -r; uptime"
        $sshRc = $LASTEXITCODE
        Write-Host "OMFLASH_POST_SSH_RC=$sshRc"
        if ($sshRc -ne 0) {
            throw "post SSH smoke returned $sshRc"
        }
    }

    Write-Host "OMFLASH_PASS=1 profile=F5_SAFE2G_EMACRESYNC partition=mtd4/linux_live host=$HostAddress evidence=$runDir"
    exit 0
} catch {
    Fail-Phase "flash-openmitrastar-f5-auto" $_.Exception.Message
    exit 1
} finally {
    Stop-Transcript | Out-Null
}


