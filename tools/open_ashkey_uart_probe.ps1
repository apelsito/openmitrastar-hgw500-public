param(
    [string]$PortName = "COM3",
    [int[]]$BaudRates = @(115200, 57600, 38400, 9600),
    [int]$CaptureSeconds = 40,
    [int]$PrepareSeconds = 25,
    [int]$PowerOffSeconds = 18,
    [string]$OutputRoot = "outputs\open-ashkey"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path ".").Path
$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$outDir = Join-Path $root (Join-Path $OutputRoot "uart-pin3-$stamp")
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function Write-Banner([string]$Text, [ConsoleColor]$Color = [ConsoleColor]::Cyan) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor $Color
    Write-Host $Text -ForegroundColor $Color
    Write-Host ("=" * 72) -ForegroundColor $Color
}

$host.UI.RawUI.WindowTitle = "Open ASHKEY - UART RTF8115VW"
Clear-Host
Write-Banner "OPEN ASHKEY - PRUEBA UART PASIVA J502" Green
Write-Host "ROUTER APAGADO. Conecta exactamente:" -ForegroundColor Yellow
Write-Host "  J502 pin 1: VACIO"
Write-Host "  J502 pin 2: VERDE -> GND del FTDI"
Write-Host "  J502 pin 3: NARANJA -> RXD del FTDI"
Write-Host "  J502 pin 4: VACIO"
Write-Host "  AMARILLO/TXD del FTDI: DESCONECTADO"
Write-Host "  VCC del FTDI: DESCONECTADO"
Write-Host ""
Write-Host "Tienes $PrepareSeconds segundos para dejarlo preparado. NO lo enciendas aun." -ForegroundColor Yellow
for ($remaining = $PrepareSeconds; $remaining -gt 0; $remaining--) {
    Write-Host ("`rPreparacion: {0,2} s " -f $remaining) -NoNewline
    Start-Sleep -Seconds 1
}
Write-Host ""

foreach ($baud in $BaudRates) {
    $rawPath = Join-Path $outDir ("com3-{0}.raw" -f $baud)
    $textPath = Join-Path $outDir ("com3-{0}.log" -f $baud)
    $port = [System.IO.Ports.SerialPort]::new(
        $PortName,
        $baud,
        [System.IO.Ports.Parity]::None,
        8,
        [System.IO.Ports.StopBits]::One
    )
    $port.Handshake = [System.IO.Ports.Handshake]::None
    $port.DtrEnable = $false
    $port.RtsEnable = $false
    $port.ReadTimeout = 100

    try {
        $port.Open()
        [Console]::Beep(1000, 500)
        [Console]::Beep(1400, 500)
        Write-Banner "LISTENING $PortName @ $baud 8N1 - ENCIENDE AHORA" Green
        Write-Host "No pulses teclas. No muevas los cables. Captura: $CaptureSeconds s" -ForegroundColor Yellow
        $start = Get-Date
        $lastStatus = -1
        $total = 0
        $buffer = New-Object byte[] 4096

        while (((Get-Date) - $start).TotalSeconds -lt $CaptureSeconds) {
            $available = $port.BytesToRead
            if ($available -gt 0) {
                $take = [Math]::Min($available, $buffer.Length)
                $read = $port.Read($buffer, 0, $take)
                if ($read -gt 0) {
                    $stream = [System.IO.File]::Open(
                        $rawPath,
                        [System.IO.FileMode]::Append,
                        [System.IO.FileAccess]::Write,
                        [System.IO.FileShare]::ReadWrite
                    )
                    try { $stream.Write($buffer, 0, $read) } finally { $stream.Dispose() }
                    $text = [System.Text.Encoding]::GetEncoding(28591).GetString($buffer, 0, $read)
                    [System.IO.File]::AppendAllText($textPath, $text, [System.Text.Encoding]::UTF8)
                    [Console]::Write($text)
                    $total += $read
                }
            }
            $elapsed = [int]((Get-Date) - $start).TotalSeconds
            if ($elapsed -ne $lastStatus -and ($elapsed % 5) -eq 0) {
                Write-Host ("`n[{0}s, {1} bytes]" -f $elapsed, $total) -ForegroundColor DarkGray
                $lastStatus = $elapsed
            }
            Start-Sleep -Milliseconds 10
        }
    }
    finally {
        if ($port.IsOpen) { $port.Close() }
    }

    if ($total -ge 16) {
        [Console]::Beep(1600, 800)
        Write-Banner "UART CON ACTIVIDAD: $total bytes @ $baud - NO TOQUES NADA" Green
        Set-Content -LiteralPath (Join-Path $outDir "DETECTED.json") -Encoding UTF8 -Value (
            [pscustomobject]@{ port=$PortName; baud=$baud; bytes=$total; raw=$rawPath; log=$textPath } | ConvertTo-Json
        )
        break
    }
    [Console]::Beep(500, 800)
    Write-Banner "FIN ${baud}: $total bytes - APAGA AHORA" Yellow
    for ($remaining = $PowerOffSeconds; $remaining -gt 0; $remaining--) {
        Write-Host ("`rApagado/enfriado: {0,2} s " -f $remaining) -NoNewline
        Start-Sleep -Seconds 1
    }
    Write-Host ""
}

Write-Banner "PRUEBAS TERMINADAS - DEJA EL ROUTER APAGADO" Cyan
Write-Host "Evidencia: $outDir"
Write-Host "Esta ventana permanecera abierta."
