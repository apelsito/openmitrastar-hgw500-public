#!/bin/ash
# Reversible HGW500 2.4 GHz module reload using installed F5 rootfs modules.
# Actions:
#   apply   - enable BE queue guard + reclaim poll on top of the current all64 profile
#   restore - restore the current F5 all64/eapol-mgntq profile

set -u
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH

action=${1:-}
release=$(uname -r)
base=/lib/modules/$release/openmitrastar/radio2g
state=/run/openmitrastar/radio2g
order=/usr/share/openmitrastar/radio2g/modules.order
hashes=/usr/share/openmitrastar/radio2g/artifacts.sha256

log()
{
	printf 'OM2G_QGUARD %s\n' "$*"
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
[ "$action" = apply ] || [ "$action" = restore ] || fail action
[ -r "$order" ] || fail missing-order
[ -r "$hashes" ] || fail missing-hashes
[ -x /usr/sbin/om-radio-start ] || fail missing-radio-start

while read -r expected path; do
	[ -n "${expected:-}" ] || continue
	target=$path
	[ -f "$target" ] || fail missing-artifact
	actual=$(sha256sum "$target" 2>/dev/null | awk '{print $1}')
	[ "$actual" = "$expected" ] || fail hash-mismatch
done <"$hashes"

ins()
{
	module=$1
	params=${2:-}
	path=$base/$module
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

log "START action=$action release=$release"
stop_radio2g_preserve_management

for name in rtl8192ee rtl_pci btcoexist rtlwifi mac80211 libarc4 cfg80211 cmac ccm ctr; do
	rmmod "$name" >/dev/null 2>&1 || true
done
rm -f "$state/modules-ready" "$state/modules-state"
mkdir -p "$state"

rtl_pci_params='hgw500_eapol_trace=1 hgw500_eapol_mgnt_queue=1'
if [ "$action" = apply ]; then
	rtl_pci_params="$rtl_pci_params hgw500_tx_queue_guard=1 hgw500_tx_queue_guard_high=16 hgw500_tx_queue_guard_low=8 hgw500_tx_reclaim_poll=1"
fi

rtl8192ee_params='msi=0 dma64=0 aspm=0 ips=0 fwlps=0 swenc=1 disable_watchdog=0 debug_level=0 hgw500_force_txbd64_width=1 hgw500_tx_dma_wmb=1 hgw500_tx_close_diag=1 hgw500_tx_page_units=2 hgw500_tx_pbp_256=0 hgw500_txbd_mgmt_split=0 hgw500_force_data_mcs7=0 hgw500_force_data_mcs15=0 hgw500_force_data_11m=0 hgw500_txbd_be_data_split=0 hgw500_tx_rate_trace=0'

while read -r module; do
	[ -n "$module" ] || continue
	case "$module" in
		rtlwifi.ko) ins "$module" 'hgw500_tx_ampdu_disable=0 hgw500_honest_tx_ack=0' ;;
		rtl_pci.ko) ins "$module" "$rtl_pci_params" ;;
		rtl8192ee.ko) ins "$module" "$rtl8192ee_params" ;;
		*) ins "$module" ;;
	esac
done <"$order"

param_is rtl_pci hgw500_eapol_trace Y
param_is rtl_pci hgw500_eapol_mgnt_queue Y
if [ "$action" = apply ]; then
	param_is rtl_pci hgw500_tx_queue_guard Y
	param_is rtl_pci hgw500_tx_queue_guard_high 16
	param_is rtl_pci hgw500_tx_queue_guard_low 8
	param_is rtl_pci hgw500_tx_reclaim_poll Y
else
	param_is rtl_pci hgw500_tx_queue_guard N
	param_is rtl_pci hgw500_tx_reclaim_poll N
fi
param_is rtl8192ee hgw500_force_txbd64_width Y
param_is rtl8192ee hgw500_txbd_be_data_split N

printf '%s\n' "$release" >"$state/modules-ready"
printf 'ready-%s\n' "$action" >"$state/modules-state"

/usr/sbin/om-radio-start || fail radio-start
log "DONE action=$action"
exit 0
