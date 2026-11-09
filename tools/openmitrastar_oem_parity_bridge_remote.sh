#!/bin/ash

set -eu
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH

[ "${1:-}" = OPENMITRASTAR_OEM_PARITY_BRIDGE_RAM_ONLY ] || exit 171

root=/tmp/openmitrastar-ap/bundle
open_state=/tmp/openmitrastar-ap/open2g
state=/tmp/openmitrastar-ap/oem-parity
bb=$root/bin/busybox
hostapd=$root/bin/hostapd
hostapd_cli=$root/bin/hostapd_cli
detach=$root/bin/detach_exec

[ "$(uname -r)" = 5.10.260-openmitrastar-radiohw ] || exit 172
[ -x "$bb" ] && [ -x "$hostapd" ] && [ -x "$hostapd_cli" ] && [ -x "$detach" ] || exit 173
[ -e /sys/class/net/br0/brif/eth0 ] || exit 174
[ -e /sys/class/net/br0/brif/wlan0 ] || exit 175
[ -r "$open_state/hostapd.conf" ] || exit 176

rm -rf "$state"
mkdir -p "$state"
chmod 700 "$state"
cat >"$state/rollback.sh" <<'EOF'
#!/bin/ash
state=/tmp/openmitrastar-ap/oem-parity
sleep 120
[ -e "$state/commit" ] && exit 0
ifconfig br0 192.168.1.200 netmask 255.255.255.0 up >/dev/null 2>&1 || true
ifconfig br0:recovery down >/dev/null 2>&1 || true
echo 'OMPARITY rollback management=192.168.1.200' >/dev/console
EOF
chmod 700 "$state/rollback.sh"
"$detach" "$state/rollback.launch.log" "$state/rollback.sh"

if ! pidof hostapd >/dev/null 2>&1; then
	rm -rf "$open_state/ctrl"
	mkdir -p "$open_state/ctrl"
	chmod 700 "$open_state/ctrl"
	"$hostapd" -B -P "$open_state/hostapd.pid" -f "$open_state/hostapd.log" "$open_state/hostapd.conf"
fi

ifconfig br0 192.168.1.90 netmask 255.255.255.0 up
ifconfig br0:recovery 192.168.1.200 netmask 255.255.255.0 up
route del default >/dev/null 2>&1 || true
route add default gw 192.168.1.1 dev br0 >/dev/null 2>&1 || true

attempt=0
while [ "$attempt" -lt 20 ]; do
	"$hostapd_cli" -p "$open_state/ctrl" -i wlan0 status 2>/dev/null | grep -q '^state=ENABLED$' && break
	attempt=$((attempt + 1))
	sleep 1
done
[ "$attempt" -lt 20 ] || exit 177
[ -e /sys/class/net/br0/brif/eth0 ] || exit 178
[ -e /sys/class/net/br0/brif/wlan0 ] || exit 179
ifconfig br0 | grep -q '192.168.1.90' || exit 180
echo 'OMPARITY READY role=videobridge management=192.168.1.90 recovery_alias=192.168.1.200 upstream=192.168.1.1 br0=eth0+wlan0 security=OPEN' >/dev/console
printf 'OMPARITY_BRIDGE_STAGE_PASS=1\n'
