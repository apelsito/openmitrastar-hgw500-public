param(
    [switch]$Execute,
    [string]$Ack = "",
    [Parameter(Mandatory = $true)][string]$PskFile,
    [string]$HostAddress = "192.168.1.200"
)
$ErrorActionPreference = "Stop"
$RequiredAck = "OPENMITRASTAR_COLD_IRQ28_IOSS_AP_RAM_ONLY"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Exec = Join-Path $PSScriptRoot "ramssh_exec.py"
$Upload = Join-Path $PSScriptRoot "ramssh_upload.py"
$Artifact = Join-Path $Root "outputs\kernel-port\quantenna-linux510-v89-radiohw-fwt-netss-only-20260818-0515"
$Modules = Join-Path $Artifact "rootfs\lib\modules\5.10.260-openmitrastar-radiohw\extra\quantenna\platform\ruby"
$Support = Join-Path $Modules "qtn_platform_support.ko"
$Board = Join-Path $Modules "board_compat.ko"
$RamInsmod = Join-Path $Root "outputs\kernel-port\ram-insmod-nolibc\ram_insmod_nolibc"
$SecureAp = Join-Path $PSScriptRoot "run_product_rootfs_secure_ap.ps1"
$SupportSha = "ed70993dac464372d7136a8aeaed3efef5da15450652a4bac2a1cb9ebe6bf908"
$BoardSha = "32bf0198d0a3d944f48772e2b6ecd18563a9b8eeed123981f0b17be75b0efff9"

foreach ($item in @($PskFile,$Support,$Board,$RamInsmod,$SecureAp)) {
    if (-not (Test-Path -LiteralPath $item -PathType Leaf)) { throw "Missing input: $item" }
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $Support).Hash.ToLowerInvariant() -ne $SupportSha) { throw "support hash mismatch" }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $Board).Hash.ToLowerInvariant() -ne $BoardSha) { throw "board hash mismatch" }

[ordered]@{
    schema = "openmitrastar.cold-irq28-ioss-ap/v1"
    mode = if($Execute){"EXECUTE_RAM"}else{"DRY_RUN"}
    logical_date = "2026-08-18"
    order = @("cold product boot", "RTL bound irq28", "IOSS-only pulse 0x20", "FWT state3", "secure AP", "IRQ28 progress")
    flash = $false
} | ConvertTo-Json -Depth 4
if(-not $Execute){"OM_COLD_IRQ28_IOSS_AP_DRY_RUN_PASS=1";exit 0}
if($Ack -cne $RequiredAck){throw "Execution requires -Ack $RequiredAck"}

function Remote([string]$Command,[int]$Timeout=30){
    $psi=[Diagnostics.ProcessStartInfo]::new()
    $psi.FileName="python.exe"
    $psi.UseShellExecute=$false
    $psi.RedirectStandardOutput=$true
    $psi.RedirectStandardError=$true
    foreach($arg in @($Exec,"--host",$HostAddress,"--timeout","$Timeout",$Command)){
        [void]$psi.ArgumentList.Add($arg)
    }
    $proc=[Diagnostics.Process]::Start($psi)
    if(-not $proc.WaitForExit($Timeout*1000)){$proc.Kill($true);throw "remote timeout"}
    $stdout=$proc.StandardOutput.ReadToEnd()
    $stderr=$proc.StandardError.ReadToEnd()
    if($proc.ExitCode){throw "remote failed: $stderr $stdout"}
    return $stdout.TrimEnd()
}

$pre=Remote 'echo IRQ_SYSFS=$(cat /sys/bus/pci/devices/0000:00:00.0/irq); grep -E "^ 28:|^28:" /proc/interrupts; grep -E "^rtl_pci " /proc/modules'
if($pre -notmatch 'IRQ_SYSFS=28' -or $pre -notmatch 'rtl_pci'){throw "cold RTL IRQ28 precondition failed: $pre"}
Remote 'rm -rf /tmp/om-ioss-final; mkdir -p /tmp/om-ioss-final' | Out-Null
& python $Upload $Support /tmp/om-ioss-final/qtn_platform_support.ko --host $HostAddress --mode 0600 | Out-Null
if($LASTEXITCODE){throw "support upload failed"}
& python $Upload $Board /tmp/om-ioss-final/board_compat.ko --host $HostAddress --mode 0600 | Out-Null
if($LASTEXITCODE){throw "board upload failed"}
& python $Upload $RamInsmod /tmp/om-ioss-final/ram_insmod --host $HostAddress --mode 0700 | Out-Null
if($LASTEXITCODE){throw "ram_insmod upload failed"}

$pulse=Remote '/tmp/om-ioss-final/ram_insmod /tmp/om-ioss-final/qtn_platform_support.ko; /tmp/om-ioss-final/ram_insmod /tmp/om-ioss-final/board_compat.ko "board_id=65535 emac0=1 emac1=1 wifi_hw=7 rfic=4 calstate=3 ext_lna_gain=12 ext_lna_bypass_gain=-5 tx_power_cal=0 min_tx_power=7 max_tx_power=21 allow_dram_sram_fallback=0 w3_fwt_ioss_only_probe_enable=1"; dmesg | grep -E "OMFWT1B target=ioss stage=(released|arbitration|complete)" | tail -n 8' 45
if($pulse -notmatch 'target=ioss stage=complete rc=0' -or $pulse -notmatch 'post_state=3'){throw "IOSS/FWT gate failed: $pulse"}
$post=Remote 'echo IRQ_SYSFS=$(cat /sys/bus/pci/devices/0000:00:00.0/irq); grep -E "^ 28:|^28:" /proc/interrupts'
if($post -notmatch 'IRQ_SYSFS=28'){throw "IRQ28 lost after IOSS: $post"}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SecureAp -ExecuteRam `
    -AckRamOnly OPENMITRASTAR_PRODUCT_SECURE_AP_RAM_ONLY -PskFile ([IO.Path]::GetFullPath($PskFile)) `
    -HostAddress $HostAddress -TimeoutSeconds 90
if($LASTEXITCODE){throw "secure AP failed after IOSS"}

$progress=Remote 'a=$(awk ''$1=="28:"{print $2}'' /proc/interrupts); sleep 3; b=$(awk ''$1=="28:"{print $2}'' /proc/interrupts); echo IRQ28_BEFORE=$a; echo IRQ28_AFTER=$b; /usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status 2>/dev/null | grep -E "^(state|ssid)"' 20
if($progress -notmatch 'state=ENABLED'){throw "AP not enabled: $progress"}
$before=[int]([regex]::Match($progress,'IRQ28_BEFORE=(\d+)').Groups[1].Value)
$after=[int]([regex]::Match($progress,'IRQ28_AFTER=(\d+)').Groups[1].Value)
if($after -le $before){throw "IRQ28 did not progress: $progress"}
Write-Output $progress
Write-Output "OM_COLD_IRQ28_IOSS_AP_PASS=1 fwt=GRANTED irq28=PROGRESS ap=ENABLED flash=0"
