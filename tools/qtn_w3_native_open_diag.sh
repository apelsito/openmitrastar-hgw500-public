#!/bin/sh
set -eu

ack=${1:-}
root=/tmp/qtn-native-open
rf=/sys/module/qdrv/parameters/openmitrastar_rf_enable
hostapd=/tmp/hostapd-qtn-v4
cli=/tmp/hostapd-cli-qtn-v4
rollback=/tmp/qtn-native-ap-rollback.sh
stop() { code=$1; shift; echo "OMOPEN5G stop code=$code $*" >/dev/console; sh "$rollback" "$root" script-failure; exit "$code"; }

test "$ack" = OPENMITRASTAR_QTN_W3_OPEN_DIAG_RAM_ONLY || exit 171
mkdir -p "$root" /var/run/hostapd
chmod 0700 "$root"
test "$(cat "$rf")" = 0 || stop 172 reason=rf_preopen
test "$(cat /sys/class/net/wifi0/operstate)" = down || stop 172 reason=wifi_not_down
test -e /sys/class/net/br0/brif/eth1_emac1 || stop 172 reason=management_missing
grep -q '^wlan_scan_ap ' /proc/modules || stop 172 reason=wlan_scan_ap_missing

conf=$root/hostapd.conf
{
	echo driver=madwifi
	echo interface=wifi0
	echo bridge=br0
	echo hw_mode=a
		echo ssid=OpenMitraStar-5G
	echo auth_algs=1
	echo wpa=0
	echo ctrl_interface=/var/run/hostapd
	echo logger_stdout=-1
	echo logger_stdout_level=0
} >"$conf"
chmod 0600 "$conf"
rm -f "$root/commit" "$root/hostapd.pid" "$root/ping" "$root/get_config"
test -e /sys/class/net/br0/brif/wifi0 || brctl addif br0 wifi0
(
	sleep 600
	test -e "$root/commit" || sh "$rollback" "$root" timeout
) >/dev/null 2>&1 &
echo $! >"$root/rollback.pid"
echo "OMOPEN5G rollback-armed seconds=600" >/dev/console
printf '1\n' >"$rf"
"$hostapd" -B -dd -P "$root/hostapd.pid" -f "$root/hostapd.log" "$conf" || stop 173 reason=hostapd_start

i=0
while [ "$i" -lt 30 ]; do
	i=$((i + 1))
	if [ -e /var/run/hostapd/wifi0 ]; then
		"$cli" -p /var/run/hostapd -i wifi0 ping >"$root/ping" 2>&1 || true
		"$cli" -p /var/run/hostapd -i wifi0 get_config >"$root/get_config" 2>&1 || true
		grep -qx PONG "$root/ping" && grep -qx 'ssid=OpenMitraStar-5G' "$root/get_config" && break
	fi
	sleep 1
done
grep -qx PONG "$root/ping" || stop 174 reason=no_pong
grep -qx 'ssid=OpenMitraStar-5G' "$root/get_config" || stop 174 reason=ssid
grep -Fq 'wifi0: Setup of interface done.' "$root/hostapd.log" || stop 174 reason=setup
flags=$(cat /sys/class/net/wifi0/flags)
test $((flags & 0x41)) -eq 65 || stop 174 reason=wifi_not_up_running flags="$flags"
touch "$root/commit"
chmod 0600 "$root/commit"
echo "W3_QTN_OPEN_AP_PASS=1 ssid=OpenMitraStar-5G security=open commit=1 flash=0"
