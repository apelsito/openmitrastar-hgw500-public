#!/bin/ash
# Load a RAM-only 2.4 GHz Realtek bundle with BE TX summary tracing enabled.

set -u
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH

root=${1:-/tmp/be-tx-summary}
release=$(uname -r)
state=/run/openmitrastar/radio2g
order=$root/LOAD_ORDER.txt
hashes=$root/SHA256SUMS

log()
{
	printf 'OM2G_BE_SUMMARY %s\n' "$*"
}

fail()
{
	log "FAIL reason=$1"
	exit 1
}

stop_radio2g_preserve_management()
{
	if [ -r "$state/hostapd.pid" ]; then
		kill "$(cat "$state/hostapd.pid")" >/dev/null 2>&1 || true
	fi
	/usr/sbin/hostapd_cli -p "$state/ctrl" -i wlan0 terminate >/dev/null 2>&1 || true
	killall hostapd >/dev/null 2>&1 || true
	sleep 1
	brctl delif br0 wlan0 >/dev/null 2>&1 || true
	ifconfig wlan0 down >/dev/null 2>&1 || true
	ifconfig br0 192.168.1.90 netmask 255.255.255.0 up >/dev/null 2>&1 || true
	route del default >/dev/null 2>&1 || true
	route add default gw 192.168.1.1 dev br0 >/dev/null 2>&1 || true
	[ -e /sys/class/net/br0/brif/eth0 ] || fail br0-lost-eth0
	log "PRESERVED_MANAGEMENT bridge=br0 eth0=present"
}

[ "$release" = 5.10.260-openmitrastar-radiohw ] || fail kernel-release
[ -r "$order" ] || fail missing-order
[ -r "$hashes" ] || fail missing-hashes
[ -x /usr/sbin/om-radio-start ] || fail missing-radio-start

(
	cd "$root" || exit 10
	while read -r expected path; do
		case "$path" in
			modules/*.ko|LOAD_ORDER.txt) ;;
			*) continue ;;
		esac
		[ -f "$path" ] || exit 11
		actual=$(sha256sum "$path" 2>/dev/null | awk '{print $1}')
		[ "$actual" = "$expected" ] || exit 12
	done <SHA256SUMS
) || fail hash-check

ins()
{
	module=$1
	params=${2:-}
	path=$root/modules/$module
	[ -f "$path" ] || fail "missing-module-$module"
	if [ -n "$params" ]; then
		insmod "$path" $params || fail "insmod-$module"
	else
		insmod "$path" || fail "insmod-$module"
	fi
	log "LOAD module=$module params=${params:-none}"
}

param_is()
{
	module=$1
	name=$2
	want=$3
	path=/sys/module/$module/parameters/$name
	[ -r "$path" ] || fail "missing-param-$module-$name"
	got=$(cat "$path" 2>/dev/null)
	[ "$got" = "$want" ] || fail "param-$module-$name-got-$got-want-$want"
}

log "START root=$root release=$release"
stop_radio2g_preserve_management

for name in rtl8192ee rtl_pci btcoexist rtlwifi mac80211 libarc4 cfg80211 cmac ccm ctr; do
	rmmod "$name" >/dev/null 2>&1 || true
done
rm -f "$state/modules-ready" "$state/modules-state"
mkdir -p "$state"

while read -r module; do
	[ -n "$module" ] || continue
	case "$module" in
		rtlwifi.ko) ins "$module" 'hgw500_tx_ampdu_disable=0 hgw500_honest_tx_ack=0' ;;
		rtl_pci.ko) ins "$module" 'hgw500_eapol_mgnt_queue=1 hgw500_tx_queue_guard=0 hgw500_tx_reclaim_poll=0 hgw500_mgmt_tx_complete_trace=0 hgw500_eapol_trace=0 hgw500_be_tx_summary=1' ;;
		rtl8192ee.ko) ins "$module" 'msi=0 dma64=0 aspm=0 ips=0 fwlps=0 swenc=1 disable_watchdog=0 debug_level=0 hgw500_force_txbd64_width=1 hgw500_tx_dma_wmb=1 hgw500_tx_page_units=2 hgw500_tx_pbp_256=0 hgw500_txbd_mgmt_split=0 hgw500_force_data_mcs7=0 hgw500_force_data_mcs15=0 hgw500_force_data_11m=0 hgw500_txbd_be_data_split=0 hgw500_tx_rate_trace=0 hgw500_tx_close_diag=0' ;;
		*) ins "$module" ;;
	esac
done <"$order"

param_is rtl_pci hgw500_be_tx_summary Y
param_is rtl_pci hgw500_eapol_mgnt_queue Y
param_is rtl_pci hgw500_eapol_trace N
param_is rtl8192ee hgw500_force_txbd64_width Y
param_is rtl8192ee hgw500_tx_dma_wmb Y
param_is rtl8192ee hgw500_tx_close_diag N
param_is rtlwifi hgw500_tx_ampdu_disable N
param_is rtlwifi hgw500_honest_tx_ack N

printf '%s\n' "$release" >"$state/modules-ready"
printf 'ready-be-tx-summary\n' >"$state/modules-state"

/usr/sbin/om-radio-start || fail radio-start
log "DONE"
exit 0
