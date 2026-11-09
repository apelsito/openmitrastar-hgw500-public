#!/bin/ash
set -eu
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH

[ "${1:-}" = OPENMITRASTAR_W2_TX3_VERIFY ] || exit 171
state=/run/openmitrastar/radio2g

fail() { printf 'OMW2_TX3_VERIFY_FAIL reason=%s\n' "$1" >&2; exit 1; }
check()
{
	module=$1
	parameter=$2
	expected=$3
	[ "$(cat "/sys/module/$module/parameters/$parameter" 2>/dev/null)" = "$expected" ] || fail "$module-$parameter"
}

check rtl_pci hgw500_txbd_compact32 Y
check rtlwifi hgw500_tx_ampdu_disable N
check rtlwifi hgw500_honest_tx_ack N
check rtl8192ee hgw500_tx_dma_wmb Y
check rtl8192ee hgw500_tx_close_diag Y
check rtl8192ee msi N
check rtl8192ee dma64 N
check rtl8192ee aspm 0
check rtl8192ee ips N
check rtl8192ee fwlps N
check rtl8192ee swenc Y
check rtl8192ee disable_watchdog Y
check rtl8192ee debug_level 0

dmesg | grep -q 'OMRTLTX3 stage=txbd-layout data_compact32=1 requested=1 dma64=0' || fail layout-marker
for expected in 'q=0 stride=32 compact=1' 'q=1 stride=32 compact=1' 'q=2 stride=32 compact=1' 'q=3 stride=32 compact=1' 'q=4 stride=64 compact=0' 'q=6 stride=64 compact=0'; do
	dmesg | grep -q "OMRTLTX3 stage=txbd-ring $expected" || fail "stride-$expected"
done
dmesg | grep -q 'OMRTLTX1 stage=publish-barrier-active target=hgw500 rtl8192ee=1 dma64=0' || fail barrier-marker
/usr/sbin/hostapd_cli -p "$state/ctrl" -i wlan0 status | grep -qx 'state=ENABLED' || fail hostapd
/usr/sbin/hostapd_cli -p "$state/ctrl" -i wlan0 get_config >"$state/tx2-hostapd-config.txt" || fail hostapd-config
grep -qx 'ssid=OpenMitraStar-2G-DIAG' "$state/tx2-hostapd-config.txt" || fail ssid
grep -qx 'wpa=0' "$state/hostapd.conf" || fail open-profile
! grep -Eq '^(wpa_passphrase|wpa_psk|wps_state|config_methods)=' "$state/hostapd.conf" || fail credential-or-wps-present
[ -e /sys/class/net/br0/brif/eth0 ] || fail bridge-eth0
[ -e /sys/class/net/br0/brif/wlan0 ] || fail bridge-wlan0
[ -e /sys/class/leds/openmitrastar:green:wlan2g/brightness ] || fail gpio11-led

printf 'OMW2_TX3_VERIFY_PASS data_compact32=1 protected_queues_stride64=1 dma_wmb=1 tx_close_diag=1 ampdu=baseline ack=baseline ssid=OpenMitraStar-2G-DIAG security=OPEN flash=0\n'
