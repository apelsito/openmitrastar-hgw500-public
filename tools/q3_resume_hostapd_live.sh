#!/bin/ash
# Resume the Q3 5 GHz AP after the OEM hostapd rejected its unsupported
# pid_file= directive.  RAM-only diagnostic: modules/qdrv/wifi0 must already
# be alive and RF must still be closed by the service rollback.
set -eu

state=/run/openmitrastar/radio5g
origin=/run/openmitrastar/origin-mtd5
psk_file=/run/openmitrastar/secrets/wpa2.psk
rf=/sys/module/qdrv/parameters/openmitrastar_rf_enable

fail()
{
	reason=$1
	printf 'Q3_HOSTAPD_RESUME_FAIL reason=%s\n' "$reason" >/dev/console
	if [ -s "$state/hostapd.pid" ]; then
		kill "$(cat "$state/hostapd.pid")" >/dev/null 2>&1 || true
	fi
	printf '0\n' >"$rf" 2>/dev/null || true
	[ ! -e /sys/class/net/br0/brif/wifi0 ] || brctl delif br0 wifi0 >/dev/null 2>&1 || true
	rm -f "$state/hostapd.conf" "$state/hostapd.pid" "$state/commit"
	printf 'resume-failed-%s\n' "$reason" >"$state/state"
	exit 1
}

value()
{
	awk -F= -v key="$1" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "$2" 2>/dev/null |
		sed 's/\r$//'
}

grep -aq 'mitrastar,hgw-500bna-qcv2' /proc/device-tree/compatible || fail target
[ -e /sys/class/net/eth0 ] && [ -e /sys/class/net/wlan0 ] && [ -e /sys/class/net/wifi0 ] || fail interfaces
[ "$(cat /sys/module/board_compat/parameters/allow_dram_sram_fallback)" = Y ] || fail sram-gate
[ "$(cat /sys/module/switch_tqe/parameters/w3_rx_ring_entries)" = 256 ] || fail tqe-ring
[ "$(cat /sys/module/switch_emac/parameters/w3_symbols_only)" = Y ] || fail symbols-only
[ "$(cat "$rf")" = 0 ] || fail rf-not-closed
[ -r "$psk_file" ] || fail psk-file

ssid=$(value RADIO5G_SSID "$origin/runtime.conf")
case "$ssid" in ''|*[!A-Za-z0-9_.-]*) fail ssid ;; esac
IFS= read -r psk <"$psk_file" || fail psk-read
[ "${#psk}" -ge 8 ] && [ "${#psk}" -le 63 ] || { unset psk; fail psk-length; }

mkdir -p /var/run/hostapd
rm -f /var/run/hostapd/wifi0
conf="$state/hostapd.conf"
{
	printf '%s\n' 'driver=madwifi' 'interface=wifi0' 'bridge=br0' 'hw_mode=a' 'channel=36'
	printf 'ssid=%s\n' "$ssid"
	printf '%s\n' 'wpa=2' 'wpa_key_mgmt=WPA-PSK' 'wpa_pairwise=CCMP'
	printf 'wpa_passphrase=%s\n' "$psk"
	printf '%s\n' 'auth_algs=1' 'wpa_group_rekey=0' 'wpa_strict_rekey=0' 'wpa_gmk_rekey=0'
	printf '%s\n' 'ctrl_interface=/var/run/hostapd'
	printf '%s\n' 'logger_syslog=-1' 'logger_syslog_level=3' 'logger_stdout=-1' 'logger_stdout_level=3'
} >"$conf"
chmod 0600 "$conf"
unset psk

[ -e /sys/class/net/br0/brif/wifi0 ] || brctl addif br0 wifi0 || fail bridge-add
rm -f "$state/commit"
(
	sleep 120
	[ -e "$state/commit" ] || {
		[ ! -s "$state/hostapd.pid" ] || kill "$(cat "$state/hostapd.pid")" >/dev/null 2>&1 || true
		printf '0\n' >"$rf" 2>/dev/null || true
		[ ! -e /sys/class/net/br0/brif/wifi0 ] || brctl delif br0 wifi0 >/dev/null 2>&1 || true
		printf 'resume-rollback-timeout\n' >"$state/state"
	}
) >/dev/null 2>&1 &
rollback_pid=$!

printf '1\n' >"$rf" || fail rf-open
/usr/sbin/hostapd-qtn -dd -f "$state/hostapd.log" "$conf" &
hostapd_pid=$!
printf '%s\n' "$hostapd_pid" >"$state/hostapd.pid"
chmod 0600 "$state/hostapd.pid"
kill -0 "$hostapd_pid" >/dev/null 2>&1 || fail hostapd-start

ready=0
i=0
while [ "$i" -lt 30 ]; do
	i=$((i + 1))
	if /usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping >"$state/hostapd.status" 2>&1 &&
		grep -qx PONG "$state/hostapd.status"; then
		ready=1
		break
	fi
	sleep 1
done
[ "$ready" = 1 ] || fail hostapd-not-ready
[ "$(( $(cat /sys/class/net/wifi0/flags) & 0x41 ))" -eq 65 ] || fail wifi0-not-running
[ -e /sys/class/net/br0/brif/eth0 ] && [ -e /sys/class/net/br0/brif/wlan0 ] &&
	[ -e /sys/class/net/br0/brif/wifi0 ] || fail bridge-members

touch "$state/commit"
chmod 0600 "$state/commit"
kill "$rollback_pid" >/dev/null 2>&1 || true
printf 'ready\n' >"$state/ready"
printf 'ready\n' >"$state/state"
printf 'Q3_HOSTAPD_RESUME_PASS ssid=%s region=ES channel=36 bw=80 security=WPA2-PSK-CCMP psk=redacted\n' "$ssid" >/dev/console
exit 0
