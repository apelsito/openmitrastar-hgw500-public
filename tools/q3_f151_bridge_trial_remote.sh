#!/bin/ash
# Reversible F151 bridge/DHCP trial. Runtime state only; no MTD writes.
set -eu

PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH

action=${1:-status}
state=/run/openmitrastar/radio5g
trial=/run/openmitrastar/radio5g-bridge-trial
rollback_script=$trial/rollback.sh
rf=/sys/module/qdrv/parameters/openmitrastar_rf_enable

log()
{
	printf '%s\n' "$*" >/dev/console 2>/dev/null || printf '%s\n' "$*"
}

rollback_now()
{
	txba_restore=$(cat "$trial/original_txba" 2>/dev/null || printf '0\n')
	case "$txba_restore" in 0|1) ;; *) txba_restore=0 ;; esac
	if [ -s "$trial/rollback.pid" ]; then
		rollback_pid=$(cat "$trial/rollback.pid" 2>/dev/null || true)
		[ "$rollback_pid" = "$$" ] || kill "$rollback_pid" >/dev/null 2>&1 || true
	fi
	old_pid=$(cat "$state/hostapd.pid" 2>/dev/null || true)
	case "$old_pid" in ''|*[!0-9]*) ;; *) kill "$old_pid" >/dev/null 2>&1 || true ;; esac
	rm -f /var/run/hostapd/wifi0 "$state/hostapd.pid"
	[ ! -e /sys/class/net/br0/brif/wifi0 ] || brctl delif br0 wifi0 >/dev/null 2>&1 || true
	ifconfig wifi0 0.0.0.0 down >/dev/null 2>&1 || true

	psk_file=/run/openmitrastar/secrets/wpa2.psk
	origin=/run/openmitrastar/origin-mtd5/runtime.conf
	ssid=$(awk -F= '$1 == "RADIO5G_SSID" { sub(/^[^=]*=/, ""); print; exit }' "$origin")
	IFS= read -r psk <"$psk_file" || return 1
	conf=$state/hostapd.conf
	{
		printf '%s\n' 'driver=madwifi' 'interface=wifi0' 'hw_mode=a' 'channel=36'
		printf 'ssid=%s\n' "$ssid"
		printf '%s\n' 'wpa=2' 'wpa_key_mgmt=WPA-PSK' 'wpa_pairwise=CCMP'
		printf 'wpa_passphrase=%s\n' "$psk"
		printf '%s\n' 'auth_algs=1' 'wpa_group_rekey=0' 'wpa_strict_rekey=0' 'wpa_gmk_rekey=0'
		printf '%s\n' 'ctrl_interface=/var/run/hostapd'
	} >"$conf"
	chmod 0600 "$conf"
	unset psk
	ifconfig wifi0 192.168.77.1 netmask 255.255.255.0 up >/dev/null 2>&1 || return 1
	/usr/sbin/hostapd-qtn -dd -f "$state/hostapd.log" "$conf" >/dev/null 2>&1 &
	new_pid=$!
	printf '%s\n' "$new_pid" >"$state/hostapd.pid"
	chmod 0600 "$state/hostapd.pid"
	i=0
	while [ "$i" -lt 30 ]; do
		i=$((i + 1))
		/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping >/dev/null 2>&1 && break
		sleep 1
	done
	/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping >/dev/null 2>&1 || return 1
	/usr/sbin/iwpriv-qtn wifi0 uapsd 1 >/dev/null 2>&1 || return 1
	/usr/sbin/iwpriv-qtn wifi0 setparam 402 "$txba_restore" >/dev/null 2>&1 || true
	printf 'ready\n' >"$state/state"
	printf 'ready\n' >"$state/ready"
	[ "$(cat "$state/state" 2>/dev/null)" = ready ] || return 1
	[ ! -e /sys/class/net/br0/brif/wifi0 ] || return 1
	ifconfig wifi0 2>/dev/null | grep -q '192.168.77.1' || return 1
	rm -rf "$trial"
	log 'OMQTN5G_BRIDGE_TRIAL_ROLLBACK_PASS topology=isolated-l3'
}

case "$action" in
rollback)
	rollback_now
	exit $?
	;;
status)
	printf 'state='; cat "$state/state" 2>/dev/null || printf 'absent\n'
	printf 'bridge='; [ -e /sys/class/net/br0/brif/wifi0 ] && printf '1\n' || printf '0\n'
	printf 'rollback='; [ -s "$trial/rollback.pid" ] && printf 'armed\n' || printf 'none\n'
	exit 0
	;;
apply) uapsd_mode=1; txba_disable=0 ;;
apply-uapsd-off) uapsd_mode=0; txba_disable=0 ;;
apply-txba-off) uapsd_mode=1; txba_disable=1 ;;
apply-uapsd-off-txba-off) uapsd_mode=0; txba_disable=1 ;;
*) exit 2 ;;
esac

fail()
{
	reason=$1
	log "OMQTN5G_BRIDGE_TRIAL_FAIL reason=$reason"
	printf 'OMQTN5G_BRIDGE_TRIAL_FAIL reason=%s\n' "$reason"
	rollback_now >/dev/null 2>&1 || true
	exit 1
}

grep -aq 'mitrastar,hgw-500bna-qcv2' /proc/device-tree/compatible || fail target
[ "$(cat "$state/state" 2>/dev/null)" = ready ] || fail radio5-not-ready
[ "$(cat "$rf" 2>/dev/null)" = 1 ] || fail rf-not-open
[ -e /sys/class/net/br0/brif/eth0 ] || fail eth0-not-bridged
[ -e /sys/class/net/br0/brif/wlan0 ] || fail wlan0-not-bridged
[ ! -e /sys/class/net/br0/brif/wifi0 ] || fail wifi0-already-bridged
ifconfig wifi0 2>/dev/null | grep -q '192.168.77.1' || fail isolated-address-missing

psk_file=/run/openmitrastar/secrets/wpa2.psk
origin=/run/openmitrastar/origin-mtd5/runtime.conf
[ -r "$psk_file" ] || fail psk-missing
ssid=$(awk -F= '$1 == "RADIO5G_SSID" { sub(/^[^=]*=/, ""); print; exit }' "$origin")
case "$ssid" in ''|*[!A-Za-z0-9_.-]*) fail ssid ;; esac
IFS= read -r psk <"$psk_file" || fail psk-read
[ "${#psk}" -ge 8 ] && [ "${#psk}" -le 63 ] || fail psk-length
original_txba=$(/usr/sbin/iwpriv-qtn wifi0 getparam 402 2>/dev/null |
	sed -n 's/.*getparam:\([01]\).*/\1/p' | head -n 1)
case "$original_txba" in 0|1) ;; *) fail txba-original-readback ;; esac

rm -rf "$trial"
mkdir -p "$trial"
chmod 0700 "$trial"
printf '%s\n' "$original_txba" >"$trial/original_txba"
chmod 0600 "$trial/original_txba"
cat >"$rollback_script" <<'EOF'
#!/bin/ash
set -eu
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH
state=/run/openmitrastar/radio5g
trial=/run/openmitrastar/radio5g-bridge-trial
txba_restore=$(cat "$trial/original_txba" 2>/dev/null || printf '0\n')
case "$txba_restore" in 0|1) ;; *) txba_restore=0 ;; esac
old_pid=$(cat "$state/hostapd.pid" 2>/dev/null || true)
case "$old_pid" in ''|*[!0-9]*) ;; *) kill "$old_pid" >/dev/null 2>&1 || true ;; esac
rm -f /var/run/hostapd/wifi0 "$state/hostapd.pid"
[ ! -e /sys/class/net/br0/brif/wifi0 ] || brctl delif br0 wifi0 >/dev/null 2>&1 || true
ifconfig wifi0 0.0.0 down >/dev/null 2>&1 || true
ssid=$(awk -F= '$1 == "RADIO5G_SSID" { sub(/^[^=]*=/, ""); print; exit }' /run/openmitrastar/origin-mtd5/runtime.conf)
IFS= read -r psk </run/openmitrastar/secrets/wpa2.psk
conf=$state/hostapd.conf
{
	printf '%s\n' 'driver=madwifi' 'interface=wifi0' 'hw_mode=a' 'channel=36'
	printf 'ssid=%s\n' "$ssid"
	printf '%s\n' 'wpa=2' 'wpa_key_mgmt=WPA-PSK' 'wpa_pairwise=CCMP'
	printf 'wpa_passphrase=%s\n' "$psk"
	printf '%s\n' 'auth_algs=1' 'wpa_group_rekey=0' 'wpa_strict_rekey=0' 'wpa_gmk_rekey=0'
	printf '%s\n' 'ctrl_interface=/var/run/hostapd'
} >"$conf"
chmod 0600 "$conf"
unset psk
ifconfig wifi0 192.168.77.1 netmask 255.255.255.0 up >/dev/null 2>&1
/usr/sbin/hostapd-qtn -dd -f "$state/hostapd.log" "$conf" >/dev/null 2>&1 &
printf '%s\n' "$!" >"$state/hostapd.pid"
chmod 0600 "$state/hostapd.pid"
i=0
while [ "$i" -lt 30 ]; do
	i=$((i + 1))
	/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping >/dev/null 2>&1 && break
	sleep 1
done
/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping >/dev/null 2>&1
/usr/sbin/iwpriv-qtn wifi0 uapsd 1 >/dev/null 2>&1 || true
/usr/sbin/iwpriv-qtn wifi0 setparam 402 "$txba_restore" >/dev/null 2>&1 || true
printf 'ready\n' >"$state/state"
printf 'ready\n' >"$state/ready"
	printf 'OMQTN5G_BRIDGE_TRIAL_ROLLBACK_PASS topology=isolated-l3\n' >/dev/console 2>/dev/null || true
rm -rf /run/openmitrastar/radio5g-bridge-trial
EOF
chmod 0700 "$rollback_script"
(
	sleep 420
	[ -e "$trial/commit" ] || /bin/ash "$rollback_script"
) </dev/null >/dev/null 2>&1 &
printf '%s\n' "$!" >"$trial/rollback.pid"

old_pid=$(cat "$state/hostapd.pid" 2>/dev/null || true)
case "$old_pid" in ''|*[!0-9]*) fail hostapd-pid ;; esac
kill "$old_pid" >/dev/null 2>&1 || fail hostapd-stop
i=0
while kill -0 "$old_pid" >/dev/null 2>&1 && [ "$i" -lt 20 ]; do
	i=$((i + 1)); sleep 1
done
kill -0 "$old_pid" >/dev/null 2>&1 && fail hostapd-still-running

conf=$trial/hostapd.conf
{
	printf '%s\n' 'driver=madwifi' 'interface=wifi0' 'bridge=br0' 'hw_mode=a' 'channel=36'
	printf 'ssid=%s\n' "$ssid"
	printf '%s\n' 'wpa=2' 'wpa_key_mgmt=WPA-PSK' 'wpa_pairwise=CCMP'
	printf 'wpa_passphrase=%s\n' "$psk"
	printf '%s\n' 'auth_algs=1' 'wpa_group_rekey=0' 'wpa_strict_rekey=0' 'wpa_gmk_rekey=0'
	printf '%s\n' 'ctrl_interface=/var/run/hostapd'
} >"$conf"
chmod 0600 "$conf"
unset psk

rm -f /var/run/hostapd/wifi0
ifconfig wifi0 0.0.0.0 up || fail wifi0-clear-ip
! ifconfig wifi0 2>/dev/null | grep -q 'inet addr:' || fail wifi0-ip-still-present
brctl addif br0 wifi0 || fail bridge-add
[ -e /sys/class/net/br0/brif/wifi0 ] || fail bridge-member-missing-after-addif
printf '%s\n' 'OMQTN5G_BRIDGE_STAGE bridge-member-after-addif=1'
ifconfig wifi0 up || fail wifi0-up
[ -e /sys/class/net/br0/brif/wifi0 ] || fail bridge-member-missing-after-up
printf '%s\n' 'OMQTN5G_BRIDGE_STAGE bridge-member-after-up=1'
/usr/sbin/hostapd-qtn -dd -f "$trial/hostapd.log" "$conf" >/dev/null 2>&1 &
new_pid=$!
printf '%s\n' "$new_pid" >"$state/hostapd.pid"
printf '%s\n' "$new_pid" >"$trial/hostapd.pid"
chmod 0600 "$state/hostapd.pid" "$trial/hostapd.pid"

ready=0
i=0
while [ "$i" -lt 30 ]; do
	i=$((i + 1))
	if kill -0 "$new_pid" >/dev/null 2>&1 &&
		/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping >/dev/null 2>&1 &&
		[ "$(cat /sys/class/net/wifi0/carrier 2>/dev/null)" = 1 ]; then
		ready=1
		break
	fi
	sleep 1
done
[ "$ready" = 1 ] || fail hostapd-not-ready
[ "$uapsd_mode" = 1 ] || {
	/usr/sbin/iwpriv-qtn wifi0 uapsd 0 >/dev/null 2>&1 || fail uapsd-disable
	/usr/sbin/iwpriv-qtn wifi0 get_uapsd 2>/dev/null | grep -q 'get_uapsd:0' || fail uapsd-readback
}
/usr/sbin/iwpriv-qtn wifi0 setparam 402 "$txba_disable" >/dev/null 2>&1 || fail txba-set
/usr/sbin/iwpriv-qtn wifi0 getparam 402 2>/dev/null | grep -q "getparam:$txba_disable" || fail txba-readback
[ -e /sys/class/net/br0/brif/wifi0 ] || fail bridge-member-missing-after-hostapd
ifconfig br0 2>/dev/null | grep -q '192.168.1.90' || fail management-ip-missing
config=$(/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 get_config)
printf '%s\n' "$config" | grep -Fqx "ssid=$ssid" || fail ssid-readback
printf '%s\n' "$config" | grep -Eq '^key_mgmt=.*WPA-PSK' || fail wpa2-readback
printf '%s\n' "$config" | grep -Eq '^(group_cipher|rsn_pairwise_cipher)=CCMP' || fail ccmp-readback
printf 'ready-bridge-trial\n' >"$state/state"
log "OMQTN5G_BRIDGE_TRIAL_READY topology=br0 hostapd_bridge=1 uapsd=$uapsd_mode txba_disable=$txba_disable security=WPA2-PSK-CCMP rollback_seconds=420 psk=redacted"
printf 'OMQTN5G_BRIDGE_TRIAL_READY topology=br0 hostapd_bridge=1 uapsd=%s txba_disable=%s security=WPA2-PSK-CCMP rollback_seconds=420 psk=redacted\n' "$uapsd_mode" "$txba_disable"
exit 0
