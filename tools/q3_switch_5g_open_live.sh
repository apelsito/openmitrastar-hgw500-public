#!/bin/ash
# Switch the already-running Q3 wifi0 AP to an open lab network.
set -eu
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH

state=/run/openmitrastar/radio5g
control=/var/run/hostapd
rf=/sys/module/qdrv/parameters/openmitrastar_rf_enable
ssid=MOVISTAR_PLUS_55CB

fail()
{
	reason=$1
	printf 'OMRADIO5_OPEN_FAIL reason=%s\n' "$reason" >/dev/console 2>/dev/null || true
	exit 1
}

grep -aq 'mitrastar,hgw-500bna-qcv2' /proc/device-tree/compatible || fail target
[ -e /sys/class/net/wifi0 ] || fail wifi0-missing
[ -e /sys/class/net/br0/brif/eth0 ] || fail eth0-not-bridged
[ -e /sys/class/net/br0/brif/wlan0 ] || fail wlan0-not-bridged
[ -e /sys/class/net/br0/brif/wifi0 ] || fail wifi0-not-bridged
[ "$(cat "$rf")" = 1 ] || fail rf-closed

if [ -s "$state/hostapd.pid" ]; then
	old_pid=$(sed -n '1p' "$state/hostapd.pid")
	case "$old_pid" in ''|*[!0-9]*) fail old-pid-format ;; esac
	kill "$old_pid" >/dev/null 2>&1 || fail old-hostapd-stop
	i=0
	while kill -0 "$old_pid" >/dev/null 2>&1 && [ "$i" -lt 20 ]; do
		i=$((i + 1)); sleep 1
	done
	kill -0 "$old_pid" >/dev/null 2>&1 && fail old-hostapd-still-live
fi

mkdir -p "$control" "$state"
rm -f "$control/wifi0" "$state/hostapd.pid" "$state/hostapd.status" "$state/hostapd.get_config"
conf=$state/hostapd-open.conf
{
	printf '%s\n' \
		'driver=madwifi' \
		'interface=wifi0' \
		'bridge=br0' \
		'hw_mode=a' \
		'channel=36' \
		"ssid=$ssid" \
		'auth_algs=1' \
		'wpa=0' \
		'ctrl_interface=/var/run/hostapd' \
		'logger_syslog=-1' \
		'logger_syslog_level=3' \
		'logger_stdout=-1' \
		'logger_stdout_level=3'
} >"$conf"
chmod 0600 "$conf"

/usr/sbin/hostapd-qtn -dd -f "$state/hostapd-open.log" "$conf" &
pid=$!
case "$pid" in ''|*[!0-9]*) fail new-pid ;; esac
printf '%s\n' "$pid" >"$state/hostapd.pid"
chmod 0600 "$state/hostapd.pid"

ready=0
i=0
while [ "$i" -lt 30 ]; do
	i=$((i + 1))
	if kill -0 "$pid" >/dev/null 2>&1 &&
		/usr/sbin/hostapd-cli-qtn -p "$control" -i wifi0 ping >"$state/hostapd.status" 2>&1 &&
		grep -qx PONG "$state/hostapd.status"; then
		/usr/sbin/hostapd-cli-qtn -p "$control" -i wifi0 get_config >"$state/hostapd.get_config" 2>&1 || true
		if grep -Fqx "ssid=$ssid" "$state/hostapd.get_config" &&
			! grep -Eq '^key_mgmt=.*WPA|^(group_cipher|rsn_pairwise_cipher)=CCMP' "$state/hostapd.get_config"; then
			ready=1
			break
		fi
	fi
	sleep 1
done
[ "$ready" = 1 ] || fail hostapd-open-not-ready
[ "$(cat /sys/class/net/wifi0/carrier)" = 1 ] || fail carrier
[ "$(cat /sys/class/leds/openmitrastar:green:wlan5g/brightness)" = 255 ] || fail led
printf 'ready-open\n' >"$state/state"
printf 'OMRADIO5_OPEN_READY ssid=%s channel=36 bw=80 security=OPEN\n' "$ssid" >/dev/console 2>/dev/null || true
exit 0
