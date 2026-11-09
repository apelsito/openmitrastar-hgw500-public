#!/bin/sh
set -eu

root=${1:-/tmp/w3-qdrv-sequential}
gate=${2:-/tmp/W3_QDRV_SEQUENTIAL_BRINGUP_GATE.env}
control=/sys/devices/qdrv/control
switch_state=/run/openmitrastar/switch-emac-handoff/status
power_dir=/etc/power_tables

value() { sed -n "s/^$1=//p" "$gate" | head -n 1; }
stop() { code=$1; shift; echo "W3_QDRV_SEQUENTIAL_STOP code=$code $*" >/dev/console; exit "$code"; }
load() { file=$1; shift; "$root/ram_insmod" "$root/$file" "$*"; }
sha_file() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else /bin/busybox sha256sum "$1"; fi; }
verify_file() { file=$1; expected=$2; test -f "$file" || stop 133 reason=file_missing file="$file"; actual=$(sha_file "$file" | awk '{print $1}'); test "$actual" = "$expected" || stop 133 reason=hash_mismatch file="$file" actual="$actual"; }
irq_count() { awk -v irq="$1:" '$1 == irq { for (i=2; i<=NF; i++) if ($i ~ /^[0-9]+$/) n += $i } END { print n+0 }' /proc/interrupts; }
control_set()
{
	command=$1
	index=$2
	label=$3
	printf '%s\n' "$command" >"$control" || stop 135 reason=control_write_failed index="$index" label="$label"
	reply=$(cat "$control" 2>/dev/null || true)
	test "$reply" = ok || stop 135 reason=control_not_ok index="$index" label="$label" reply="$reply"
	echo "W3_QDRV_SEQUENTIAL stage=control-pass index=$index label=$label" >/dev/console
}

test "$(value W3_QDRV_SEQUENTIAL_BRINGUP_APPROVED)" = 1 || stop 131 reason=not_approved
test "$(value W3_QDRV_SEQUENTIAL_BRINGUP_ONLY)" = 1 || stop 131 reason=not_sequential_only
test "$(value W3_RAM_ONLY)" = 1 || stop 131 reason=not_ram_only
test "$(value W3_WATCHDOG_REQUIRED)" = 1 || stop 131 reason=watchdog_not_required
test "$(value W3_PRIVATE_MAC_REQUIRED)" = 1 || stop 131 reason=private_mac_not_required
test "$(value W3_QDRV_SINGLE_INSTANCE)" = 1 || stop 131 reason=not_single_instance
test "$(value W3_QDRV_LOAD_COUNT)" = 1 || stop 131 reason=load_count_invalid
test "$(value W3_QDRV_COMMAND_COUNT)" = 10 || stop 131 reason=command_count_invalid
test "$(value W3_VAP_CREATE_COUNT)" = 1 || stop 131 reason=vap_create_count_invalid
test "$(value W3_NO_RMMOD)" = 1 || stop 131 reason=no_rmmod_policy_missing
for key in W3_RF_ENABLE W3_WIFI_ENABLE W3_VAP_ENABLE W3_FLASH_ENABLE; do
	test "$(value "$key")" = 0 || stop 131 reason=unsafe_gate_open gate="$key"
done

root_type=$(awk '$2 == "/" { print $3; exit }' /proc/mounts)
case "$root_type" in rootfs|tmpfs) ;; *) stop 132 reason=rootfs_not_ram type="$root_type" ;; esac
test "$(uname -r)" = "$(value W3_KERNEL_RELEASE)" || stop 132 reason=kernel_mismatch
grep -aq "$(value W3_TARGET_COMPATIBLE)" /proc/device-tree/compatible || stop 132 reason=target_mismatch
test "$(cat "$switch_state" 2>/dev/null)" = "$(value W3_SWITCH_HANDOFF_STATUS)" || stop 132 reason=switch_not_committed
test -e /sys/class/net/br0/brif/eth1_emac1 || stop 132 reason=management_emac_missing
test ! -e /sys/class/net/br0/brif/tqe || stop 132 reason=tqe_in_bridge
grep -q '^switch_emac ' /proc/modules || stop 132 reason=switch_module_absent
dmesg | grep -q 'OMWDT stage=armed' || stop 132 reason=watchdog_not_armed
dmesg | grep -q 'OMWDT stage=pet first=1' || stop 132 reason=watchdog_not_pet
for dirty in qdrv wlan temp_sensor temp_sens; do grep -Eq "^${dirty} " /proc/modules && stop 132 reason=preexisting_qdrv_state module="$dirty"; done
test ! -e /sys/class/net/wifi0 || stop 132 reason=wifi0_present_before

verify_file "$root/provenance/qdrv-parent.ko" "$(value W3_QDRV_PARENT_SHA256)"
verify_file "$root/qdrv.ko" "$(value W3_QDRV_SHA256)"
verify_file "$root/firmware/qtn_driver.qtn_ruby.0.bin" "$(value W3_MUCFW_SHA256)"
verify_file "$root/firmware/auc_driver.nomu.0.bin" "$(value W3_AUCFW_SHA256)"
verify_file "$root/firmware/rdsp_driver.0.bin" "$(value W3_DSPFW_SHA256)"
verify_file "$root/regulatory/qtn_regulatory_db.bin" "$(value W3_REGDB_SHA256)"
verify_file "$root/power_tables/tx_power_QSR1000_es.txt" "$(value W3_POWER_TABLE_SHA256)"
verify_file "$root/power_tables/power_table.conf" "$(value W3_POWER_CONF_SHA256)"

private_mac_file=$root/private/mac0addr
test -f "$private_mac_file" || stop 133 reason=private_mac_missing
chmod 0600 "$private_mac_file"
private_mac=$(sed -n '1{s/\r$//;p;}' "$private_mac_file")
test "${#private_mac}" = 17 || stop 133 reason=private_mac_invalid
printf '%s\n' "$private_mac" | grep -Eq '^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$' || stop 133 reason=private_mac_invalid
case "$private_mac" in 00:00:00:00:00:00|ff:ff:ff:ff:ff:ff|FF:FF:FF:FF:FF:FF) stop 133 reason=private_mac_invalid ;; esac

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
verify_file /lib/firmware/qtn_driver.qtn_ruby.0.bin "$(value W3_MUCFW_SHA256)"
verify_file /lib/firmware/auc_driver.nomu.0.bin "$(value W3_AUCFW_SHA256)"
verify_file /lib/firmware/rdsp_driver.0.bin "$(value W3_DSPFW_SHA256)"
verify_file /etc/qtn_regulatory_db.bin "$(value W3_REGDB_SHA256)"
verify_file "$power_dir/tx_power_QSR1000_es.txt" "$(value W3_POWER_TABLE_SHA256)"
verify_file "$power_dir/power_table.conf" "$(value W3_POWER_CONF_SHA256)"
echo "W3_QDRV_SEQUENTIAL stage=inputs-ready firmware=verified private_mac=redacted power=verified watchdog=armed" >/dev/console

before=$(dmesg | wc -l)
if grep -Eq '^gpio ' /proc/modules; then :; else load gpio.ko; fi
load temp_sensor.ko
load temp_sens.ko
load wlan.ko
load qdrv.ko "tqe_sem_en=1 openmitrastar_clearsram_only=0 openmitrastar_core_start_only=0 openmitrastar_sequential_bringup=1 openmitrastar_single_vap_create=1 openmitrastar_rf_enable=0"
test -e "$control" || stop 134 reason=control_absent
echo 0 >/sys/devices/qdrv/panic_on_muc_halt
test "$(cat /sys/devices/qdrv/panic_on_muc_halt)" = 0 || stop 134 reason=panic_control_readback
dmesg | grep -q 'OMQDRV stage=control-ready rf=blocked' || stop 134 reason=control_not_ready
test "$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable)" = 0 || stop 134 reason=rf_gate_open

control_set "set mucfw qtn_driver.qtn_ruby.0.bin" 1 firmware-muc
control_set "set fw_no_mu 1" 2 firmware-fw-no-mu
control_set "set aucfw auc_driver.nomu.0.bin" 3 firmware-auc
control_set "set dspfw rdsp_driver.0.bin" 4 firmware-dsp
control_set "set mac0addr $private_mac" 5 private-mac-redacted
control_set "set power_table_checksum $power_dir/tx_power_QSR1000_es.txt $(value W3_POWER_TABLE_MD5)" 6 power-checksum
control_set "set lock_checksum_list 1" 7 checksum-lock
control_set clearsram 8 clearsram
echo "W3_QDRV_SEQUENTIAL stage=start-enter qdrv_loads=1 rf=blocked vap=blocked" >/dev/console
control_set start 9 core-start
irq8_before=$(irq_count 8)
irq9_before=$(irq_count 9)
irq10_before=$(irq_count 10)
control_set "start 0 ap wifi0 $private_mac" 10 vap-create-private-mac
unset private_mac
irq8_after=$(irq_count 8)
irq9_after=$(irq_count 9)
irq10_after=$(irq_count 10)
for irq in 8 9 10; do
	eval before_irq=\$irq${irq}_before
	eval after_irq=\$irq${irq}_after
	delta=$((after_irq - before_irq))
	test "$delta" -ge 0 && test "$delta" -le 64 || stop 135 reason=irq_unstable hwirq="$irq" delta="$delta"
done

after=$(dmesg | wc -l)
new=$((after - before))
test "$new" -gt 0 || stop 135 reason=no_new_dmesg
dmesg | tail -n "$new" >"$root/sequential.dmesg"
for marker in \
	'OMQDRVSEQ stage=set-pass name=mucfw' \
	'OMQDRVSEQ stage=set-pass name=fw_no_mu' \
	'OMQDRVSEQ stage=set-pass name=aucfw' \
	'OMQDRVSEQ stage=set-pass name=dspfw' \
	'OMQDRVSEQ stage=set-pass name=mac0addr' \
	'OMQDRVSEQ stage=set-pass name=power_table_checksum' \
	'OMQDRVSEQ stage=set-pass name=lock_checksum_list mask=0x7f' \
	'OMQDRVCLR stage=complete regions=5 rf=blocked vap=blocked' \
	'OMQDRVSEQ stage=clearsram-pass mask=0x7f' \
	'OMQDRVCORE stage=hal-reset-enter' \
	'OMQDRVCORE stage=hal-reset-exit' \
	'OMQDRVSHM stage=wire-pass' \
	'OMQDRVSHM stage=publish-pass' \
	'OMQDRVIRQ stage=map name=QMAC0low hwirq=8' \
	'OMQDRVIRQ stage=map name=QMACDie hwirq=10' \
	'OMQDRVIRQ stage=map name=DSP(d2l) hwirq=9' \
	'OMQDRVDESC stage=pool-create path=tx' \
	'OMQDRVDESC stage=pool-create path=rx' \
	'OMQDRVCORE stage=start-pass' \
	'OMQDRVSEQ stage=start-pass mask=0x7f rf=blocked vap=blocked' \
	'OMQDRVSEQ stage=vap-pass unit=0 mode=ap interface=wifi0 rf=blocked count=1'; do
	grep -Fq "$marker" "$root/sequential.dmesg" || stop 135 reason=marker_missing marker="$marker"
done
for irq in 8 9 10; do
	grep -Eq "OMQDRVIRQ stage=request .* hwirq=$irq virq=[0-9]+ rc=0" "$root/sequential.dmesg" || stop 135 reason=irq_request_missing hwirq="$irq"
done
! grep -Eq 'BUG:|Oops:|Kernel panic|MuC exception|forcing reboot|start-fail|stage=request .* rc=-?[1-9]' "$root/sequential.dmesg" || stop 135 reason=fatal_runtime_marker
test -e /sys/class/net/wifi0 || stop 135 reason=wifi0_absent
wifi_state=$(cat /sys/class/net/wifi0/operstate 2>/dev/null || true)
test "$wifi_state" = down || stop 135 reason=wifi0_not_down state="$wifi_state"
wifi_count=$(find /sys/class/net -maxdepth 1 -type l -name 'wifi*' | wc -l)
test "$wifi_count" = 1 || stop 135 reason=extra_vap count="$wifi_count"
test "$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable)" = 0 || stop 135 reason=rf_gate_changed
test -e /sys/class/net/br0/brif/eth1_emac1 || stop 135 reason=management_emac_lost
dmesg | grep -q 'OMWDT stage=pet first=1' || stop 135 reason=watchdog_lost
echo "W3_QDRV_SEQUENTIAL stage=complete qdrv_loads=1 commands=10 qdrv_left_loaded=1 no_rmmod=1 rf=blocked vap_created=1 vap_opened=0 wifi0=$wifi_state management=present irq8_delta=$((irq8_after-irq8_before)) irq9_delta=$((irq9_after-irq9_before)) irq10_delta=$((irq10_after-irq10_before))" >/dev/console
echo W3_QDRV_SEQUENTIAL_BRINGUP_EXPERIMENT_PASS=1
