#!/bin/sh
set -eu

root=${1:-/tmp/w3-qdrv-config-stage}
gate=${2:-/tmp/W3_QDRV_CONFIG_STAGE_GATE.env}
control=/sys/devices/qdrv/control
switch_state=/run/openmitrastar/switch-emac-handoff/status
firmware_state=/run/openmitrastar/qdrv-firmware-stage/status
config_state=/run/openmitrastar/qdrv-config-stage/status
power_dir=/etc/power_tables

value() { sed -n "s/^$1=//p" "$gate" | head -n 1; }
stop() { code=$1; shift; echo "W3_QDRV_CONFIG_STAGE_STOP code=$code $*" >/dev/console; exit "$code"; }
require_zero() { test "$(value "$1")" = 0 || stop 101 reason=unsafe_gate_open gate="$1"; }
sha_file()
{
	if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"
	elif test -x /bin/busybox; then /bin/busybox sha256sum "$1"
	else stop 103 reason=sha256_tool_missing
	fi
}
verify_file()
{
	file=$1
	expected_sha=$2
	test -f "$file" || stop 103 reason=artifact_missing file="$file"
	actual_sha=$(sha_file "$file" | awk '{print $1}')
	test "$actual_sha" = "$expected_sha" || stop 103 reason=sha256_mismatch file="$file"
}
control_set()
{
	command=$1
	printf '%s\n' "$command" >"$control" || stop 104 reason=control_write_failed index="$2"
	reply=$(cat "$control" 2>/dev/null || true)
	test "$reply" = ok || stop 104 reason=control_not_ok index="$2" reply="$reply"
	echo "W3_QDRV_CONFIG_STAGE stage=control-ok command_index=$2" >/dev/console
}

test "$(value W3_QDRV_CONFIG_STAGE_APPROVED)" = 1 || stop 101 reason=not_approved
test "$(value W3_QDRV_CONFIG_STAGE_ONLY)" = 1 || stop 101 reason=not_config_stage_only
test "$(value W3_RAM_ONLY)" = 1 || stop 101 reason=not_ram_only
test "$(value W3_WATCHDOG_REQUIRED)" = 1 || stop 101 reason=watchdog_not_required
test "$(value W3_PRIVATE_MAC_REQUIRED)" = 1 || stop 101 reason=private_mac_not_required
require_zero W3_RF_ENABLE
require_zero W3_FLASH_ENABLE
require_zero W3_WIFI_ENABLE
require_zero W3_VAP_ENABLE
require_zero W3_QDRV_CLEARSRAM_ENABLE
require_zero W3_QDRV_START_ENABLE

root_type=$(awk '$2 == "/" { print $3; exit }' /proc/mounts)
case "$root_type" in
	rootfs|tmpfs) ;;
	*) stop 102 reason=rootfs_not_ram type="$root_type" ;;
esac
etc_type=$(awk '$2 == "/etc" { print $3; exit }' /proc/mounts)
test -z "$etc_type" || test "$etc_type" = tmpfs || stop 102 reason=etc_not_ram type="$etc_type"
test "$(uname -r)" = "$(value W3_KERNEL_RELEASE)" || stop 102 reason=kernel_mismatch
grep -aq "$(value W3_TARGET_COMPATIBLE)" /proc/device-tree/compatible || stop 102 reason=target_mismatch
test "$(cat "$switch_state" 2>/dev/null)" = "$(value W3_SWITCH_HANDOFF_STATUS)" || stop 102 reason=switch_not_committed
test "$(cat "$firmware_state" 2>/dev/null)" = "$(value W3_FIRMWARE_STAGE_STATUS)" || stop 102 reason=firmware_stage_missing
grep -q '^switch_emac ' /proc/modules || stop 102 reason=switch_module_absent
grep -q '^qdrv ' /proc/modules || stop 102 reason=qdrv_not_loaded
test -e /sys/class/net/br0/brif/eth1_emac1 || stop 102 reason=management_emac_missing
test ! -e /sys/class/net/br0/brif/tqe || stop 102 reason=tqe_in_bridge
test ! -e /sys/class/net/wifi0 || stop 102 reason=vap_present
test -e "$control" || stop 102 reason=control_absent
test "$(cat "$control" 2>/dev/null)" = ok || stop 102 reason=control_not_ok_before_stage
dmesg | grep -q 'OMWDT stage=armed' || stop 102 reason=watchdog_not_armed
dmesg | grep -q 'OMWDT stage=pet first=1' || stop 102 reason=watchdog_not_pet

verify_file "$root/provenance/qdrv.ko" "$(value W3_QDRV_SHA256)"
verify_file "$root/power_tables/tx_power_QSR1000_es.txt" \
	"$(value W3_POWER_TABLE_SHA256)"
verify_file "$root/power_tables/power_table.conf" \
	"$(value W3_POWER_CONF_SHA256)"

mkdir -p "$power_dir"
cp "$root/power_tables/tx_power_QSR1000_es.txt" "$power_dir/tx_power_QSR1000_es.txt"
cp "$root/power_tables/power_table.conf" "$power_dir/power_table.conf"
chmod 0600 "$power_dir/tx_power_QSR1000_es.txt" "$power_dir/power_table.conf"
verify_file "$power_dir/tx_power_QSR1000_es.txt" \
	"$(value W3_POWER_TABLE_SHA256)"
verify_file "$power_dir/power_table.conf" \
	"$(value W3_POWER_CONF_SHA256)"

# The target BusyBox has SHA-256 but no MD5 applet.  The host gate pins both
# digests of the same local source; the target SHA-256 readback proves byte
# identity, so the paired MD5 below remains attributable without weakening the
# remote integrity check.
echo "W3_QDRV_CONFIG_STAGE stage=checksum-chain target_sha256=verified md5_source=host-pinned-same-bytes" >/dev/console

private_mac_file=$root/private/mac0addr
test -f "$private_mac_file" || stop 103 reason=private_mac_missing
chmod 0600 "$private_mac_file"
private_mac=$(sed -n '1{s/\r$//;p;}' "$private_mac_file")
test "${#private_mac}" = 17 || stop 103 reason=private_mac_invalid
printf '%s\n' "$private_mac" | grep -Eq '^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$' || stop 103 reason=private_mac_invalid
test "$private_mac" != '00:00:00:00:00:00' || stop 103 reason=private_mac_invalid
test "$private_mac" != 'ff:ff:ff:ff:ff:ff' || stop 103 reason=private_mac_invalid

control_set "set mac0addr $private_mac" 1
control_set "set power_table_checksum $power_dir/tx_power_QSR1000_es.txt $(value W3_POWER_TABLE_MD5)" 2
control_set "set lock_checksum_list 1" 3
unset private_mac

mkdir -p "${config_state%/*}"
printf 'configured\n' >"$config_state"
chmod 0600 "$config_state"
echo "W3_QDRV_CONFIG_STAGE stage=configured commands=3 ram_only=1 private_mac=redacted wdt=armed rf=blocked vap=blocked flash=blocked" >/dev/console
echo "W3_QDRV_CONFIG_STAGE_EXPERIMENT_PASS=1"
