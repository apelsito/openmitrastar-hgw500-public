#!/bin/ash

# Restore the Q2 Realtek stack and an open diagnostic AP entirely in RAM.
set -u
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH

[ "${1:-}" = OPENMITRASTAR_Q2_OPEN_RAM_ONLY ] || exit 171

release=5.10.260-openmitrastar-radiohw
module_dir=/lib/modules/$release/openmitrastar/radio2g
loader_image=/tmp/om-realtek-loader
loader_dir=/tmp/om-realtek-tools
loader=$loader_dir/busybox
state=/run/openmitrastar/radio2g
open_conf=$state/hostapd-open.conf

fail()
{
	echo "OM2GRESTORE FAIL stage=$1" >/dev/console 2>/dev/null || true
	echo "OM2GRESTORE_FAIL=$1" >&2
	exit 1
}

[ "$(uname -r)" = "$release" ] || fail kernel
[ -x "$loader_image" ] || fail loader
[ -r "$open_conf" ] || fail open-config
[ -r /run/openmitrastar/secrets/wpa2.psk ] || fail bootstrap-psk
mkdir -p "$loader_dir" "$state"
ln -sf "$loader_image" "$loader" || fail loader-link

for module in ctr ccm cmac cfg80211 libarc4 mac80211 rtlwifi btcoexist rtl_pci; do
	grep -q "^$module " /proc/modules 2>/dev/null && continue
	"$loader" insmod "$module_dir/$module.ko" || fail "insmod-$module"
done
if ! grep -q '^rtl8192ee ' /proc/modules 2>/dev/null; then
	"$loader" insmod "$module_dir/rtl8192ee.ko" \
		msi=0 dma64=0 aspm=0 ips=0 fwlps=0 swenc=1 \
		disable_watchdog=1 debug_level=5 || fail insmod-rtl8192ee
fi

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

printf '%s\n' "$release" >"$state/modules-ready"
printf '%s\n' ready >"$state/modules-state"

# Reuse the product bridge transaction, then replace only the security profile.
/usr/sbin/om-radio-start || fail product-radio-start
pid=$(cat "$state/hostapd.pid" 2>/dev/null || true)
[ -n "$pid" ] && kill "$pid" >/dev/null 2>&1 || true
sleep 2
rm -rf "$state/ctrl-open"
mkdir -p "$state/ctrl-open"
/usr/sbin/hostapd -B -P "$state/hostapd-open.pid" -f "$state/hostapd-open.log" "$open_conf" || fail open-hostapd

attempt=0
while [ "$attempt" -lt 30 ]; do
	/usr/sbin/hostapd_cli -p "$state/ctrl-open" -i wlan0 status 2>/dev/null | grep -q '^state=ENABLED$' && break
	attempt=$((attempt + 1))
	sleep 1
done
[ "$attempt" -lt 30 ] || fail open-enabled

echo 0 > /sys/class/leds/openmitrastar:green:wlan2g/brightness 2>/dev/null || true
echo 'OM2GRESTORE PASS interface=wlan0 bridge=br0 security=OPEN profile=topaz-safe flash=0' >/dev/console
echo 'OM2GRESTORE_PASS=1'
