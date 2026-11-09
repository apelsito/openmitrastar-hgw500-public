#!/bin/ash

set -eu
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH

ack=${1:-}
[ "$ack" = OPENMITRASTAR_OPEN_2G_ISOLATED_RAM_ONLY ] || exit 171

root=/tmp/openmitrastar-ap/bundle
state=/tmp/openmitrastar-ap/open2g
hostapd=$root/bin/hostapd
hostapd_cli=$root/bin/hostapd_cli
detach=$root/bin/detach_exec

[ "$(uname -r)" = 5.10.260-openmitrastar-radiohw ] || exit 172
[ -x "$hostapd" ] && [ -x "$hostapd_cli" ] && [ -x "$detach" ] || exit 173
[ -e /sys/class/net/eth0 ] && [ -e /sys/class/net/wlan0 ] || exit 174
[ ! -e /sys/class/net/br0 ] || exit 175
ifconfig eth0 | grep -q '192.168.1.200' || exit 176

rm -rf "$state"
mkdir -p "$state/ctrl"
chmod 700 "$state" "$state/ctrl"
cat >"$state/hostapd.conf" <<'EOF'
interface=wlan0
driver=nl80211
ctrl_interface=/tmp/openmitrastar-ap/open2g/ctrl
ctrl_interface_group=0
ssid=OpenMitraStar-RXGuard-Open
country_code=ES
ieee80211d=1
hw_mode=g
channel=1
ieee80211n=1
wmm_enabled=1
auth_algs=1
wpa=0
ignore_broadcast_ssid=0
EOF
chmod 600 "$state/hostapd.conf"

cat >"$state/rollback.sh" <<'EOF'
#!/bin/ash
state=/tmp/openmitrastar-ap/open2g
sleep 300
[ -e "$state/commit" ] && exit 0
/tmp/openmitrastar-ap/bundle/bin/hostapd_cli -p "$state/ctrl" -i wlan0 terminate >/dev/null 2>&1 || true
[ ! -r "$state/hostapd.pid" ] || kill "$(cat "$state/hostapd.pid")" >/dev/null 2>&1 || true
ifconfig wlan0 0.0.0.0 down >/dev/null 2>&1 || true
echo 'OMOPEN2G rollback reason=timeout' >/dev/console
EOF
chmod 700 "$state/rollback.sh"
"$detach" "$state/rollback.launch.log" "$state/rollback.sh"

pidof hostapd >/dev/null 2>&1 && killall hostapd >/dev/null 2>&1 || true
ifconfig wlan0 down
ifconfig wlan0 192.168.2.1 netmask 255.255.255.0 up
"$hostapd" -B -P "$state/hostapd.pid" -f "$state/hostapd.log" "$state/hostapd.conf"

attempt=0
while [ "$attempt" -lt 30 ]; do
	"$hostapd_cli" -p "$state/ctrl" -i wlan0 status 2>/dev/null | grep -q '^state=ENABLED$' && break
	attempt=$((attempt + 1))
	sleep 1
done
[ "$attempt" -lt 30 ] || exit 177
[ ! -e /sys/class/net/br0 ] || exit 178
ifconfig eth0 | grep -q '192.168.1.200' || exit 179
echo 'OMOPEN2G AP_READY ssid=OpenMitraStar-RXGuard-Open security=OPEN channel=1 wlan0=192.168.2.1 rollback_s=300' >/dev/console
printf 'OMOPEN2G_AP_PASS=1 ssid=OpenMitraStar-RXGuard-Open security=OPEN\n'
