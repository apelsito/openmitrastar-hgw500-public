#!/bin/ash

# RAM-only recovery of the HGW-500BNA-QCv2 Realtek AP profile.
# Keeps eth0/br0 management intact and never touches MTD.
set -u
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH

[ "${1:-}" = OPENMITRASTAR_REALTEK_PROFILE_RAM_ONLY ] || exit 171

release=5.10.260-openmitrastar-radiohw
module_dir=/lib/modules/$release/openmitrastar/radio2g
rtlwifi_module=${OM_RTLWIFI_MODULE:-$module_dir/rtlwifi.ko}
rtlwifi_parameters=${OM_RTLWIFI_PARAMETERS:-}
expected_ampdu_disable=${OM_EXPECT_TX_AMPDU_DISABLE:-}
loader_image=/tmp/om-realtek-loader
loader_dir=/tmp/om-realtek-tools
loader=$loader_dir/busybox
hostapd=/usr/sbin/hostapd
hostapd_cli=/usr/sbin/hostapd_cli
state=/run/openmitrastar/radio2g
conf=$state/hostapd-open.conf
ctrl=$state/ctrl-open

fail()
{
	echo "OM2GRELOAD FAIL stage=$1" >/dev/console 2>/dev/null || true
	echo "OM2GRELOAD_FAIL=$1" >&2
	exit 1
}

[ "$(uname -r)" = "$release" ] || fail kernel
[ -x "$loader_image" ] || fail loader
[ -r "$conf" ] || fail open-config
[ -e /sys/class/net/br0/brif/eth0 ] || fail bridge-eth0
mkdir -p "$loader_dir" || fail loader-dir
ln -sf "$loader_image" "$loader" || fail loader-link

echo 'OM2GRELOAD BEGIN profile=msi0-dma32-aspm0-ips0-fwlps0-swenc1-watchdog0' >/dev/console

# Quiesce only the Wi-Fi leg.  Management stays on br0 through eth0.
if [ -e /sys/class/net/wlan0 ]; then
	pid=$(cat "$state/hostapd-open.pid" 2>/dev/null || true)
	[ -n "$pid" ] && kill "$pid" >/dev/null 2>&1 || true
	sleep 2
	brctl delif br0 wlan0 >/dev/null 2>&1 || true
	ifconfig wlan0 down >/dev/null 2>&1 || true
fi

for module in rtl8192ee rtl_pci btcoexist rtlwifi mac80211 cfg80211; do
	grep -q "^$module " /proc/modules 2>/dev/null || continue
	rmmod "$module" >/dev/null 2>&1 || fail "rmmod-$module"
done

for module in cfg80211 libarc4 mac80211 rtlwifi btcoexist rtl_pci; do
	grep -q "^$module " /proc/modules 2>/dev/null && continue
	path="$module_dir/$module.ko"
	if [ "$module" = rtlwifi ]; then
		path=$rtlwifi_module
		if [ -n "$rtlwifi_parameters" ]; then
			"$loader" insmod "$path" $rtlwifi_parameters || fail "insmod-$module"
		else
			"$loader" insmod "$path" || fail "insmod-$module"
		fi
	else
		"$loader" insmod "$path" || fail "insmod-$module"
	fi
done

"$loader" insmod "$module_dir/rtl8192ee.ko" \
	msi=0 dma64=0 aspm=0 ips=0 fwlps=0 swenc=1 \
	disable_watchdog=1 debug_level=5 || fail insmod-rtl8192ee

attempt=0
while [ "$attempt" -lt 20 ] && [ ! -e /sys/class/net/wlan0 ]; do
	attempt=$((attempt + 1))
	sleep 1
done
[ -e /sys/class/net/wlan0 ] || fail wlan0-after

check_param()
{
	name=$1
	expected=$2
	observed=$(cat "/sys/module/rtl8192ee/parameters/$name" 2>/dev/null) || fail "param-$name-missing"
	[ "$observed" = "$expected" ] || fail "param-$name-$observed"
}
check_param msi N
check_param dma64 N
check_param aspm 0
check_param ips N
check_param fwlps N
check_param swenc Y
check_param disable_watchdog Y
check_param debug_level 5
if [ -n "$expected_ampdu_disable" ]; then
	observed=$(cat /sys/module/rtlwifi/parameters/hgw500_tx_ampdu_disable 2>/dev/null) || fail ampdu-param-missing
	[ "$observed" = "$expected_ampdu_disable" ] || fail "ampdu-param-$observed"
fi

ifconfig wlan0 down || fail wlan0-down-before-ap
/usr/sbin/iw dev wlan0 set type __ap || fail wlan0-set-ap
ifconfig wlan0 0.0.0.0 up || fail wlan0-up
brctl addif br0 wlan0 || fail bridge-wlan0
rm -rf "$ctrl"
mkdir -p "$ctrl"
"$hostapd" -B -P "$state/hostapd-open.pid" -f "$state/hostapd-open.log" "$conf" || fail hostapd

attempt=0
while [ "$attempt" -lt 30 ]; do
	"$hostapd_cli" -p "$ctrl" -i wlan0 status 2>/dev/null | grep -q '^state=ENABLED$' && break
	attempt=$((attempt + 1))
	sleep 1
done
[ "$attempt" -lt 30 ] || fail hostapd-enabled

# GPIO11 is physically active-low on this unit.
echo 0 > /sys/class/leds/openmitrastar:green:wlan2g/brightness 2>/dev/null || true

echo 'OM2GRELOAD PASS interface=wlan0 bridge=br0 security=OPEN flash=0' >/dev/console
echo 'OM2GRELOAD_PASS=1'
