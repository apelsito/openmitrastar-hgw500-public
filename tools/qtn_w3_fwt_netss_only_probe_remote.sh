#!/bin/sh
set -eu

if [ "${1:-}" != "--worker" ]; then
	root=${1:-/tmp/w3-qtn-fwt-n80}
	gate=${2:-/tmp/W3_FWT_NETSS_ONLY_PROBE_GATE.env}
	result=/tmp/W3_FWT_NETSS_ONLY_PROBE.worker.log
	rm -f "$result"
	( trap '' HUP; exec sh "$0" --worker "$root" "$gate" ) >"$result" 2>&1 </dev/null &
	echo "W3_FWT_NETSS_ONLY_DETACHED pid=$! result=$result"
	exit 0
fi

root=${2:-/tmp/w3-qtn-fwt-n80}
gate=${3:-/tmp/W3_FWT_NETSS_ONLY_PROBE_GATE.env}
value(){ sed -n "s/^$1=//p" "$gate" | head -n1; }
stop(){ code=$1; shift; echo "W3_FWT_NETSS_ONLY_STOP code=$code $*"; exit "$code"; }

test "$(value W3_FWT_NETSS_ONLY_PROBE_APPROVED)" = 1 || stop 151 reason=not_approved
test "$(value W3_PAIR_APPROVED)" = 1 || stop 151 reason=pair_not_approved
test "$(value W3_HARDWARE_ACTIVE_APPROVED)" = 0 || stop 151 reason=broader_gate
test "$(value W3_RESET_PULSE_MASK)" = 0x00000080 || stop 151 reason=wrong_mask
test "$(value W3_WAIT_MS)" = 50 || stop 151 reason=wrong_wait
test "$(value W3_IOSS_WRITE_ALLOWED)" = 0 || stop 151 reason=ioss_not_forbidden
test "$(value W3_ENET0_RESET_ALLOWED)" = 0 || stop 151 reason=enet0_not_forbidden
test "$(value W3_FWT_TABLE_ACCESS_ALLOWED)" = 0 || stop 151 reason=table_not_forbidden
test "$(uname -r)" = "$(value W3_KERNEL_RELEASE)" || stop 152 reason=kernel_mismatch

for module in qtn_platform_support board_compat hbm switch_tqe fwt_ctrl qdrv wlan; do
	grep -Eq "^$module " /proc/modules && stop 152 reason=dirty module="$module"
done

rollback(){ set +e; rmmod board_compat 2>/dev/null; rmmod qtn_platform_support 2>/dev/null; echo W3_FWT_NETSS_ONLY_ROLLBACK_COMPLETE; }
trap rollback EXIT INT TERM

"$root/ram_insmod" "$root/qtn_platform_support.ko"
"$root/ram_insmod" "$root/board_compat.ko" \
	"board_id=65535 emac0=1 emac1=1 wifi_hw=7 rfic=4 calstate=3 ext_lna_gain=12 ext_lna_bypass_gain=-5 tx_power_cal=0 min_tx_power=7 max_tx_power=21 allow_dram_sram_fallback=0 w3_fwt_netss_only_probe_enable=1"

for marker in \
	'OMFWTPROBE stage=gate-pass target=mitrastar,hgw-500bna-qcv2' \
	'OMFWT1B target=netss stage=snapshot' \
	'OMFWT1B target=netss stage=asserted' \
	'OMFWT1B target=netss stage=released' \
	'OMFWT1B target=netss stage=arbitration' \
	'OMFWT1B target=netss stage=arbitration-released' \
	'OMFWT1B target=netss stage=complete'; do
	dmesg | grep -q "$marker" || stop 153 reason=marker_absent marker="$marker"
done
dmesg | grep 'OMFWT1B target=netss stage=released' | grep -q 'vec_restored=1 mask_restored=1' || stop 153 reason=restore_failed
! dmesg | grep -q 'OMFWT stage=table-cleared-hash-enabled' || stop 153 reason=unexpected_fwt_write
dmesg | tail -n 180
echo W3_FWT_NETSS_ONLY_PROBE_PASS
