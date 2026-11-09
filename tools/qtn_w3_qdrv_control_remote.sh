#!/bin/sh
set -eu

root=${1:-/tmp/w3-qdrv-control}
gate=${2:-/tmp/W3_QDRV_CONTROL_GATE.env}
switch_state=/run/openmitrastar/switch-emac-handoff/status

value() { sed -n "s/^$1=//p" "$gate" | head -n 1; }
stop() { code=$1; shift; echo "W3_QDRV_CONTROL_STOP code=$code $*" >/dev/console; exit "$code"; }
load() { file=$1; shift; "$root/ram_insmod" "$root/$file" "$*"; }
rollback()
{
	set +e
	rmmod qdrv 2>/dev/null
	rmmod wlan 2>/dev/null
	rmmod temp_sens 2>/dev/null
	rmmod temp_sensor 2>/dev/null
	rmmod gpio 2>/dev/null
	echo "W3_QDRV_CONTROL stage=rollback-complete" >/dev/console
}
trap 'rollback' 0 2 15

test "$(value W3_QDRV_CONTROL_APPROVED)" = 1 || stop 101 reason=not_approved
test "$(value W3_QDRV_CONTROL_ONLY)" = 1 || stop 101 reason=not_control_only
test "$(value W3_RF_ENABLE)" = 0 || stop 101 reason=rf_gate_open
stop_after_wlan=$(value W3_QDRV_STOP_AFTER_WLAN)
test "$stop_after_wlan" = 0 || test "$stop_after_wlan" = 1 || stop 101 reason=stage_gate_invalid
test "$(uname -r)" = "$(value W3_KERNEL_RELEASE)" || stop 102 reason=kernel_mismatch
grep -aq "$(value W3_TARGET_COMPATIBLE)" /proc/device-tree/compatible || stop 102 reason=target_mismatch
test "$(cat "$switch_state" 2>/dev/null)" = "$(value W3_SWITCH_HANDOFF_STATUS)" || stop 102 reason=switch_not_committed
test -e /sys/class/net/br0/brif/eth1_emac1 || stop 102 reason=management_emac_missing
test ! -e /sys/class/net/br0/brif/tqe || stop 102 reason=tqe_in_bridge
grep -q '^switch_emac ' /proc/modules || stop 102 reason=switch_module_absent
for dirty in qdrv wlan temp_sensor temp_sens; do
	grep -Eq "^${dirty} " /proc/modules && stop 102 reason=dirty_module module="$dirty"
done

if grep -Eq '^gpio ' /proc/modules; then
	echo "W3_QDRV_CONTROL stage=module-preloaded module=gpio" >/dev/console
else
	load gpio.ko
fi
echo "W3_QDRV_CONTROL stage=load-enter module=temp_sensor" >/dev/console
load temp_sensor.ko
echo "W3_QDRV_CONTROL stage=load-pass module=temp_sensor" >/dev/console
echo "W3_QDRV_CONTROL stage=load-enter module=temp_sens" >/dev/console
load temp_sens.ko
echo "W3_QDRV_CONTROL stage=load-pass module=temp_sens" >/dev/console
echo "W3_QDRV_CONTROL stage=load-enter module=wlan" >/dev/console
load wlan.ko
echo "W3_QDRV_CONTROL stage=load-pass module=wlan" >/dev/console
if [ "$stop_after_wlan" = 1 ]; then
	rmmod wlan
	rmmod temp_sens
	rmmod temp_sensor
	trap - 0 2 15
	echo "W3_QDRV_WLAN_ONLY_EXPERIMENT_PASS=1"
	exit 0
fi
echo "W3_QDRV_CONTROL stage=load-enter module=qdrv" >/dev/console
load qdrv.ko tqe_sem_en=1
echo "W3_QDRV_CONTROL stage=load-pass module=qdrv" >/dev/console
test -e /sys/devices/qdrv/control || stop 103 reason=control_absent
test -e /sys/devices/qdrv/panic_on_muc_halt || stop 103 reason=panic_control_absent
echo 0 >/sys/devices/qdrv/panic_on_muc_halt
test "$(cat /sys/devices/qdrv/panic_on_muc_halt)" = 0 || stop 103 reason=panic_control_readback
control=$(cat /sys/devices/qdrv/control 2>/dev/null || true)
echo "W3_QDRV_CONTROL stage=control-ready qdrv_loaded=1 rf=blocked control_bytes=${#control}" >/dev/console
trap - 0 2 15
echo "W3_QDRV_CONTROL_EXPERIMENT_PASS=1"
