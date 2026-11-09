#!/bin/ash
set -eu

state=/run/openmitrastar/radio5g
conf="$state/hostapd-fresh.conf"

if [ -s "$state/hostapd.pid" ]; then
	old_pid=$(sed -n '1p' "$state/hostapd.pid")
	kill "$old_pid" >/dev/null 2>&1 || true
	sleep 1
fi

mkdir -p "$state" /var/run/hostapd
rm -f /var/run/hostapd/wifi0 "$state/hostapd.pid"
cat >"$conf" <<'EOF'
driver=madwifi
interface=wifi0
bridge=br0
hw_mode=a
channel=36
ssid=OpenMitraStar-5G-FRESH
auth_algs=1
wpa=0
ctrl_interface=/var/run/hostapd
logger_syslog=-1
logger_syslog_level=3
logger_stdout=-1
logger_stdout_level=3
EOF
chmod 0600 "$conf"

(
	trap '' HUP
	exec /usr/sbin/hostapd-qtn -dd -f "$state/hostapd-fresh.log" "$conf"
) >/dev/null 2>&1 &
printf '%s\n' "$!" >"$state/hostapd.pid"
chmod 0600 "$state/hostapd.pid"
sleep 3
/usr/sbin/iwpriv-qtn wifi0 pm 0
/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping
/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 get_config
/usr/sbin/iwconfig-qtn wifi0
printf 'Q3_FRESH_OPEN_PASS carrier=%s ssid=OpenMitraStar-5G-FRESH security=OPEN\n' \
	"$(cat /sys/class/net/wifi0/carrier)"
