#!/bin/sh
set -eu

if [ "${1:-}" != "--worker" ]; then
	root=${1:-/tmp/w3-qtn-fwt-ni}
	gate=${2:-/tmp/W3_FWT_NETSS_IOSS_PROBE_GATE.env}
	result=/tmp/W3_FWT_NETSS_IOSS_PROBE.worker.log
	rm -f "$result"
	(
		trap '' HUP
		exec sh "$0" --worker "$root" "$gate"
	) >"$result" 2>&1 </dev/null &
	echo "W3_FWT_NI_DETACHED pid=$! result=$result"
	exit 0
fi

root=${2:-/tmp/w3-qtn-fwt-ni}
gate=${3:-/tmp/W3_FWT_NETSS_IOSS_PROBE_GATE.env}

value()
{
	sed -n "s/^$1=//p" "$gate" | head -n1
}

stop()
{
	code=$1
	shift
	echo "W3_FWT_NI_STOP code=$code $*"
	exit "$code"
}

test "$(value W3_FWT_NETSS_IOSS_PROBE_APPROVED)" = 1 || stop 141 reason=not_approved
test "$(value W3_PAIR_APPROVED)" = 1 || stop 141 reason=pair_not_approved
test "$(value W3_FWT_RXP_HYPOTHESIS_REJECTED)" = 1 || stop 141 reason=rxp_not_closed
test "$(value W3_HARDWARE_ACTIVE_APPROVED)" = 0 || stop 141 reason=broader_gate
test "$(value W3_FWT_TABLE_ACCESS_ALLOWED)" = 0 || stop 141 reason=table_access_not_forbidden
test "$(value W3_RESET_PULSE_MASK)" = 0x000000a0 || stop 141 reason=wrong_pulse_mask
test "$(value W3_RESET_WAIT_MS)" = 50 || stop 141 reason=wrong_wait
test "$(value W3_ENET0_RESET_ALLOWED)" = 0 || stop 141 reason=enet0_not_forbidden
test "$(value W3_OTHER_MMIO_WRITES_ALLOWED)" = 0 || stop 141 reason=other_mmio_not_forbidden

for module in qtn_platform_support board_compat hbm topaz_congest_queue switch_tqe fwt_ctrl qdrv wlan; do
	grep -Eq "^$module " /proc/modules && stop 142 reason=dirty module="$module"
done

rollback()
{
	set +e
	rmmod board_compat 2>/dev/null
	rmmod qtn_platform_support 2>/dev/null
	echo W3_FWT_NI_ROLLBACK_COMPLETE
}
trap rollback EXIT INT TERM

"$root/ram_insmod" "$root/qtn_platform_support.ko"
"$root/ram_insmod" "$root/board_compat.ko" \
	"board_id=65535 emac0=1 emac1=1 wifi_hw=7 rfic=4 calstate=3 ext_lna_gain=12 ext_lna_bypass_gain=-5 tx_power_cal=0 min_tx_power=7 max_tx_power=21 allow_dram_sram_fallback=0 w3_fwt_netss_ioss_pulse_probe_enable=1"

grep -Eq '^board_compat ' /proc/modules || stop 143 reason=probe_module_absent
for marker in \
	'OMFWTNI stage=gate-pass target=mitrastar,hgw-500bna-qcv2' \
	'OMFWTNI stage=snapshot vec=' \
	'OMFWTNI stage=asserted vec=' \
	'OMFWTNI stage=released vec=' \
	'OMFWTNI stage=arbitration pre_raw=' \
	'OMFWTNI stage=arbitration-released raw=' \
	'OMFWTNI stage=complete rc='; do
	dmesg | grep -q "$marker" || stop 143 reason=marker_absent marker="$marker"
done
dmesg | grep 'OMFWTNI stage=released' | grep -q 'vec_restored=1 mask_cleared=1' || \
	stop 143 reason=reset_restore_failed

! grep -Eq '^(hbm|topaz_congest_queue|switch_tqe|fwt_ctrl|qdrv|wlan) ' /proc/modules || \
	stop 143 reason=forbidden_module_loaded
! dmesg | grep -q 'OMFWT stage=table-cleared-hash-enabled' || \
	stop 143 reason=unexpected_fwt_write
! dmesg | grep -q 'OMTQE stage=ring-programmed' || \
	stop 143 reason=unexpected_tqe_ring

dmesg | tail -n 180
rmmod board_compat
rmmod qtn_platform_support

trap - EXIT INT TERM
rollback
echo W3_FWT_NETSS_IOSS_PROBE_PASS
