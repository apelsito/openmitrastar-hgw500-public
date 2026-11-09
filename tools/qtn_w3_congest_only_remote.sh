#!/bin/sh
set -eu
root=${1:-/tmp/w3-qtn-congest}
gate=${2:-/tmp/W3_CONGEST_ONLY_GATE.env}
value() { sed -n "s/^$1=//p" "$gate" | head -n 1; }
stop() { code=$1; shift; echo "W3_CONGEST_STOP code=$code $*"; exit "$code"; }

test "$(value W3_CONGEST_ONLY_APPROVED)" = 1 || stop 61 reason=congest_only_not_approved
test "$(value W3_PAIR_APPROVED)" = 1 || stop 61 reason=pair_not_approved
test "$(value W3_HBM_ONLY_PROVEN)" = 1 || stop 61 reason=hbm_not_proven
test "$(value W3_HARDWARE_ACTIVE_APPROVED)" = 0 || stop 61 reason=broader_gate_must_remain_zero
test "$(uname -r)" = "$(value W3_KERNEL_RELEASE)" || stop 62 reason=kernel_mismatch
for forbidden in hbm topaz_congest_queue switch_tqe qdrv wlan gpio temp_sens temp_sensor fwt_ctrl; do
	grep -Eq "^${forbidden} " /proc/modules && stop 62 reason=dirty_state module="$forbidden"
done

rollback() {
	set +e
	rmmod topaz_congest_queue 2>/dev/null
	rmmod hbm 2>/dev/null
	for module in fwt_if switch_vlan dmautil iputil qtn_platform_support runtime_compat board_compat qtn_pm_qos_compat; do rmmod "$module" 2>/dev/null; done
	echo W3_CONGEST_ROLLBACK_COMPLETE
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
insmod "$root/hbm.ko" w3_hbm_lifecycle_enable=1
grep -Eq '^hbm ' /proc/modules || stop 63 reason=hbm_baseline_absent
echo W3_CONGEST_BASELINE_HBM_PASS

insmod "$root/topaz_congest_queue.ko"
grep -Eq '^topaz_congest_queue ' /proc/modules || stop 64 reason=congest_absent
! grep -Eq '^(switch_tqe|qdrv|wlan) ' /proc/modules || stop 64 reason=forbidden_consumer_loaded
dmesg | tail -n 120
dmesg | grep -q 'OMCGQ stage=module-ready allocation=deferred mmio=none' || stop 64 reason=lifecycle_marker_absent
echo W3_CONGEST_ONLY_LOADED
rmmod topaz_congest_queue
! grep -Eq '^topaz_congest_queue ' /proc/modules || stop 65 reason=congest_unload_failed
dmesg | grep -q 'OMCGQ stage=module-exit' || stop 65 reason=exit_marker_absent
echo W3_CONGEST_ONLY_UNLOADED
trap - EXIT INT TERM
rollback
echo W3_CONGEST_ONLY_PASS
