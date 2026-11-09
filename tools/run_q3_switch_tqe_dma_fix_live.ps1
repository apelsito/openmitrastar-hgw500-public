param(
    [string]$Port = 'COM3',
    [string]$ServerIp = '192.168.1.43',
    [string]$BootClientIp = '192.168.1.200',
    [string]$SshHost = '192.168.1.90',
    [switch]$UseSshReboot,
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$boot = Join-Path $PSScriptRoot 'run_q3_maintenance_hbm_clear_v1.ps1'
$exec = Join-Path $PSScriptRoot 'ramssh_exec.py'
$upload = Join-Path $PSScriptRoot 'ramssh_upload.py'
$module = Join-Path $root 'outputs\kernel-port\qtn-switch-tqe-dma-device-fix-20260821\switch_tqe.ko'
$wrapper = Join-Path $root 'tools\ram-insmod-qtn-trace-wrapper.sh'
$expected = '368c347eac8fdf895cc4ec37c394a0a97b4c0297f892a506bf5986a21e532c74'

foreach ($path in @($boot, $exec, $upload, $module, $wrapper)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing input: $path" }
}
$actual = (Get-FileHash -LiteralPath $module -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw "switch_tqe identity mismatch expected=$expected actual=$actual" }

Write-Host "OMQTN_DMA_FIX_PREFLIGHT_PASS switch_tqe_sha256=$actual load=0x87000000 flash=0"
if (-not $Execute) { exit 0 }

# The hardware may currently be hard-stalled.  Arm Bootbase first; the human
# then performs one cold power-cycle.  This path never writes flash.
$bootArgs = @{
    Port = $Port
    ServerIp = $ServerIp
    BootClientIp = $BootClientIp
    SshHost = $SshHost
    Execute = $true
}
if ($UseSshReboot) { $bootArgs.UseSshReboot = $true }
& $boot @bootArgs
if ($LASTEXITCODE -ne 0) { throw "Q3 maintenance RAM boot failed rc=$LASTEXITCODE" }

& python $upload $module '/tmp/switch_tqe-fixed.ko' --host $SshHost --mode 0600
if ($LASTEXITCODE -ne 0) { throw 'switch_tqe upload failed' }
& python $upload $wrapper '/tmp/ram-insmod-qtn-trace-wrapper.sh' --host $SshHost --mode 0700
if ($LASTEXITCODE -ne 0) { throw 'module trace wrapper upload failed' }

$prepare = @'
set -eu
expected=368c347eac8fdf895cc4ec37c394a0a97b4c0297f892a506bf5986a21e532c74
actual=$(sha256sum /tmp/switch_tqe-fixed.ko | awk '{print $1}')
[ "$actual" = "$expected" ]
cp /tmp/switch_tqe-fixed.ko /lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/switch_tqe.ko
mv /usr/sbin/ram-insmod-qtn /usr/sbin/ram-insmod-qtn.real
cp /tmp/ram-insmod-qtn-trace-wrapper.sh /usr/sbin/ram-insmod-qtn
chmod 0700 /usr/sbin/ram-insmod-qtn /usr/sbin/ram-insmod-qtn.real
/usr/sbin/om-qtn-cal-readonly
/usr/sbin/om-qtn-mac-prepare
echo OMQTN_DMA_FIX_RUNTIME_READY switch_tqe_sha256=$actual flash=0 >/dev/console
'@
& python $exec $prepare --host $SshHost --timeout 90
if ($LASTEXITCODE -ne 0) { throw 'runtime preparation failed' }

Write-Host "OMQTN_DMA_FIX_RUNTIME_PREP_PASS host=$SshHost flash=0"
