#!/bin/ash

set -eu
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH

[ "${1:-}" = OPENMITRASTAR_OPEN_2G_BRIDGE_RAM_ONLY ] || exit 171

root=/tmp/openmitrastar-ap/bundle
state=/tmp/openmitrastar-ap/open2g-bridge
bb=$root/bin/busybox
detach=$root/bin/detach_exec

[ "$(uname -r)" = 5.10.260-openmitrastar-radiohw ] || exit 172
[ -x "$bb" ] && [ -x "$detach" ] || exit 173
[ -e /sys/class/net/eth0 ] && [ -e /sys/class/net/wlan0 ] || exit 174
[ ! -e /sys/class/net/br0 ] || exit 175
ifconfig eth0 | grep -q '192.168.1.200' || exit 176
pidof hostapd >/dev/null 2>&1 || exit 177

rm -rf "$state"
mkdir -p "$state"
chmod 700 "$state"
cat >"$state/rollback.sh" <<'EOF'
#!/bin/ash
state=/tmp/openmitrastar-ap/open2g-bridge
bb=/tmp/openmitrastar-ap/bundle/bin/busybox
sleep 120
[ -e "$state/commit" ] && exit 0
$bb brctl delif br0 wlan0 >/dev/null 2>&1 || true
$bb brctl delif br0 eth0 >/dev/null 2>&1 || true
$bb ifconfig br0 0.0.0.0 down >/dev/null 2>&1 || true
$bb brctl delbr br0 >/dev/null 2>&1 || true
$bb ifconfig eth0 192.168.1.200 netmask 255.255.255.0 up >/dev/null 2>&1 || true
$bb ifconfig wlan0 192.168.2.1 netmask 255.255.255.0 up >/dev/null 2>&1 || true
echo 'OMOPEN2G_BRIDGE rollback reason=timeout' >/dev/console
EOF
chmod 700 "$state/rollback.sh"
"$detach" "$state/rollback.launch.log" "$state/rollback.sh"

ifconfig wlan0 0.0.0.0 up
ifconfig eth0 0.0.0.0 up
brctl addbr br0
brctl addif br0 eth0
brctl addif br0 wlan0
ifconfig br0 192.168.1.200 netmask 255.255.255.0 up
route del default >/dev/null 2>&1 || true
route add default gw 192.168.1.1 dev br0 >/dev/null 2>&1 || true

[ -e /sys/class/net/br0/brif/eth0 ] || exit 178
[ -e /sys/class/net/br0/brif/wlan0 ] || exit 179
ifconfig br0 | grep -q '192.168.1.200' || exit 180
echo 'OMOPEN2G_BRIDGE READY br0=eth0+wlan0 management=192.168.1.200 rollback_s=120' >/dev/console
printf 'OMOPEN2G_BRIDGE_STAGE_PASS=1\n'
