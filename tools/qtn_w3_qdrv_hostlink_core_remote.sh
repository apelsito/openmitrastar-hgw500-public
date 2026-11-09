#!/bin/sh
set -eu

root=${1:-/tmp/w3-qdrv-hostlink-core}
gate=${2:-/tmp/W3_QDRV_HOSTLINK_CORE_GATE.env}
control=/sys/devices/qdrv/control
switch_state=/run/openmitrastar/switch-emac-handoff/status
power_dir=/etc/power_tables

value() { sed -n "s/^$1=//p" "$gate" | head -n 1; }
stop() { code=$1; shift; echo "W3_QDRV_HOSTLINK_CORE_STOP code=$code $*" >/dev/console; exit "$code"; }
load() { file=$1; shift; "$root/ram_insmod" "$root/$file" "$*"; }
sha_file() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else /bin/busybox sha256sum "$1"; fi; }
verify_file() { file=$1; expected=$2; test -f "$file" || stop 143 reason=file_missing file="$file"; actual=$(sha_file "$file" | awk '{print $1}'); test "$actual" = "$expected" || stop 143 reason=hash_mismatch file="$file" actual="$actual"; }
control_set()
{
	command=$1
	index=$2
	label=$3
	printf '%s\n' "$command" >"$control" || stop 145 reason=control_write_failed index="$index" label="$label"
	reply=$(cat "$control" 2>/dev/null || true)
	test "$reply" = ok || stop 145 reason=control_not_ok index="$index" label="$label" reply="$reply"
	echo "W3_QDRV_HOSTLINK_CORE stage=control-pass index=$index label=$label" >/dev/console
}

test "$(value W3_QDRV_HOSTLINK_CORE_APPROVED)" = 1 || stop 141 reason=not_approved
test "$(value W3_QDRV_HOSTLINK_CORE_ONLY)" = 1 || stop 141 reason=not_core_only
test "$(value W3_RAM_ONLY)" = 1 || stop 141 reason=not_ram_only
watchdog_required=$(value W3_WATCHDOG_REQUIRED)
case "$watchdog_required" in 0|1) ;; *) stop 141 reason=watchdog_gate_invalid ;; esac
test "$(value W3_PRIVATE_MAC_REQUIRED)" = 1 || stop 141 reason=private_mac_not_required
test "$(value W3_QDRV_SINGLE_INSTANCE)" = 1 || stop 141 reason=not_single_instance
test "$(value W3_QDRV_LOAD_COUNT)" = 1 || stop 141 reason=load_count_invalid
test "$(value W3_QDRV_COMMAND_COUNT)" = 9 || stop 141 reason=command_count_invalid
test "$(value W3_VAP_CREATE_COUNT)" = 0 || stop 141 reason=vap_create_count_invalid
test "$(value W3_NO_RMMOD)" = 1 || stop 141 reason=no_rmmod_policy_missing
for key in W3_RF_ENABLE W3_WIFI_ENABLE W3_VAP_ENABLE W3_FLASH_ENABLE; do
	test "$(value "$key")" = 0 || stop 141 reason=unsafe_gate_open gate="$key"
done

root_type=$(awk '$2 == "/" { print $3; exit }' /proc/mounts)
case "$root_type" in rootfs|tmpfs) ;; *) stop 142 reason=rootfs_not_ram type="$root_type" ;; esac
test "$(uname -r)" = "$(value W3_KERNEL_RELEASE)" || stop 142 reason=kernel_mismatch
grep -aq "$(value W3_TARGET_COMPATIBLE)" /proc/device-tree/compatible || stop 142 reason=target_mismatch
test "$(cat "$switch_state" 2>/dev/null)" = "$(value W3_SWITCH_HANDOFF_STATUS)" || stop 142 reason=switch_not_committed
management_mode=$(cat /run/openmitrastar/switch-emac-handoff/management-mode 2>/dev/null || echo switch-emac)
case "$management_mode" in
direct-preserved)
	test -e /sys/class/net/br0/brif/eth0 || stop 142 reason=direct_management_emac_missing
	test ! -e /sys/class/net/eth1_emac0 || stop 142 reason=unexpected_emac0_netdev
	test ! -e /sys/class/net/eth1_emac1 || stop 142 reason=unexpected_emac1_netdev
	test "$(cat /sys/module/switch_emac/parameters/w3_symbols_only)" = Y || stop 142 reason=symbols_only_gate_missing
	;;
switch-emac)
	test -e /sys/class/net/br0/brif/eth1_emac1 || stop 142 reason=management_emac_missing
	test ! -e /sys/class/net/br0/brif/tqe || stop 142 reason=tqe_in_bridge
	;;
*) stop 142 reason=management_mode_invalid mode="$management_mode" ;;
esac
grep -q '^switch_emac ' /proc/modules || stop 142 reason=switch_module_absent
if [ "$watchdog_required" = 1 ]; then
	dmesg | grep -q 'OMWDT stage=armed' || stop 142 reason=watchdog_not_armed
	dmesg | grep -q 'OMWDT stage=pet first=1' || stop 142 reason=watchdog_not_pet
else
	echo "W3_QDRV_HOSTLINK_CORE stage=no-hw-watchdog local-rollback-required=1" >/dev/console
fi
for dirty in qdrv wlan temp_sensor temp_sens; do grep -Eq "^${dirty} " /proc/modules && stop 142 reason=preexisting_qdrv_state module="$dirty"; done
test ! -e /sys/class/net/wifi0 || stop 142 reason=wifi0_present_before

verify_file "$root/provenance/qdrv-parent.ko" "$(value W3_QDRV_PARENT_SHA256)"
verify_file "$root/qdrv.ko" "$(value W3_QDRV_SHA256)"
verify_file "$root/firmware/qtn_driver.qtn_ruby.0.bin" "$(value W3_MUCFW_SHA256)"
verify_file "$root/firmware/auc_driver.nomu.0.bin" "$(value W3_AUCFW_SHA256)"
verify_file "$root/firmware/rdsp_driver.0.bin" "$(value W3_DSPFW_SHA256)"
verify_file "$root/regulatory/qtn_regulatory_db.bin" "$(value W3_REGDB_SHA256)"
verify_file "$root/power_tables/tx_power_QSR1000_es.txt" "$(value W3_POWER_TABLE_SHA256)"
verify_file "$root/power_tables/power_table.conf" "$(value W3_POWER_CONF_SHA256)"

private_mac_file=$root/private/mac0addr
test -f "$private_mac_file" || stop 143 reason=private_mac_missing
chmod 0600 "$private_mac_file"
private_mac=$(sed -n '1{s/\r$//;p;}' "$private_mac_file")
test "${#private_mac}" = 17 || stop 143 reason=private_mac_invalid
printf '%s\n' "$private_mac" | grep -Eq '^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$' || stop 143 reason=private_mac_invalid

mkdir -p /lib/firmware /etc "$power_dir"
cp "$root/firmware/qtn_driver.qtn_ruby.0.bin" /lib/firmware/qtn_driver.qtn_ruby.0.bin
cp "$root/firmware/auc_driver.nomu.0.bin" /lib/firmware/auc_driver.nomu.0.bin
cp "$root/firmware/rdsp_driver.0.bin" /lib/firmware/rdsp_driver.0.bin
cp "$root/regulatory/qtn_regulatory_db.bin" /etc/qtn_regulatory_db.bin
cp "$root/power_tables/tx_power_QSR1000_es.txt" "$power_dir/tx_power_QSR1000_es.txt"
cp "$root/power_tables/power_table.conf" "$power_dir/power_table.conf"
chmod 0600 /lib/firmware/qtn_driver.qtn_ruby.0.bin /lib/firmware/auc_driver.nomu.0.bin \
	/lib/firmware/rdsp_driver.0.bin /etc/qtn_regulatory_db.bin \
	"$power_dir/tx_power_QSR1000_es.txt" "$power_dir/power_table.conf"

before=$(dmesg | wc -l)
if grep -Eq '^gpio ' /proc/modules; then :; else load gpio.ko; fi
load temp_sensor.ko
load temp_sens.ko
load wlan.ko
load qdrv.ko "tqe_sem_en=1 openmitrastar_clearsram_only=0 openmitrastar_core_start_only=0 openmitrastar_sequential_bringup=1 openmitrastar_single_vap_create=0 openmitrastar_rf_enable=0"
test -e "$control" || stop 144 reason=control_absent
echo 0 >/sys/devices/qdrv/panic_on_muc_halt
test "$(cat /sys/devices/qdrv/panic_on_muc_halt)" = 0 || stop 144 reason=panic_control_readback
dmesg | grep -q 'OMQDRV stage=control-ready rf=blocked' || stop 144 reason=control_not_ready
test "$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable)" = 0 || stop 144 reason=rf_gate_open

control_set "set mucfw qtn_driver.qtn_ruby.0.bin" 1 firmware-muc
control_set "set fw_no_mu 1" 2 firmware-fw-no-mu
control_set "set aucfw auc_driver.nomu.0.bin" 3 firmware-auc
control_set "set dspfw rdsp_driver.0.bin" 4 firmware-dsp
control_set "set mac0addr $private_mac" 5 private-mac-redacted
control_set "set power_table_checksum $power_dir/tx_power_QSR1000_es.txt $(value W3_POWER_TABLE_MD5)" 6 power-checksum
control_set "set lock_checksum_list 1" 7 checksum-lock
control_set clearsram 8 clearsram
echo "W3_QDRV_HOSTLINK_CORE stage=start-enter qdrv_loads=1 rf=blocked vap=blocked" >/dev/console
control_set start 9 core-start
unset private_mac
sleep 2

after=$(dmesg | wc -l)
new=$((after - before))
test "$new" -gt 0 || stop 145 reason=no_new_dmesg
dmesg | tail -n "$new" >"$root/core.dmesg"
for marker in \
	'OMQDRVHLINK stage=alloc-pass' \
	'OMQDRVHLINK stage=publish' \
	'OMQDRVHLINK stage=complete' \
	'OMQDRVCORE stage=start-pass' \
	'OMQDRVSEQ stage=start-pass mask=0x7f rf=blocked vap=blocked'; do
	grep -Fq "$marker" "$root/core.dmesg" || stop 145 reason=marker_missing marker="$marker"
done
grep -Eq 'OMQDRVHLINK stage=alloc-pass .*original_dma=0x8[0-9a-f]+ .*wire_bus=0x[1-7][0-9a-f]+ .*muc_nocache=0x4[0-9a-f]+' "$root/core.dmesg" || stop 145 reason=hostlink_alloc_translation_invalid
grep -Eq 'OMQDRVHLINK stage=publish .*cmd=19 .*published=0x4[0-9a-f]+' "$root/core.dmesg" || stop 145 reason=calcmd_publish_invalid
grep -Eq 'OMQDRVHLINK stage=complete .*cmd=19 .*rc=1' "$root/core.dmesg" || stop 145 reason=calcmd_completion_missing
! grep -Eq 'HLINK MSG timed out.*cmd=19|MuC exception|forcing reboot|Kernel panic|Oops:|BUG:|Unable to handle|start-fail' "$root/core.dmesg" || stop 145 reason=fatal_or_calcmd_timeout
test ! -e /sys/class/net/wifi0 || stop 145 reason=wifi0_unexpected
test "$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable)" = 0 || stop 145 reason=rf_gate_changed
case "$management_mode" in
direct-preserved) test -e /sys/class/net/br0/brif/eth0 || stop 145 reason=direct_management_emac_lost ;;
switch-emac) test -e /sys/class/net/br0/brif/eth1_emac1 || stop 145 reason=management_emac_lost ;;
esac
if [ "$watchdog_required" = 1 ]; then
	dmesg | grep -q 'OMWDT stage=pet first=1' || stop 145 reason=watchdog_lost
fi
echo "W3_QDRV_HOSTLINK_CORE stage=complete qdrv_loads=1 commands=9 qdrv_left_loaded=1 no_rmmod=1 rf=blocked vap_created=0 management=present mode=$management_mode" >/dev/console
echo W3_QDRV_HOSTLINK_CORE_EXPERIMENT_PASS=1
