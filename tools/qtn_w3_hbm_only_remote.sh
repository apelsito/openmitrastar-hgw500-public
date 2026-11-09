#!/bin/sh
set -eu

root=${1:-/tmp/w3-qtn-hbm}
gate=${2:-/tmp/W3_HBM_ONLY_GATE.env}

value() { sed -n "s/^$1=//p" "$gate" | head -n 1; }
stop() { code=$1; shift; echo "W3_HBM_STOP code=$code $*"; exit "$code"; }

test "$(value W3_HBM_ONLY_APPROVED)" = 1 || stop 51 reason=hbm_only_not_approved
test "$(value W3_PAIR_APPROVED)" = 1 || stop 51 reason=pair_not_approved
test "$(value W3_HARDWARE_ACTIVE_APPROVED)" = 0 || stop 51 reason=broader_hardware_gate_must_remain_zero
test "$(uname -r)" = "$(value W3_KERNEL_RELEASE)" || stop 52 reason=kernel_release_mismatch

for forbidden in hbm switch_tqe qdrv wlan gpio temp_sens temp_sensor fwt_ctrl; do
	grep -Eq "^${forbidden} " /proc/modules && stop 52 reason=dirty_state module="$forbidden"
done

rollback()
{
	set +e
	rmmod hbm 2>/dev/null
	for module in fwt_if switch_vlan dmautil iputil qtn_platform_support runtime_compat board_compat qtn_pm_qos_compat; do
		rmmod "$module" 2>/dev/null
	done
	echo W3_HBM_ROLLBACK_COMPLETE
}
trap rollback EXIT INT TERM

insmod "$root/qtn_pm_qos_compat.ko"
insmod "$root/board_compat.ko" board_id=65535 emac0=1 emac1=1 wifi_hw=7 rfic=4 calstate=3 ext_lna_gain=12 ext_lna_bypass_gain=-5 tx_power_cal=0 min_tx_power=7 max_tx_power=21 allow_dram_sram_fallback=0
insmod "$root/runtime_compat.ko"
insmod "$root/qtn_platform_support.ko"
insmod "$root/iputil.ko"
insmod "$root/dmautil.ko"
insmod "$root/switch_vlan.ko"
insmod "$root/fwt_if.ko"

echo W3_HBM_ONLY_PRE modules="$(awk '{ printf "%s,", $1 }' /proc/modules)"
dmesg | tail -n 80
insmod "$root/hbm.ko" w3_hbm_lifecycle_enable=1
grep -Eq '^hbm ' /proc/modules || stop 53 reason=hbm_absent_after_insmod
echo W3_HBM_ONLY_LOADED
cat /proc/modules | grep -E '^(hbm|qtn_pm_qos_compat|board_compat|runtime_compat|qtn_platform_support|iputil|dmautil|switch_vlan|fwt_if) '
dmesg | tail -n 120
rmmod hbm
! grep -Eq '^hbm ' /proc/modules || stop 54 reason=hbm_failed_to_unload
echo W3_HBM_ONLY_UNLOADED
trap - EXIT INT TERM
rollback
echo W3_HBM_ONLY_PASS
