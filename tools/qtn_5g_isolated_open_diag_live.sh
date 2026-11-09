#!/bin/ash
# Switch the already-running persistent 5 GHz AP to an isolated open diagnostic
# SSID.  This is a live-only test helper: no flash, no module load, no RF reopen.
set -e
set -u
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH

ssid=${1:-OpenMitraStar-5G-DIAG}
state=/run/openmitrastar/radio5g
control=/var/run/hostapd
rf=/sys/module/qdrv/parameters/openmitrastar_rf_enable

fail()
{
	reason=$1
	printf 'OMQTN5G_OPEN_DIAG_FAIL reason=%s\n' "$reason" >/dev/console 2>/dev/null || true
	printf 'OMQTN5G_OPEN_DIAG_FAIL reason=%s\n' "$reason"
	exit 1
}

case "$ssid" in ''|*[!A-Za-z0-9_.-]*) fail ssid ;; esac
grep -aq 'mitrastar,hgw-500bna-qcv2' /proc/device-tree/compatible || fail target
[ -e /sys/class/net/wifi0 ] || fail wifi0-missing
[ -e /sys/class/net/br0/brif/eth0 ] || fail eth0-not-bridged
[ -e /sys/class/net/br0/brif/wlan0 ] || fail wlan0-not-bridged
[ ! -e /sys/class/net/br0/brif/wifi0 ] || fail wifi0-unexpectedly-bridged
[ "$(cat "$rf" 2>/dev/null)" = 1 ] || fail rf-not-open
ifconfig wifi0 2>/dev/null | grep -q '192.168.77.1' || fail isolated-l3-address

if [ -s "$state/hostapd.pid" ]; then
	old_pid=$(sed -n '1{s/\r$//;p;}' "$state/hostapd.pid")
	case "$old_pid" in ''|*[!0-9]*) fail old-pid-format ;; esac
	kill "$old_pid" >/dev/null 2>&1 || true
	i=0
	while kill -0 "$old_pid" >/dev/null 2>&1 && [ "$i" -lt 20 ]; do
		i=$((i + 1))
		sleep 1
	done
	kill -0 "$old_pid" >/dev/null 2>&1 && fail old-hostapd-still-live
fi

mkdir -p "$state" "$control"
rm -f "$control/wifi0" "$state/hostapd.pid" "$state/hostapd.status" "$state/hostapd.get_config"
/usr/sbin/iwpriv-qtn wifi0 region 21317 >/dev/null 2>&1 || fail region-set
/usr/sbin/iwpriv-qtn wifi0 mode 11ac80Edge+ >/dev/null 2>&1 || fail mode-set
/usr/sbin/iwconfig-qtn wifi0 essid "$ssid" >/dev/null 2>&1 || fail ssid-set
/usr/sbin/iwconfig-qtn wifi0 channel 36 >/dev/null 2>&1 || fail channel-set
ifconfig wifi0 192.168.77.1 netmask 255.255.255.0 up >/dev/null 2>&1 || true
ifconfig wifi0 2>/dev/null | grep -q '192.168.77.1' || fail isolated-l3-address
conf=$state/hostapd-open-diag.conf
{
	printf '%s\n' \
		'driver=madwifi' \
		'interface=wifi0' \
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

(
	trap '' HUP
	exec /usr/sbin/hostapd-qtn -dd -f "$state/hostapd-open-diag.log" "$conf"
) >/dev/null 2>&1 &
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
			! grep -Eqi '^key_mgmt=.*WPA|^wpa=[1-9]|CCMP' "$state/hostapd.get_config"; then
			ready=1
			break
		fi
	fi
	sleep 1
done
[ "$ready" = 1 ] || fail hostapd-open-not-ready
/usr/sbin/iwpriv-qtn wifi0 pm 0 >/dev/null 2>&1 || true
[ "$(cat /sys/class/net/wifi0/carrier 2>/dev/null)" = 1 ] || fail carrier
[ "$(cat /sys/class/leds/openmitrastar:green:wlan5g/brightness 2>/dev/null)" = 255 ] || fail led
printf 'ready-open-diag\n' >"$state/state"
printf 'OMQTN5G_OPEN_DIAG_READY ssid=%s topology=isolated-l3 address=192.168.77.1 flash=0\n' "$ssid"
