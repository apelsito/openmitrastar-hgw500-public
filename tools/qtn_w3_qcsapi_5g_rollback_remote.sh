#!/bin/sh
set -u

root=${1:-/tmp/w3-qcsapi-5g-ap}
reason=${2:-unspecified}
bridge=${3:-br0}
gate=/sys/module/qdrv/parameters/openmitrastar_rf_enable

test "$bridge" = br0 || bridge=br0

if test -f "$root/private/hostapd.pid"; then
	pid=$(sed -n '1p' "$root/private/hostapd.pid" 2>/dev/null || true)
	case "$pid" in
		''|*[!0-9]*) ;;
		*) kill "$pid" >/dev/null 2>&1 || true ;;
	esac
fi

if command -v ifconfig >/dev/null 2>&1; then
	ifconfig wifi0 down >/dev/null 2>&1 || true
else
	/bin/busybox ifconfig wifi0 down >/dev/null 2>&1 || true
fi

test -e "$gate" && printf '0\n' >"$gate" 2>/dev/null || true
if command -v brctl >/dev/null 2>&1; then
	brctl delif "$bridge" wifi0 >/dev/null 2>&1 || true
else
	/bin/busybox brctl delif "$bridge" wifi0 >/dev/null 2>&1 || true
fi

rm -f "$root/private/wpa2.psk" "$root/private/hostapd.conf" \
	"$root/private/qcsapi-passphrase.readback" "$root/commit"
echo "OMQCSAPI rollback-complete reason=$reason rf=closed wifi0=down bridge=$bridge-detached" >/dev/console
