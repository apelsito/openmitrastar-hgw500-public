#!/bin/sh
set -eu

root=${1:-/tmp/w3-qtn-fwt-reset}
gate=${2:-/tmp/W3_FWT_RESET_PROBE_GATE.env}

value()
{
	sed -n "s/^$1=//p" "$gate" | head -n1
}

stop()
{
	code=$1
	shift
	echo "W3_FWT_RESET_STOP code=$code $*"
	exit "$code"
}

test "$(value W3_FWT_RESET_PROBE_APPROVED)" = 1 || stop 121 reason=not_approved
test "$(value W3_PAIR_APPROVED)" = 1 || stop 121 reason=pair_not_approved
test "$(value W3_SWITCH_TQE_DRAMLAB_PROVEN)" = 1 || stop 121 reason=switch_not_proven
test "$(value W3_HARDWARE_ACTIVE_APPROVED)" = 0 || stop 121 reason=broader_gate
test "$(value W3_FWT_TABLE_ACCESS_ALLOWED)" = 0 || stop 121 reason=table_access_not_forbidden

for module in hbm topaz_congest_queue switch_tqe fwt_ctrl qdrv wlan; do
	grep -Eq "^$module " /proc/modules && stop 122 reason=dirty module="$module"
done

rollback()
{
	set +e
	rmmod switch_tqe 2>/dev/null
	rmmod topaz_congest_queue 2>/dev/null
	rmmod hbm 2>/dev/null
	for module in fwt_if switch_vlan dmautil iputil qtn_platform_support \
		runtime_compat board_compat qtn_pm_qos_compat; do
		rmmod "$module" 2>/dev/null
	done
	echo W3_FWT_RESET_ROLLBACK_COMPLETE
}
trap rollback EXIT INT TERM

load()
{
	module=$1
	shift
	if [ "$#" -gt 0 ]; then
		"$root/ram_insmod" "$root/$module" "$*"
	else
		"$root/ram_insmod" "$root/$module"
	fi
}

load qtn_pm_qos_compat.ko
load board_compat.ko board_id=65535 emac0=1 emac1=1 wifi_hw=7 rfic=4 calstate=3 ext_lna_gain=12 ext_lna_bypass_gain=-5 tx_power_cal=0 min_tx_power=7 max_tx_power=21 allow_dram_sram_fallback=1
load runtime_compat.ko
load qtn_platform_support.ko
load iputil.ko
load dmautil.ko
load switch_vlan.ko
load fwt_if.ko
load hbm.ko w3_hbm_lifecycle_enable=1
load topaz_congest_queue.ko
load switch_tqe.ko w3_switch_tqe_only_enable=1 w3_fwt_reset_probe_enable=1

grep -Eq '^switch_tqe ' /proc/modules || stop 123 reason=switch_probe_absent
for marker in \
	'OMFWTRESET stage=pre-reset cpu_vec_raw=' \
	'OMFWTRESET stage=pre-reset released_raw=' \
	'OMFWTRESET stage=post-reset cpu_vec_raw=' \
	'OMFWTRESET stage=post-reset released_raw='; do
	dmesg | grep -q "$marker" || stop 123 reason=marker_absent marker="$marker"
done
for field in cpu_vec_mask_raw pre_raw pre_state pre_req rc post_raw post_state post_req; do
	dmesg | grep 'OMFWTRESET stage=pre-reset cpu_vec_raw=' | grep -q "$field=" || \
		stop 123 reason=field_absent stage=pre-reset field="$field"
	dmesg | grep 'OMFWTRESET stage=post-reset cpu_vec_raw=' | grep -q "$field=" || \
		stop 123 reason=field_absent stage=post-reset field="$field"
done
for field in released_state released_req; do
	dmesg | grep 'OMFWTRESET stage=pre-reset released_raw=' | grep -q "$field=" || \
		stop 123 reason=field_absent stage=pre-reset field="$field"
	dmesg | grep 'OMFWTRESET stage=post-reset released_raw=' | grep -q "$field=" || \
		stop 123 reason=field_absent stage=post-reset field="$field"
done

! grep -Eq '^(fwt_ctrl|qdrv|wlan) ' /proc/modules || stop 123 reason=forbidden_loaded
! dmesg | grep -q 'OMFWT stage=table-cleared-hash-enabled' || stop 123 reason=unexpected_fwt_write
! dmesg | grep -q 'OMFWT stage=hooks-registered' || stop 123 reason=unexpected_hooks

dmesg | tail -n 240
rmmod switch_tqe
dmesg | grep -q 'OMTQE stage=exit-complete' || stop 124 reason=exit_marker_absent

trap - EXIT INT TERM
rollback
echo W3_FWT_RESET_PROBE_PASS
