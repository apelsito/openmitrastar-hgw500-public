#!/bin/ash
# Reversible HGW500 2.4 GHz module reload using installed F5 rootfs modules.
# Actions:
#   speed    - keep the working WPA2/all64 fixes, disable heavy diagnostics
#   noampdu  - speed profile plus TX A-MPDU disabled
#   honest   - speed profile plus no fabricated TX ACK status
#   mcs15    - speed profile plus force unicast data descriptors to MCS15
#   mcs7     - speed profile plus force unicast data descriptors to MCS7
#   legacy11 - speed profile plus force unicast data descriptors to 11 Mbps CCK
#   diag     - restore the current F5 diagnostic profile

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
	printf 'OM2G_SPEED_PROFILE %s\n' "$*"
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
[ "$action" = speed ] || [ "$action" = noampdu ] || [ "$action" = honest ] || \
	[ "$action" = mcs15 ] || [ "$action" = mcs7 ] || \
	[ "$action" = legacy11 ] || [ "$action" = diag ] || fail action
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

rtl_pci_params='hgw500_eapol_mgnt_queue=1 hgw500_tx_queue_guard=0 hgw500_tx_reclaim_poll=0 hgw500_mgmt_tx_complete_trace=0'
rtl8192ee_params='msi=0 dma64=0 aspm=0 ips=0 fwlps=0 swenc=1 disable_watchdog=0 debug_level=0 hgw500_force_txbd64_width=1 hgw500_tx_dma_wmb=1 hgw500_tx_page_units=2 hgw500_tx_pbp_256=0 hgw500_txbd_mgmt_split=0 hgw500_force_data_mcs7=0 hgw500_force_data_mcs15=0 hgw500_force_data_11m=0 hgw500_txbd_be_data_split=0 hgw500_tx_rate_trace=0 hgw500_oem_tx_report=0'

if [ "$action" = diag ]; then
	rtl_pci_params="$rtl_pci_params hgw500_eapol_trace=1"
	rtl8192ee_params="$rtl8192ee_params hgw500_tx_close_diag=1"
else
	rtl_pci_params="$rtl_pci_params hgw500_eapol_trace=0"
	rtl8192ee_params="$rtl8192ee_params hgw500_tx_close_diag=0"
fi
if [ "$action" = mcs15 ]; then
	rtl8192ee_params="$rtl8192ee_params hgw500_force_data_mcs15=1"
elif [ "$action" = mcs7 ]; then
	rtl8192ee_params="$rtl8192ee_params hgw500_force_data_mcs7=1"
elif [ "$action" = legacy11 ]; then
	rtl8192ee_params="$rtl8192ee_params hgw500_force_data_11m=1"
fi

while read -r module; do
	[ -n "$module" ] || continue
	case "$module" in
		rtlwifi.ko)
			if [ "$action" = noampdu ]; then
				ins "$module" 'hgw500_tx_ampdu_disable=1 hgw500_honest_tx_ack=0'
			elif [ "$action" = honest ]; then
				ins "$module" 'hgw500_tx_ampdu_disable=0 hgw500_honest_tx_ack=1'
			else
				ins "$module" 'hgw500_tx_ampdu_disable=0 hgw500_honest_tx_ack=0'
			fi
			;;
		rtl_pci.ko) ins "$module" "$rtl_pci_params" ;;
		rtl8192ee.ko) ins "$module" "$rtl8192ee_params" ;;
		*) ins "$module" ;;
	esac
done <"$order"

param_is rtl_pci hgw500_eapol_mgnt_queue Y
param_is rtl_pci hgw500_eapol_trace "$([ "$action" = diag ] && echo Y || echo N)"
param_is rtl_pci hgw500_mgmt_tx_complete_trace N
param_is rtl_pci hgw500_tx_queue_guard N
param_is rtl_pci hgw500_tx_reclaim_poll N
param_is rtl8192ee hgw500_force_txbd64_width Y
param_is rtl8192ee hgw500_tx_dma_wmb Y
param_is rtl8192ee hgw500_tx_page_units 2
param_is rtl8192ee hgw500_tx_close_diag "$([ "$action" = diag ] && echo Y || echo N)"
param_is rtl8192ee hgw500_tx_rate_trace N
param_is rtl8192ee hgw500_oem_tx_report N
param_is rtl8192ee hgw500_force_data_mcs15 "$([ "$action" = mcs15 ] && echo Y || echo N)"
param_is rtl8192ee hgw500_force_data_mcs7 "$([ "$action" = mcs7 ] && echo Y || echo N)"
param_is rtl8192ee hgw500_force_data_11m "$([ "$action" = legacy11 ] && echo Y || echo N)"
param_is rtl8192ee hgw500_txbd_be_data_split N
param_is rtlwifi hgw500_tx_ampdu_disable "$([ "$action" = noampdu ] && echo Y || echo N)"
param_is rtlwifi hgw500_honest_tx_ack "$([ "$action" = honest ] && echo Y || echo N)"

printf '%s\n' "$release" >"$state/modules-ready"
printf 'ready-speed-profile-%s\n' "$action" >"$state/modules-state"

/usr/sbin/om-radio-start || fail radio-start
log "DONE action=$action"
exit 0
