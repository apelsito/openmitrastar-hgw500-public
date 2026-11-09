#!/bin/ash

set -eu
PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH

state=/run/openmitrastar/w5-cold-visibility
watchdog_pid=$state/watchdog.pid
commit=$state/commit
local_pass=$state/local-pass
hostapd_state=/run/openmitrastar/radio5g
ctrl=/var/run/hostapd
rf=/sys/module/qdrv/parameters/openmitrastar_rf_enable
led=/sys/class/leds/openmitrastar:green:wlan5g

arm()
{
	mkdir -p "$state"
	chmod 0700 "$state"
	if [ -s "$watchdog_pid" ]; then
		old=$(cat "$watchdog_pid" 2>/dev/null || true)
		case "$old" in ''|*[!0-9]*) ;; *) kill "$old" >/dev/null 2>&1 || true ;; esac
	fi
	rm -f "$commit" "$local_pass" "$watchdog_pid"
	(
		sleep 120
		if [ ! -e "$commit" ]; then
			printf '%s\n' 'OMW5_VISIBILITY_ROLLBACK reason=commit-timeout seconds=120' >/dev/console 2>/dev/null || true
			reboot -f
		fi
	) >/dev/null 2>&1 &
	printf '%s\n' "$!" >"$watchdog_pid"
	chmod 0600 "$watchdog_pid"
	printf '%s\n' 'OMW5_VISIBILITY_WATCHDOG_ARMED seconds=120 flash=0'
}

check()
{
	test -s "$watchdog_pid"
	pid=$(cat "$watchdog_pid")
	kill -0 "$pid"
	test "$(cat /run/openmitrastar/radio5g/state)" = ready
	test "$(cat "$rf")" = 1
	test "$(cat /sys/module/switch_tqe/parameters/w3_rx_ring_entries)" = 256
	test "$(( $(cat /sys/class/net/wifi0/flags) & 0x41 ))" -eq 65
	test "$(cat /sys/class/net/wifi0/carrier)" = 1
	test -e /sys/class/net/br0/brif/eth0
	test -e /sys/class/net/br0/brif/wlan0
	test -e /sys/class/net/br0/brif/wifi0
	test "$(cat "$led/brightness")" = "$(cat "$led/max_brightness")"
	test "$(/usr/sbin/hostapd-cli-qtn -p "$ctrl" -i wifi0 ping)" = PONG
	/usr/sbin/hostapd-cli-qtn -p "$ctrl" -i wifi0 get_config >"$state/hostapd.get_config"
	grep -Fqx 'ssid=MOVISTAR_PLUS_55CB' "$state/hostapd.get_config"
	! grep -Eqi '^key_mgmt=.*WPA' "$state/hostapd.get_config"
	! grep -Eqi 'CCMP' "$state/hostapd.get_config"
	! grep -Eq '^wpa=[1-9]' "$state/hostapd.get_config"
	grep -q 'get_region:21317' <<EOF
$(/usr/sbin/iwpriv-qtn wifi0 get_region)
EOF
	/usr/sbin/iwpriv-qtn wifi0 get_mode | grep -Eqi '11ac80'
	/usr/sbin/iwconfig-qtn wifi0 | grep -Fq 'Frequency:5.18 GHz'
	dmesg | grep -Eq 'OMQDRVBC stage=preflight-pass .*count=[0-9]+ total=[0-9]+ used=[0-9]+ beacon_len=[0-9]+ head_dma=0x[0-9a-f]+ args_dma=0x[0-9a-f]+'
	dmesg | grep -Eq 'OMQDRVBC stage=ioctl-send count=[0-9]+ command=[0-9]+ arg1=[0-9]+ arg2=0x[0-9a-f]+ argp=0x[0-9a-f]+'
	! dmesg | grep -Eq 'OMQDRVBC stage=preflight-fail|OMQDRVBC stage=quarantined|OMQDRVHLINK stage=quarantine|No DDR heap memory for beacon buffer|HLINK MSG timed out .*cmd=6|MuC exception|forcing reboot|Kernel panic|Oops:|BUG:|Unable to handle|EV_TLB|EV_ProtV'
	irq_before=$(awk '$1 == "8:" {print $2}' /proc/interrupts)
	tx_before=$(cat /sys/class/net/wifi0/statistics/tx_packets)
	sleep 5
	irq_after=$(awk '$1 == "8:" {print $2}' /proc/interrupts)
	tx_after=$(cat /sys/class/net/wifi0/statistics/tx_packets)
	test "$irq_after" -gt "$irq_before"
	test "$tx_after" -gt "$tx_before"
	printf 'boot_id=%s\nirq8_delta=%s\nwifi0_tx_delta=%s\n' \
		"$(cat /proc/sys/kernel/random/boot_id)" "$((irq_after - irq_before))" "$((tx_after - tx_before))" >"$local_pass"
	chmod 0600 "$local_pass"
	cat "$local_pass"
	printf '%s\n' 'Q3_VISIBILITY_LOCAL_PASS ssid=MOVISTAR_PLUS_55CB security=OPEN region=ES channel=36 width=80 flash=0'
}

commit_visible()
{
	test "${1:-}" = visible
	test -s "$local_pass"
	touch "$commit"
	chmod 0600 "$commit"
	if [ -s "$watchdog_pid" ]; then
		pid=$(cat "$watchdog_pid")
		kill "$pid" >/dev/null 2>&1 || true
	fi
	rm -f "$watchdog_pid"
	printf '%s\n' 'Q3_VISIBILITY_COMMIT_PASS external_ssid_visible=1 flash=0'
}

case "${1:-}" in
arm) arm ;;
check) check ;;
commit) commit_visible "${2:-}" ;;
*) echo 'usage: q3_open_lab_visibility_gate_remote.sh arm|check|commit visible' >&2; exit 2 ;;
esac
