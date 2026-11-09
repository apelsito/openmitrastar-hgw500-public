#!/bin/sh
set -eu
umask 077

root=${1:-/tmp/w3-qcsapi-5g-ap}
gate_file=${2:-/tmp/W3_QCSAPI_5G_AP_GATE.env}
runtime=$root/runtime
private=$root/private
rf_gate=/sys/module/qdrv/parameters/openmitrastar_rf_enable
switch_state=/run/openmitrastar/switch-emac-handoff/status
rollback=$root/rollback.sh
bridge=
rf_enable=

value() { sed -n "s/^$1=//p" "$gate_file" | head -n 1; }
log() { echo "OMQCSAPI $*" >/dev/console; }
stop() { code=$1; shift; log "stop code=$code $*"; exit "$code"; }
sha_file() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else /bin/busybox sha256sum "$1"; fi; }
sha_stdin() { if command -v sha256sum >/dev/null 2>&1; then sha256sum; else /bin/busybox sha256sum; fi; }
irq_count() { awk -v irq="$1:" '$1 == irq { for (i=2; i<=NF; i++) if ($i ~ /^[0-9]+$/) n += $i } END { print n+0 }' /proc/interrupts; }

on_exit()
{
	rc=$?
	if test "$rc" -ne 0 && test -x "$rollback"; then
		sh "$rollback" "$root" script-failure "${bridge:-br0}" >/dev/null 2>&1 || true
	fi
}
trap on_exit EXIT HUP INT TERM

qc()
{
	LD_LIBRARY_PATH="$runtime/lib" \
		"$runtime/lib/ld-uClibc-0.9.29.so" "$runtime/bin/call_qcsapi" "$@"
}

qc_set()
{
	label=$1
	shift
	out=$private/qcsapi-set-$label.out
	if ! qc "$@" >"$out" 2>&1; then
		stop 153 reason=qcsapi_set_failed label="$label"
	fi
	rm -f "$out"
	log "set-pass label=$label rf=blocked"
}

qc_get()
{
	label=$1
	shift
	out=$private/qcsapi-get-$label.out
	if ! qc "$@" >"$out" 2>&1; then
		stop 154 reason=qcsapi_get_failed label="$label"
	fi
	tr -d '\r' <"$out" | sed '/^[[:space:]]*$/d' | tail -n 1
}

test "$(value W3_QCSAPI_5G_AP_APPROVED)" = 1 || stop 151 reason=not_approved
test "$(value W3_QCSAPI_5G_AP_ONLY)" = 1 || stop 151 reason=wrong_experiment
test "$(value W3_RAM_ONLY)" = 1 || stop 151 reason=not_ram_only
test "$(value W3_FLASH_ENABLE)" = 0 || stop 151 reason=flash_gate_open
test "$(value W3_PSK_BUNDLED)" = 0 || stop 151 reason=psk_bundled
test "$(value W3_PSK_FILE_MODE)" = 0600 || stop 151 reason=psk_mode_gate
test "$(value W3_TARGET_COMPATIBLE)" = mitrastar,hgw-500bna-qcv2 || stop 151 reason=target_gate
test "$(value W3_KERNEL_RELEASE)" = 5.10.260-openmitrastar-radiohw || stop 151 reason=kernel_gate
test "$(value W3_REGION)" = es || stop 151 reason=region_gate
test "$(value W3_CHANNEL)" = 36 || stop 151 reason=channel_gate
test "$(value W3_BANDWIDTH_MHZ)" = 80 || stop 151 reason=bandwidth_gate
test "$(value W3_DFS_BYPASS)" = 0 || stop 151 reason=dfs_bypass
test "$(value W3_SSID)" = OpenMitraStar-5G || stop 151 reason=ssid_gate
test "$(value W3_SECURITY)" = WPA2-PSK-AES || stop 151 reason=security_gate
test "$(value W3_BRIDGE)" = br0 || stop 151 reason=bridge_gate
test "$(value W3_RF_ENABLE)" = 1 || stop 151 reason=rf_enable_gate
test "$(value W3_RF_OPEN_COUNT)" = 1 || stop 151 reason=rf_open_count
test "$(value W3_LOCAL_ROLLBACK_REQUIRED)" = 1 || stop 151 reason=rollback_not_required
bridge=$(value W3_BRIDGE)
rf_enable=$(value W3_RF_ENABLE)

root_type=$(awk '$2 == "/" { print $3; exit }' /proc/mounts)
case "$root_type" in rootfs|tmpfs) ;; *) stop 152 reason=rootfs_not_ram type="$root_type" ;; esac
test "$(uname -r)" = "$(value W3_KERNEL_RELEASE)" || stop 152 reason=kernel_mismatch
grep -aq "$(value W3_TARGET_COMPATIBLE)" /proc/device-tree/compatible || stop 152 reason=target_mismatch
test "$(cat "$switch_state" 2>/dev/null)" = committed || stop 152 reason=switch_not_committed
test -e "/sys/class/net/$bridge/brif/eth1_emac1" || stop 152 reason=management_emac_missing
test ! -e "/sys/class/net/$bridge/brif/tqe" || stop 152 reason=tqe_in_bridge
grep -q '^qdrv ' /proc/modules || stop 152 reason=qdrv_absent
grep -q '^wlan ' /proc/modules || stop 152 reason=wlan_absent
test -e /sys/class/net/wifi0 || stop 152 reason=wifi0_absent
test "$(cat "$rf_gate")" = 0 || stop 152 reason=rf_not_blocked_initially
test "$(cat /sys/module/qdrv/parameters/openmitrastar_sequential_bringup)" = 1 || stop 152 reason=wrong_qdrv_mode
test "$(cat /sys/module/qdrv/parameters/openmitrastar_single_vap_create)" = 1 || stop 152 reason=vap_gate_not_consumed
test "$(cat /sys/class/net/wifi0/operstate 2>/dev/null)" = down || stop 152 reason=wifi0_not_down_initially
grep -q '^wlan_scan_ap ' /proc/modules || stop 152 reason=wlan_scan_ap_absent
test -e /proc/device-tree/soc/recovery@e0000000/mitrastar,product-watchdog-canary || stop 152 reason=watchdog_dt_opt_in_absent
uptime_s=$(awk '{print int($1)}' /proc/uptime)
test "$uptime_s" -ge 60 || stop 152 reason=watchdog_uptime_too_short uptime="$uptime_s"
test ! -e /var/run/hostapd/wifi0 || stop 152 reason=preexisting_wifi0_hostapd_control

mkdir -p "$private" /var/run/hostapd
chmod 0700 "$private"
manifest=$runtime/manifest.sha256
test -f "$manifest" || stop 153 reason=runtime_manifest_missing
actual_manifest=$(sha_file "$manifest" | awk '{print $1}')
test "$actual_manifest" = "$(value W3_RUNTIME_MANIFEST_SHA256)" || stop 153 reason=runtime_manifest_mismatch
if command -v sha256sum >/dev/null 2>&1; then
	(cd "$runtime" && sha256sum -c manifest.sha256 >"$private/runtime.verify" 2>&1) || stop 153 reason=runtime_hash_failure
else
	(cd "$runtime" && /bin/busybox sha256sum -c manifest.sha256 >"$private/runtime.verify" 2>&1) || stop 153 reason=runtime_hash_failure
fi

for link in \
	ld-uClibc.so.0:ld-uClibc-0.9.29.so \
	libc.so.0:libuClibc-0.9.29.so \
	libpthread.so.0:libpthread-0.9.29.so \
	libm.so.0:libm-0.9.29.so \
	libdl.so.0:libdl-0.9.29.so \
	librt.so.0:librt-0.9.29.so \
	libz.so.1:libz.so.1.2.3 \
	libqcsapi.so.1:libqcsapi.so.1.0.1 \
	libcall_qcsapi.so.1:libcall_qcsapi.so.1.0.1; do
	name=${link%%:*}
	target=${link#*:}
	ln -sf "$target" "$runtime/lib/$name"
done
chmod 0700 "$runtime/bin/call_qcsapi" "$runtime/bin/hostapd" "$runtime/bin/hostapd_cli" \
	"$runtime/lib/ld-uClibc-0.9.29.so" "$rollback"

psk_file=$private/wpa2.psk
test -f "$psk_file" || stop 153 reason=psk_file_missing
mode=$(ls -l "$psk_file" | awk '{print $1}')
test "$mode" = -rw------- || stop 153 reason=psk_file_mode actual="$mode"
psk=$(sed -n '1{s/\r$//;p;}' "$psk_file")
psk_len=${#psk}
test "$psk_len" -ge 8 && test "$psk_len" -le 63 || stop 153 reason=psk_length_invalid
printf '%s\n' "$psk" | LC_ALL=C grep -Eq '^[ -~]{8,63}$' || stop 153 reason=psk_charset_invalid
psk_sha=$(printf '%s' "$psk" | sha_stdin | awk '{print $1}')

hostapd_conf=$private/hostapd.conf
{
	printf '%s\n' 'driver=madwifi'
	printf '%s\n' 'interface=wifi0'
	printf 'bridge=%s\n' "$bridge"
	printf '%s\n' 'hw_mode=a'
	printf '%s\n' 'channel=36'
	printf '%s\n' 'ssid=OpenMitraStar-5G'
	printf '%s\n' 'wpa=2'
	printf '%s\n' 'wpa_key_mgmt=WPA-PSK'
	printf '%s\n' 'wpa_pairwise=CCMP'
	printf 'wpa_passphrase=%s\n' "$psk"
	printf '%s\n' 'auth_algs=1'
	printf '%s\n' 'ieee80211w=0'
	printf '%s\n' 'wpa_group_rekey=0'
	printf '%s\n' "pid_file=$private/hostapd.pid"
	printf '%s\n' 'ctrl_interface=/var/run/hostapd'
	printf '%s\n' 'logger_syslog=-1'
	printf '%s\n' 'logger_syslog_level=3'
	printf '%s\n' 'logger_stdout=-1'
	printf '%s\n' 'logger_stdout_level=3'
} >"$hostapd_conf"
chmod 0600 "$hostapd_conf"
unset psk
rm -f "$psk_file"
log "runtime-ready abi=ARC700-uClibc-0.9.29 hashes=verified psk=validated-redacted"

mode_before=$(qc_get mode-before get_mode wifi0)
printf '%s\n' "$mode_before" | grep -Eqi '(^ap$|access[[:space:]]+point)' || stop 154 reason=wifi0_not_ap value="$mode_before"
channels_file=$private/qcsapi-get-channels-es-80.out
qc get_regulatory_channels es 80 >"$channels_file" 2>&1 || stop 154 reason=regulatory_channels_query_failed
grep -Eq '(^|[^0-9])36([^0-9]|$)' "$channels_file" || stop 154 reason=channel36_not_allowed
regdb=$(qc_get regdb-version get_regulatory_db_version)
test -n "$regdb" || stop 154 reason=regdb_version_empty

qc_set regulatory-region set_regulatory_region wifi0 es
qc_set bandwidth set_bw wifi0 80
qc_set channel set_channel wifi0 36
qc_set ssid set_SSID wifi0 OpenMitraStar-5G

test "$(cat "$rf_gate")" = 0 || stop 155 reason=rf_opened_during_configuration
test "$(cat /sys/class/net/wifi0/operstate 2>/dev/null)" = down || stop 155 reason=wifi0_opened_during_configuration

if test ! -e "/sys/class/net/$bridge/brif/wifi0"; then
	if command -v brctl >/dev/null 2>&1; then
		brctl addif "$bridge" wifi0
	else
		/bin/busybox brctl addif "$bridge" wifi0
	fi
fi
test -e "/sys/class/net/$bridge/brif/wifi0" || stop 155 reason=bridge_attach_failed

before_dmesg=$(dmesg | wc -l)
irq8_before=$(irq_count 8)
irq9_before=$(irq_count 9)
irq10_before=$(irq_count 10)
rm -f "$root/commit"
rollback_seconds=$(value W3_ROLLBACK_SECONDS)
case "$rollback_seconds" in ''|*[!0-9]*) stop 155 reason=rollback_seconds_invalid ;; esac
(
	sleep "$rollback_seconds"
	test -e "$root/commit" || sh "$rollback" "$root" timeout "$bridge"
) >/dev/null 2>&1 &
echo $! >"$private/rollback-watchdog.pid"
chmod 0600 "$private/rollback-watchdog.pid"
log "rollback-armed seconds=$rollback_seconds management=eth1_emac1"

# This is the only transition that permits vnet_init() to open the radio.
printf '%s\n' "$rf_enable" >"$rf_gate"
test "$(cat "$rf_gate")" = "$rf_enable" || stop 156 reason=rf_gate_write_failed
log "rf-gate-open value=$rf_enable count=1 region=es channel=36 bw=80"

hostapd_log=$private/hostapd.start.log
if ! LD_LIBRARY_PATH="$runtime/lib" \
	"$runtime/lib/ld-uClibc-0.9.29.so" "$runtime/bin/hostapd" -B "$hostapd_conf" \
	>"$hostapd_log" 2>&1; then
	stop 156 reason=hostapd_start_failed
fi

ready=0
i=0
while test "$i" -lt 30; do
	i=$((i + 1))
	if test -S /var/run/hostapd/wifi0 || test -e /var/run/hostapd/wifi0; then
		status=$private/hostapd.status
		if LD_LIBRARY_PATH="$runtime/lib" \
			"$runtime/lib/ld-uClibc-0.9.29.so" "$runtime/bin/hostapd_cli" \
			-p /var/run/hostapd -i wifi0 status >"$status" 2>&1 && \
			grep -Eq '^(state=ENABLED|hostapd_state=ENABLED)$' "$status"; then
			ready=1
			break
		fi
	fi
	sleep 1
done
test "$ready" = 1 || stop 156 reason=hostapd_not_enabled
test -s "$private/hostapd.pid" || stop 156 reason=hostapd_pid_missing
hostapd_pid=$(sed -n '1p' "$private/hostapd.pid")
case "$hostapd_pid" in ''|*[!0-9]*) stop 156 reason=hostapd_pid_invalid ;; esac
kill -0 "$hostapd_pid" >/dev/null 2>&1 || stop 156 reason=hostapd_pid_not_live

region=$(qc_get region get_regulatory_region wifi0)
channel=$(qc_get channel get_channel wifi0)
bw=$(qc_get bandwidth get_bw wifi0)
ssid=$(qc_get ssid get_SSID wifi0)
beacon=$(qc_get beacon get_beacon_type wifi0)
auth=$(qc_get authentication get_IEEE11i_authentication_mode wifi0)
cipher=$(qc_get encryption get_IEEE11i_encryption_modes wifi0)
ready_state=$(qc_get wifi-ready is_wifi_ready wifi0)
associations=$(qc_get associations get_count_associations wifi0)

test "$(printf '%s' "$region" | tr '[:upper:]' '[:lower:]')" = es || stop 157 reason=region_readback value="$region"
test "$channel" = 36 || stop 157 reason=channel_readback value="$channel"
test "$bw" = 80 || stop 157 reason=bandwidth_readback value="$bw"
test "$ssid" = OpenMitraStar-5G || stop 157 reason=ssid_readback value="$ssid"
test "$beacon" = 11i || stop 157 reason=beacon_readback value="$beacon"
test "$auth" = PSKAuthentication || stop 157 reason=authentication_readback value="$auth"
test "$cipher" = AESEncryption || stop 157 reason=encryption_readback value="$cipher"
test "$ready_state" = 1 || stop 157 reason=wifi_ready_readback value="$ready_state"
case "$associations" in ''|*[!0-9]*) stop 157 reason=association_readback value="$associations" ;; esac

pass_readback=$private/qcsapi-passphrase.readback
qc get_key_passphrase wifi0 0 >"$pass_readback" 2>/dev/null || stop 157 reason=passphrase_readback_failed
chmod 0600 "$pass_readback"
readback_sha=$(tr -d '\r\n' <"$pass_readback" | sha_stdin | awk '{print $1}')
test "$readback_sha" = "$psk_sha" || stop 157 reason=passphrase_readback_mismatch
rm -f "$pass_readback" "$hostapd_conf"
unset psk_sha readback_sha

test -e "/sys/class/net/$bridge/brif/wifi0" || stop 157 reason=wifi0_not_in_bridge
test -e "/sys/class/net/$bridge/brif/eth1_emac1" || stop 157 reason=management_emac_lost
test "$(cat "$rf_gate")" = "$rf_enable" || stop 157 reason=rf_gate_closed_unexpectedly
test "$(cat /sys/class/net/wifi0/operstate 2>/dev/null)" != down || stop 157 reason=wifi0_still_down
ping -c 3 -W 2 "$(value W3_MANAGEMENT_HOST)" >"$private/management.ping" 2>&1 || stop 157 reason=management_ping_failed
dmesg | grep -q 'OMWDT stage=pet first=1' || stop 157 reason=watchdog_lost

after_dmesg=$(dmesg | wc -l)
new_lines=$((after_dmesg - before_dmesg))
test "$new_lines" -ge 0 || stop 157 reason=dmesg_counter_invalid
if test "$new_lines" -gt 0; then
	dmesg | tail -n "$new_lines" >"$root/ap-open.dmesg"
	! grep -Eq 'BUG:|Oops:|Kernel panic|Unable to handle|MuC.*halt|DMA.*error' "$root/ap-open.dmesg" || stop 157 reason=fatal_runtime_marker
fi
irq8_after=$(irq_count 8)
irq9_after=$(irq_count 9)
irq10_after=$(irq_count 10)
for irq in 8 9 10; do
	eval before=\$irq${irq}_before
	eval after=\$irq${irq}_after
	delta=$((after - before))
	test "$delta" -ge 0 && test "$delta" -le 100000 || stop 157 reason=irq_delta_invalid hwirq="$irq" delta="$delta"
done

log "ap-armed ssid=OpenMitraStar-5G region=es channel=36 bw=80 security=WPA2-PSK-AES hostapd=ENABLED process=wifi0-isolated bridge=$bridge rf_enable=$rf_enable psk=redacted rollback=pending irq8_delta=$((irq8_after-irq8_before)) irq9_delta=$((irq9_after-irq9_before)) irq10_delta=$((irq10_after-irq10_before))"
echo "W3_QCSAPI_5G_AP_ARMED_PASS=1 rollback_pending=1 psk=redacted"
