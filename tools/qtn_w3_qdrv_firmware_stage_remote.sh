#!/bin/sh
set -eu

root=${1:-/tmp/w3-qdrv-firmware-stage}
gate=${2:-/tmp/W3_QDRV_FIRMWARE_STAGE_GATE.env}
control=/sys/devices/qdrv/control
switch_state=/run/openmitrastar/switch-emac-handoff/status
stage_state=/run/openmitrastar/qdrv-firmware-stage/status

value() { sed -n "s/^$1=//p" "$gate" | head -n 1; }
stop() { code=$1; shift; echo "W3_QDRV_FIRMWARE_STAGE_STOP code=$code $*" >/dev/console; exit "$code"; }
require_zero() { test "$(value "$1")" = 0 || stop 101 reason=unsafe_gate_open gate="$1"; }
sha_file()
{
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$1"
	elif test -x /bin/busybox; then
		/bin/busybox sha256sum "$1"
	else
		stop 103 reason=sha256_tool_missing
	fi
}
verify_file()
{
	file=$1
	expected=$2
	test -f "$file" || stop 103 reason=artifact_missing file="$file"
	actual=$(sha_file "$file" | awk '{print $1}')
	test "$actual" = "$expected" || stop 103 reason=artifact_hash_mismatch file="$file" actual="$actual"
}
control_set()
{
	command=$1
	printf '%s\n' "$command" >"$control" || stop 104 reason=control_write_failed
	reply=$(cat "$control" 2>/dev/null || true)
	test "$reply" = ok || stop 104 reason=control_not_ok reply="$reply"
	echo "W3_QDRV_FIRMWARE_STAGE stage=control-ok command_index=$2" >/dev/console
}

test "$(value W3_QDRV_FIRMWARE_STAGE_APPROVED)" = 1 || stop 101 reason=not_approved
test "$(value W3_QDRV_FIRMWARE_STAGE_ONLY)" = 1 || stop 101 reason=not_firmware_stage_only
test "$(value W3_RAM_ONLY)" = 1 || stop 101 reason=not_ram_only
require_zero W3_RF_ENABLE
require_zero W3_FLASH_ENABLE
require_zero W3_WIFI_ENABLE
require_zero W3_QDRV_CLEARSRAM_ENABLE
require_zero W3_QDRV_START_ENABLE

test "$(uname -r)" = "$(value W3_KERNEL_RELEASE)" || stop 102 reason=kernel_mismatch
grep -aq "$(value W3_TARGET_COMPATIBLE)" /proc/device-tree/compatible || stop 102 reason=target_mismatch
test "$(cat "$switch_state" 2>/dev/null)" = "$(value W3_SWITCH_HANDOFF_STATUS)" || stop 102 reason=switch_not_committed
grep -q '^switch_emac ' /proc/modules || stop 102 reason=switch_module_absent
grep -q '^qdrv ' /proc/modules || stop 102 reason=qdrv_not_loaded
test -e /sys/class/net/br0/brif/eth1_emac1 || stop 102 reason=management_emac_missing
test ! -e /sys/class/net/br0/brif/tqe || stop 102 reason=tqe_in_bridge
test ! -e /sys/class/net/wifi0 || stop 102 reason=wifi_interface_present
test -e "$control" || stop 102 reason=control_absent
test "$(cat /sys/devices/qdrv/panic_on_muc_halt 2>/dev/null)" = 0 || stop 102 reason=panic_control_not_zero

verify_file "$root/provenance/qdrv.ko" "$(value W3_QDRV_SHA256)"
verify_file "/lib/firmware/qtn_driver.qtn_ruby.0.bin" "$(value W3_MUCFW_SHA256)"
verify_file "/lib/firmware/auc_driver.nomu.0.bin" "$(value W3_AUCFW_SHA256)"
verify_file "/lib/firmware/rdsp_driver.0.bin" "$(value W3_DSPFW_SHA256)"
if test "$(value W3_REGDB_AVAILABLE)" = 1; then
	verify_file "/etc/qtn_regulatory_db.bin" "$(value W3_REGDB_SHA256)"
fi

control_set "set mucfw qtn_driver.qtn_ruby.0.bin" 1
control_set "set fw_no_mu 1" 2
control_set "set aucfw auc_driver.nomu.0.bin" 3
control_set "set dspfw rdsp_driver.0.bin" 4

mkdir -p "${stage_state%/*}"
printf 'staged\n' >"$stage_state"
chmod 0600 "$stage_state"
echo "W3_QDRV_FIRMWARE_STAGE stage=staged qdrv_loaded=1 switch=committed ram_only=1 rf=blocked flash=blocked" >/dev/console
echo "W3_QDRV_FIRMWARE_STAGE_EXPERIMENT_PASS=1"
