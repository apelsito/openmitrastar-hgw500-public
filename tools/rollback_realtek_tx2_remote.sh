#!/bin/ash
set -eu
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH

[ "${1:-}" = OPENMITRASTAR_W2_TX3_ROLLBACK ] || exit 171
release=5.10.260-openmitrastar-radiohw
base=/lib/modules/$release/openmitrastar/radio2g
state=/run/openmitrastar/radio2g
loader=${OM_MODULE_LOADER:-/usr/sbin/ram-insmod-qtn}

/usr/sbin/hostapd_cli -p "$state/ctrl" -i wlan0 terminate >/dev/null 2>&1 || true
[ ! -r "$state/hostapd.pid" ] || kill "$(cat "$state/hostapd.pid")" >/dev/null 2>&1 || true
sleep 1
brctl delif br0 wlan0 >/dev/null 2>&1 || true
ifconfig wlan0 down >/dev/null 2>&1 || true
for module in rtl8192ee rtl_pci btcoexist rtlwifi mac80211 cfg80211; do
	grep -q "^$module " /proc/modules 2>/dev/null || continue
	rmmod "$module"
done
for module in cfg80211 libarc4 mac80211; do
	grep -q "^$module " /proc/modules 2>/dev/null || "$loader" "$base/$module.ko"
done
"$loader" "$base/rtlwifi.ko" 'hgw500_tx_ampdu_disable=0 hgw500_honest_tx_ack=0'
"$loader" "$base/btcoexist.ko"
"$loader" "$base/rtl_pci.ko"
"$loader" "$base/rtl8192ee.ko" 'msi=0 dma64=0 aspm=0 ips=0 fwlps=0 swenc=1 disable_watchdog=1 debug_level=0 hgw500_tx_dma_wmb=1 hgw500_tx_close_diag=1'
printf '%s\n' "$release" >"$state/modules-ready"
ifconfig wlan0 down
/usr/sbin/iw dev wlan0 set type __ap
ifconfig wlan0 0.0.0.0 up
[ -e /sys/class/net/br0/brif/wlan0 ] || brctl addif br0 wlan0
rm -rf "$state/ctrl"
mkdir -p "$state/ctrl"
/usr/sbin/hostapd -f "$state/hostapd.log" "$state/hostapd.conf" >/dev/null 2>&1 &
printf '%s\n' "$!" >"$state/hostapd.pid"
sleep 2
/usr/sbin/hostapd_cli -p "$state/ctrl" -i wlan0 status | grep -qx 'state=ENABLED'
printf 'OMW2_TX3_ROLLBACK_PASS source=installed-rootfs ssid=OpenMitraStar-2G-DIAG\n' >/dev/console
