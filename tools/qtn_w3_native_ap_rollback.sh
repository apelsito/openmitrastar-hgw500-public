#!/bin/sh
set -u
root=${1:-/tmp/qtn-native-ap}
reason=${2:-manual}
rf=/sys/module/qdrv/parameters/openmitrastar_rf_enable
if [ -s "$root/hostapd.pid" ]; then
	pid=$(cat "$root/hostapd.pid" 2>/dev/null || true)
	case "$pid" in ''|*[!0-9]*) ;; *) kill "$pid" 2>/dev/null || true ;; esac
fi
ifconfig wifi0 down 2>/dev/null || true
test -e /sys/class/net/br0/brif/wifi0 && brctl delif br0 wifi0 2>/dev/null || true
test -e "$rf" && printf '0\n' >"$rf"
rm -f /var/run/hostapd/wifi0 "$root/hostapd.pid" "$root/commit" \
	"$root/hostapd.conf" "$root/status" "$root/ping" "$root/get_config"
echo "OMNATIVEAP rollback-complete reason=$reason rf=closed wifi0=down" >/dev/console
