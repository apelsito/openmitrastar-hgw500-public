#!/bin/sh
set -eu

ack=${1:-}
rollback_seconds=${2:-120}
commit_mode=${3:-auto}
root=/tmp/qtn-native-open-ap
rf=/sys/module/qdrv/parameters/openmitrastar_rf_enable
hostapd=/tmp/hostapd-qtn-v4
cli=/tmp/hostapd-cli-qtn-v4
iwconfig=/tmp/iwconfig-v4
iwpriv=/tmp/iwpriv-v4
rollback=/tmp/qtn-native-ap-rollback.sh
stop() { code=$1; shift; echo "OMNATIVEOPEN stop code=$code $*" >/dev/console; sh "$rollback" "$root" script-failure; exit "$code"; }
sha_file() { /bin/busybox sha256sum "$1" | awk '{print $1}'; }

test "$ack" = OPENMITRASTAR_QTN_W3_NATIVE_OPEN_AP_RAM_ONLY || exit 171
case "$rollback_seconds" in ''|*[!0-9]*) exit 171 ;; esac
test "$rollback_seconds" -ge 120 && test "$rollback_seconds" -le 900 || exit 171
case "$commit_mode" in auto|deferred) ;; *) exit 171 ;; esac
mkdir -p "$root" /var/run/hostapd
chmod 0700 "$root"
test "$(sha_file "$hostapd")" = 338beaae1e3f3bc951b16d4bea1871d42d184170fc95f5efd200aa46e45dc269 || stop 172 reason=hostapd_hash
test "$(sha_file "$cli")" = 67df5a9d7e6484101ac29f25c8f178cdea2bef51d4ea3f6fcdeeebb9eb033504 || stop 172 reason=cli_hash
test "$(sha_file "$iwconfig")" = 5ebc31cb2ca69a1fbe1e0882f4aadba248e131a3b153c1d86d210ba53890c18b || stop 172 reason=iwconfig_hash
test "$(sha_file "$iwpriv")" = 94c0d675a2d18fd0c259eb713e6a69d99fe6b2f73f2f838dc2fca2c2bf5f4edd || stop 172 reason=iwpriv_hash
test "$(cat "$rf")" = 0 || stop 172 reason=rf_preopen
test "$(cat /sys/class/net/wifi0/operstate)" = down || stop 172 reason=wifi_not_down
management_path=
if test -e /sys/class/net/br0/brif/eth1_emac1; then
	management_path=vendor-switch-emac
elif test -e /sys/class/net/br0/brif/eth0 &&
	 dmesg | grep -Fq 'OMEMACSW stage=symbols-only-ready target=mitrastar,hgw-500bna-qcv2'; then
	management_path=direct-emac-preserved
else
	stop 172 reason=management_missing
fi
region=$($iwpriv wifi0 get_region | sed -n 's/.*get_region:\([0-9][0-9]*\).*/\1/p')
test "$region" = 21317 || stop 172 reason=region actual="$region"
$iwpriv wifi0 get_mode | grep -Eqi '11ac80' || stop 172 reason=mode
$iwconfig wifi0 | grep -q 'ESSID:"OpenMitraStar-5G"' || stop 172 reason=ssid
$iwconfig wifi0 | grep -q 'Frequency:5.18 GHz' || stop 172 reason=channel

conf=$root/hostapd.conf
{
	echo driver=madwifi
	echo interface=wifi0
	echo bridge=br0
	echo hw_mode=a
	echo channel=36
	echo ssid=OpenMitraStar-5G
	echo auth_algs=1
	echo wpa=0
	echo ctrl_interface=/var/run/hostapd
	echo logger_stdout=-1
	echo logger_stdout_level=0
} >"$conf"
chmod 0600 "$conf"
rm -f "$root/commit" "$root/hostapd.pid"

test -e /sys/class/net/br0/brif/wifi0 || brctl addif br0 wifi0
test -e /sys/class/net/br0/brif/wifi0 || stop 174 reason=bridge_attach
(
	sleep "$rollback_seconds"
	test -e "$root/commit" || sh "$rollback" "$root" timeout
) >/dev/null 2>&1 &
echo $! >"$root/rollback.pid"
chmod 0600 "$root/rollback.pid"
echo "OMNATIVEOPEN rollback-armed seconds=$rollback_seconds commit_mode=$commit_mode" >/dev/console

printf '1\n' >"$rf"
test "$(cat "$rf")" = 1 || stop 175 reason=rf_open
echo "OMNATIVEOPEN rf-open region=ES channel=36 bw=80 security=OPEN count=1" >/dev/console
if ! "$hostapd" -B -dd -P "$root/hostapd.pid" -f "$root/hostapd.log" "$conf"; then
	stop 175 reason=hostapd_start
fi

i=0
while [ "$i" -lt 30 ]; do
	i=$((i + 1))
	if [ -e /var/run/hostapd/wifi0 ]; then
		"$cli" -p /var/run/hostapd -i wifi0 ping >"$root/ping" 2>&1 || true
		"$cli" -p /var/run/hostapd -i wifi0 get_config >"$root/get_config" 2>&1 || true
		if grep -qx PONG "$root/ping" &&
		   grep -qx 'ssid=OpenMitraStar-5G' "$root/get_config" &&
		   ! grep -Eq '^key_mgmt=.*WPA' "$root/get_config" &&
		   ! grep -Eq '^(group_cipher|rsn_pairwise_cipher)=CCMP' "$root/get_config"; then
			break
		fi
	fi
	sleep 1
done
grep -qx PONG "$root/ping" || stop 176 reason=hostapd_no_pong
grep -qx 'ssid=OpenMitraStar-5G' "$root/get_config" || stop 176 reason=hostapd_config_ssid
! grep -Eq '^key_mgmt=.*WPA' "$root/get_config" || stop 176 reason=hostapd_not_open
! grep -Eq '^(group_cipher|rsn_pairwise_cipher)=CCMP' "$root/get_config" || stop 176 reason=hostapd_cipher_present
grep -Fq 'wifi0: Setup of interface done.' "$root/hostapd.log" || stop 176 reason=hostapd_setup_incomplete
test -s "$root/hostapd.pid" || stop 176 reason=pid_missing
pid=$(cat "$root/hostapd.pid")
kill -0 "$pid" || stop 176 reason=pid_dead
flags=$(cat /sys/class/net/wifi0/flags)
test $((flags & 0x41)) -eq 65 || stop 176 reason=wifi_not_up_running flags="$flags"
test "$(cat "$rf")" = 1 || stop 176 reason=rf_closed
case "$management_path" in
	vendor-switch-emac) test -e /sys/class/net/br0/brif/eth1_emac1 || stop 176 reason=management_lost ;;
	direct-emac-preserved) test -e /sys/class/net/br0/brif/eth0 || stop 176 reason=management_lost ;;
esac
if [ "$commit_mode" = auto ]; then
	touch "$root/commit"
	chmod 0600 "$root/commit"
fi
rm -f "$conf"
echo "OMNATIVEOPEN AP_READY ssid=OpenMitraStar-5G region=ES channel=36 bw=80 security=OPEN hostapd=PONG+CONFIG management=$management_path rollback_pending=$([ "$commit_mode" = deferred ] && echo 1 || echo 0)" >/dev/console
echo W3_QTN_NATIVE_OPEN_AP_EXPERIMENT_PASS=1
