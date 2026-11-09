[CmdletBinding(PositionalBinding=$false)]
param([Parameter(Mandatory=$true)][string]$AttemptDir,[Parameter(Mandatory=$true)][string]$EvidenceDir,[switch]$SkipRamCrcObservation)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'f319_uart_guard.ps1')
$attempt=Get-Content -LiteralPath (Join-Path $AttemptDir 'result.json') -Raw | ConvertFrom-Json
$ram=Get-Content -LiteralPath (Join-Path $AttemptDir 'writer/ethernet-ram-result.json') -Raw | ConvertFrom-Json
$native=Get-Content -LiteralPath (Join-Path $AttemptDir 'writer/native-loader-result.json') -Raw | ConvertFrom-Json
$plan=Get-Content -LiteralPath (Join-Path $AttemptDir 'plan.json') -Raw | ConvertFrom-Json
if ($attempt.candidate_sha256 -cne '98a08807df84feb6c7d3cc8081a6bc92a64e5f472e0dc269bc52232e6089b126' -or
    $attempt.writer_verified -ne $false -or $attempt.helper_containment_verified -ne $true -or
    $attempt.lease_released -ne $true -or $attempt.firewall_cleanup_verified -ne $true -or
    $ram.flash_writes -ne 0 -or $native.flash_written -ne $false -or $native.native_cleanup_verified -ne $true -or
    (Test-Path -LiteralPath (Join-Path $AttemptDir 'ethernet-writer-process.stdout.log'))) {
    throw 'Exact clean pre-erase abort evidence required; no console operation performed'
}
if(Test-Path -LiteralPath $EvidenceDir){throw 'Fresh recovery evidence directory required'}
[void][IO.Directory]::CreateDirectory($EvidenceDir)
$report=[ordered]@{schema='openmitrastar.f325-preerase-normal-boot/v1';started_at_utc=[DateTime]::UtcNow.ToString('o');
    status='FAIL';flash_writes=0;boot_environment_saved=$false;boot_command_sent=$false;responses=@()}
$guard=$null;$serial=$null
function Response([string]$Stage,[string]$Command,[int]$Seconds=15,[bool]$NoCarriageReturn=$false) {
    $serial.DiscardInBuffer()
    if($NoCarriageReturn){$serial.Write($Command)}else{$serial.Write($Command+"`r")}
    $text=[Text.StringBuilder]::new();$until=[DateTime]::UtcNow.AddSeconds($Seconds)
    do {
        $chunk=$serial.ReadExisting()
        if($chunk){[void]$text.Append($chunk)}
        if($text.Length -gt 30000){throw 'Bounded console response exceeded'}
        if($text.ToString().Replace("`r","`n") -match '(?m)^topaz> *$'){break}
        Start-Sleep -Milliseconds 50
    } while([DateTime]::UtcNow -lt $until)
    $value=$text.ToString()
    $bytes=[Text.Encoding]::ASCII.GetBytes($value);$hash=[Security.Cryptography.SHA256]::Create()
    try{$digest=-join($hash.ComputeHash($bytes)|ForEach-Object{$_.ToString('x2')})}finally{$hash.Dispose()}
    $controls=@{};foreach($byte in $bytes){if($byte -lt 32 -and $byte -notin @(9,10,13)){ $key=('0x{0:x2}' -f $byte);if(-not$controls.ContainsKey($key)){$controls[$key]=0};$controls[$key]++ }}
    $promptSeen=($value.Replace("`r","`n") -match '(?m)^topaz> *$')
    $report.responses+=@{stage=$Stage;bytes=$bytes.Length;sha256=$digest;control_byte_counts=$controls;prompt_seen=$promptSeen;
        loading_seen=($value -match 'Loading:');abort_seen=($value -match '(?m)^Abort\r?$')}
    if(-not $promptSeen){throw 'Expected Bootbase prompt not observed'}
    return $value
}
try {
    $guard=Enter-F319HardwareGuard -Port 'COM3' -ExpectedPnpDeviceId $plan.uart_pnp_device_id -PhysicalLockDir $plan.physical_lock -Owner 'f325-preerase-normal-boot' -EvidenceDir $EvidenceDir
    $serial=[IO.Ports.SerialPort]::new('COM3',115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
    $serial.Handshake=[IO.Ports.Handshake]::None;$serial.DtrEnable=$false;$serial.RtsEnable=$false;$serial.ReadTimeout=500;$serial.WriteTimeout=2000
    $serial.Open()
    # A blank line repeats U-Boot's previous command, which may be tftpboot.
    # This exact pre-erase recovery may cancel only a RAM transfer; never use
    # this sequence when an erase/write has been entered or is uncertain.
    [void](Response 'interrupt-preerase-ram-wait' ([string][char]0x03) 15 $true)
    $envReply=Response 'boot-selection-read' 'printenv bootcmd bootselect'
    if($envReply -notmatch '(?m)^bootcmd=bootselect\r?$' -or $envReply -notmatch '(?m)^bootselect=([01])\r?$'){
        throw 'Normal boot selection is not the expected preserved bootselect contract'
    }
    $report.bootselect=$Matches[1]
    $report.ram_crc_observation_skipped=[bool]$SkipRamCrcObservation
    $report.ram_crc32_observed=$null;$report.ram_candidate_verified=$false
    if(-not $SkipRamCrcObservation){
        $crc=Response 'candidate-ram-crc' 'crc32 0x83000000 0x00513000' 30
        $matches=[regex]::Matches($crc,'(?i)==>\s*([0-9a-f]{8})')
        $report.ram_crc32_observed=if($matches.Count -eq 1){$matches[0].Groups[1].Value.ToLowerInvariant()}else{$null}
        $report.ram_candidate_verified=($report.ram_crc32_observed -ceq '5bf57eae')
    }
    # The guarded attempt never reached the writer. Preserve the existing
    # normal selector; do not boot the diagnostic image that is only in RAM.
    $serial.Write("boot`r")
    $drainUntil=[DateTime]::UtcNow.AddSeconds(2)
    while($serial.BytesToWrite -gt 0 -and [DateTime]::UtcNow -lt $drainUntil){Start-Sleep -Milliseconds 10}
    if($serial.BytesToWrite -ne 0){throw 'Boot command transmission not confirmed'}
    Start-Sleep -Milliseconds 100
    $report.boot_command_sent=$true;$report.status='NORMAL_BOOT_REQUESTED_UNVERIFIED'
} catch {$report.error_type=$_.Exception.GetType().Name;$report.error=$_.Exception.Message}
finally {
    if($serial){if($serial.IsOpen){$serial.Close()};$serial.Dispose()}
    if($guard){Exit-F319HardwareGuard -Guard $guard}
    $report.finished_at_utc=[DateTime]::UtcNow.ToString('o')
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $EvidenceDir 'result.json') -Encoding UTF8
}
$report | ConvertTo-Json -Depth 8
if(-not$report.boot_command_sent){exit 1}
