param(
    [string]$Port = "COM3",
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Command,
    [int]$TimeoutSeconds = 30,
    [string]$CredentialPath = ".\Accesos.txt",
    [string]$LogPath = ".\outputs\uart-live\oem-uart-exec.log"
)

$ErrorActionPreference = "Stop"

if ($Command.Contains("`r") -or $Command.Contains("`n")) {
    throw "Command must be a single shell line"
}

if ($env:OPENMITRASTAR_ROOT_PASSWORD) {
    $user = "root"
    $password = $env:OPENMITRASTAR_ROOT_PASSWORD
    $supportPassword = $null
} else {
    $credentials = Get-Content -LiteralPath $CredentialPath |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and -not $_.StartsWith("#") -and $_.Contains(":") }
    $loginCredential = $credentials |
        Where-Object { -not $_.StartsWith("support-shell:") } |
        Select-Object -First 1
    if (-not $loginCredential) {
        throw "No usable credential found in $CredentialPath"
    }
    $parts = $loginCredential.Split([char[]]@(':'), 2)
    $user = $parts[0].Trim()
    $password = $parts[1].Trim()
    $supportCredential = $credentials |
        Where-Object { $_.StartsWith("support-shell:") } |
        Select-Object -First 1
    $supportPassword = if ($supportCredential) {
        $supportCredential.Split([char[]]@(':'), 2)[1].Trim()
    } else {
        $null
    }
}

$logDirectory = Split-Path -Parent $LogPath
if ($logDirectory) {
    New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
}

$serial = [IO.Ports.SerialPort]::new(
    $Port, 115200, [IO.Ports.Parity]::None, 8,
    [IO.Ports.StopBits]::One)
$serial.Handshake = [IO.Ports.Handshake]::None
$serial.ReadTimeout = 150
$serial.WriteTimeout = 500
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$transcript = [Text.StringBuilder]::new()

function Read-Until {
    param(
        [string[]]$Markers,
        [int]$Seconds
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $chunk = $serial.ReadExisting()
        } catch [TimeoutException] {
            $chunk = ""
        }
        if ($chunk) {
            [void]$transcript.Append($chunk)
            Write-Host -NoNewline $chunk
            $all = $transcript.ToString()
            foreach ($marker in $Markers) {
                if ($all.IndexOf($marker, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                    return $marker
                }
            }
        }
        Start-Sleep -Milliseconds 40
    }
    throw "UART timeout waiting for: $($Markers -join ', ')"
}

try {
    $serial.Open()
    $serial.Write("`r")
    $state = Read-Until -Markers @("login:", "# ", ">") -Seconds $TimeoutSeconds

    if ($state -eq "login:") {
        $transcript.Clear() | Out-Null
        $serial.Write($user + "`r")
        [void](Read-Until -Markers @("Password:") -Seconds 10)
        $transcript.Clear() | Out-Null
        $serial.Write($password + "`r")
        $password = $null
        $state = Read-Until -Markers @("# ", ">") -Seconds 15
    }

    if ($state -eq ">") {
        if (-not $supportPassword) {
            throw "Restricted CLI reached but support-shell credential is absent"
        }
        $transcript.Clear() | Out-Null
        $serial.Write("sh`r")
        [void](Read-Until -Markers @("Password:") -Seconds 10)
        $transcript.Clear() | Out-Null
        $serial.Write($supportPassword + "`r")
        $supportPassword = $null
        [void](Read-Until -Markers @("# ") -Seconds 15)
    }

    $transcript.Clear() | Out-Null
    $serial.Write("stty -echo; echo __OMUART_READY__`r")
    [void](Read-Until -Markers @("__OMUART_READY__") -Seconds 10)

    $transcript.Clear() | Out-Null
    $payload = "echo __OMUART_BEGIN__; $Command; rc=`$?; echo __OMUART_RC=`$rc; echo __OMUART_END__"
    $serial.Write($payload + "`r")
    [void](Read-Until -Markers @("__OMUART_END__") -Seconds $TimeoutSeconds)
    $output = $transcript.ToString()
    Set-Content -LiteralPath $LogPath -Value $output -Encoding UTF8

    $match = [regex]::Match($output, "__OMUART_RC=(\d+)")
    if (-not $match.Success) {
        throw "UART command completed without a parseable return code"
    }
    Write-Host "`nOMUART_COMPLETE rc=$($match.Groups[1].Value) log=$LogPath"
    exit [int]$match.Groups[1].Value
} finally {
    $password = $null
    $supportPassword = $null
    Remove-Item Env:\OPENMITRASTAR_ROOT_PASSWORD -ErrorAction SilentlyContinue
    if ($serial.IsOpen) {
        $serial.Close()
    }
    $serial.Dispose()
}
