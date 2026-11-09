#!/bin/ash
set -eu
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH

[ "${1:-}" = OPENMITRASTAR_W2_TX3_RAM_ONLY ] || exit 171
bundle=${2:-/tmp/openmitrastar-w2-tx3}
release=5.10.260-openmitrastar-radiohw
base=/lib/modules/$release/openmitrastar/radio2g
state=/run/openmitrastar/radio2g
loader="$bundle/ram_insmod"
changed=0

log() { printf '%s\n' "$*" >/dev/console 2>/dev/null || printf '%s\n' "$*"; }

load_bundle()
{
	"$loader" "$@"
}

load_base()
{
	"$loader" "$@"
}

stop_ap()
{
	/usr/sbin/hostapd_cli -p "$state/ctrl" -i wlan0 terminate >/dev/null 2>&1 || true
	[ ! -r "$state/hostapd.pid" ] || kill "$(cat "$state/hostapd.pid")" >/dev/null 2>&1 || true
	sleep 1
	brctl delif br0 wlan0 >/dev/null 2>&1 || true
	ifconfig wlan0 down >/dev/null 2>&1 || true
	rm -f "$state/hostapd.pid" "$state/modules-ready"
}

unload_wifi()
{
	for module in rtl8192ee rtl_pci btcoexist rtlwifi mac80211 cfg80211; do
		grep -q "^$module " /proc/modules 2>/dev/null || continue
		rmmod "$module" || return 1
	done
}

start_diag()
{
	ifconfig wlan0 down || return 1
	/usr/sbin/iw dev wlan0 set type __ap || return 1
	ifconfig wlan0 0.0.0.0 up || return 1
	[ -e /sys/class/net/br0/brif/wlan0 ] || brctl addif br0 wlan0 || return 1
	rm -rf "$state/ctrl"
	mkdir -p "$state/ctrl"
	/usr/sbin/hostapd -f "$state/hostapd.log" "$state/hostapd.conf" >/dev/null 2>&1 &
	printf '%s\n' "$!" >"$state/hostapd.pid"
	attempt=0
	while [ "$attempt" -lt 30 ]; do
		/usr/sbin/hostapd_cli -p "$state/ctrl" -i wlan0 status 2>/dev/null | grep -q '^state=ENABLED$' && return 0
		attempt=$((attempt + 1))
		sleep 1
	done
	return 1
}

rollback()
{
	[ "$changed" = 1 ] || return 0
	log 'OMW2_TX3_ROLLBACK_BEGIN source=installed-rootfs'
	stop_ap
	unload_wifi >/dev/null 2>&1 || true
	for module in cfg80211 libarc4 mac80211; do
		grep -q "^$module " /proc/modules 2>/dev/null || load_base "$base/$module.ko" || return 1
	done
	load_base "$base/rtlwifi.ko" 'hgw500_tx_ampdu_disable=0 hgw500_honest_tx_ack=0' || return 1
	load_base "$base/btcoexist.ko" || return 1
	load_base "$base/rtl_pci.ko" || return 1
	load_base "$base/rtl8192ee.ko" 'msi=0 dma64=0 aspm=0 ips=0 fwlps=0 swenc=1 disable_watchdog=1 debug_level=0 hgw500_tx_dma_wmb=1 hgw500_tx_close_diag=1' || return 1
	printf '%s\n' "$release" >"$state/modules-ready"
	start_diag || return 1
	log 'OMW2_TX3_ROLLBACK_PASS source=installed-rootfs'
}

fail()
{
	reason=$1
	log "OMW2_TX3_FAIL reason=$reason"
	rollback || log 'OMW2_TX3_ROLLBACK_FAIL'
	exit 1
}

[ "$(uname -r)" = "$release" ] || fail kernel
[ -x "$loader" ] || fail loader
[ -r "$bundle/SHA256SUMS" ] || fail checksums
(cd "$bundle" && sha256sum -c SHA256SUMS >/dev/null) || fail hash
[ -r "$state/hostapd.conf" ] || fail hostapd-config
grep -qx 'ssid=OpenMitraStar-2G-DIAG' "$state/hostapd.conf" || fail ssid
grep -qx 'wpa=0' "$state/hostapd.conf" || fail open-profile
! grep -Eq '^(wpa_passphrase|wpa_psk|wps_state|config_methods)=' "$state/hostapd.conf" || fail credential-or-wps-present

stop_ap
changed=1
unload_wifi || fail unload
for module in cfg80211 libarc4 mac80211; do
	grep -q "^$module " /proc/modules 2>/dev/null || load_bundle "$bundle/modules/$module.ko" || fail "load-$module"
done
load_bundle "$bundle/modules/rtlwifi.ko" 'hgw500_tx_ampdu_disable=0 hgw500_honest_tx_ack=0' || fail load-rtlwifi
load_bundle "$bundle/modules/btcoexist.ko" || fail load-btcoexist
load_bundle "$bundle/modules/rtl_pci.ko" 'hgw500_txbd_compact32=1' || fail load-rtl-pci
load_bundle "$bundle/modules/rtl8192ee.ko" 'msi=0 dma64=0 aspm=0 ips=0 fwlps=0 swenc=1 disable_watchdog=1 debug_level=0 hgw500_tx_dma_wmb=1 hgw500_tx_close_diag=1' || fail load-rtl8192ee
printf '%s\n' "$release" >"$state/modules-ready"
start_diag || fail start-ap
"$bundle/verify-realtek-tx3" OPENMITRASTAR_W2_TX3_VERIFY || fail verify
changed=0
log 'OMW2_TX3_APPLY_PASS data_compact32=1 protected_queues_stride64=1 dma_wmb=1 ssid=OpenMitraStar-2G-DIAG flash=0'
exit 0
