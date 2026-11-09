param(
    [switch]$Execute,
    [string]$OutputRoot = "outputs\f3-certification\qtn-5g-f168-txpool-probe-off"
)
$ErrorActionPreference = 'Stop'
$ack = 'OPENMITRASTAR_F151_5G_BRIDGE_TRIAL'
$qdrv = 'ed5314b5f24e6ae4f3dd07ef1efc57c68e4246c9e3fdf055657f80c5798f7f26'
$wlan = 'f4f6099b43dd675dd44e7021374f1ea2f4380a4d9d9fd81b1d35ea411984897f'
if (-not $Execute) {
    Write-Output "DRY_RUN only. This script never flashes or reboots."
    Write-Output "After the main hardware owner installs F168, run:"
    Write-Output ".\tools\run_f168_5g_physical_gate.ps1 -Execute"
    exit 0
}
1..3 | ForEach-Object {
    $out = "$OutputRoot-r$_"
    python tools\run_f151_5g_bridge_trial.py --execute --ack $ack --router-host 192.168.1.90 --seconds 300 --transfer-mib 32 --transfer-timeout-seconds 90 --disable-tx-ba --persistent-bridge --expected-qdrv-sha $qdrv --expected-wlan-sha $wlan --output-dir $out
    if ($LASTEXITCODE -ne 0) { throw "F168 physical run $_ failed" }
}
Write-Output "F168 physical runs complete. Compare medians with the F167 32 MiB baseline; do not claim improvement without all three PASS, zero disconnects/fatals/busy/GSO drops, and >=5% median throughput gain or a separately measured latency gain."
