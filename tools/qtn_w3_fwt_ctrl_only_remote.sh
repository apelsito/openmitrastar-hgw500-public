#!/bin/sh
set -eu
root=${1:-/tmp/w3-qtn-fwt}
gate=${2:-/tmp/W3_FWT_CTRL_ONLY_GATE.env}
value(){ sed -n "s/^$1=//p" "$gate"|head -n1; }
stop(){ c=$1;shift;echo "W3_FWT_STOP code=$c $*";exit "$c"; }
test "$(value W3_FWT_CTRL_ONLY_APPROVED)" = 1 || stop 91 reason=fwt_not_approved
test "$(value W3_SWITCH_TQE_DRAMLAB_PROVEN)" = 1 || stop 91 reason=switch_not_proven
test "$(value W3_HARDWARE_ACTIVE_APPROVED)" = 0 || stop 91 reason=broader_gate_must_remain_zero
test "$(uname -r)" = "$(value W3_KERNEL_RELEASE)" || stop 92 reason=kernel_mismatch
for m in hbm topaz_congest_queue switch_tqe fwt_ctrl qdrv wlan gpio temp_sens temp_sensor;do grep -Eq "^$m " /proc/modules&&stop 92 reason=dirty_state module=$m;done
rollback(){ set +e;rmmod fwt_ctrl 2>/dev/null;rmmod switch_tqe 2>/dev/null;rmmod topaz_congest_queue 2>/dev/null;rmmod hbm 2>/dev/null;for m in fwt_if switch_vlan dmautil iputil qtn_platform_support runtime_compat board_compat qtn_pm_qos_compat;do rmmod $m 2>/dev/null;done;echo W3_FWT_ROLLBACK_COMPLETE; }
trap rollback EXIT INT TERM
load(){ m=$1;shift;if [ $# -gt 0 ];then "$root/ram_insmod" "$root/$m" "$*";else "$root/ram_insmod" "$root/$m";fi; }
load qtn_pm_qos_compat.ko
load board_compat.ko board_id=65535 emac0=1 emac1=1 wifi_hw=7 rfic=4 calstate=3 ext_lna_gain=12 ext_lna_bypass_gain=-5 tx_power_cal=0 min_tx_power=7 max_tx_power=21 allow_dram_sram_fallback=1
load runtime_compat.ko;load qtn_platform_support.ko;load iputil.ko;load dmautil.ko;load switch_vlan.ko;load fwt_if.ko;load hbm.ko w3_hbm_lifecycle_enable=1;load topaz_congest_queue.ko;load switch_tqe.ko w3_switch_tqe_only_enable=1
grep -Eq '^switch_tqe ' /proc/modules||stop 93 reason=switch_absent
echo W3_FWT_BASELINE_PASS
load fwt_ctrl.ko w3_fwt_ctrl_only_enable=1
grep -Eq '^fwt_ctrl ' /proc/modules||stop 94 reason=fwt_absent
for marker in 'OMFWT stage=gate-pass' 'OMFWT stage=snapshot entries=' 'OMFWT stage=table-cleared-hash-enabled' 'OMFWT stage=timestamp-enabled' 'OMFWT stage=hooks-registered' 'OMFWT stage=ready';do dmesg|grep -q "$marker"||stop 94 reason=marker_absent marker="$marker";done
! grep -Eq '^(qdrv|wlan|gpio|temp_sens|temp_sensor) ' /proc/modules||stop 94 reason=forbidden_loaded
sleep 3
! dmesg|tail -n300|grep -Eq 'BUG:|Oops:|Kernel panic|use-after-free|restore-failed'||stop 94 reason=fatal_marker
echo W3_FWT_CTRL_ONLY_LOADED
rmmod fwt_ctrl
for marker in 'OMFWT stage=interface-cleanup' 'OMFWT stage=ipmac-cleanup' 'OMFWT stage=restore-readback rc=0' 'OMFWT stage=exit-complete';do dmesg|grep -q "$marker"||stop 95 reason=restore_marker_absent marker="$marker";done
! grep -Eq '^fwt_ctrl ' /proc/modules||stop 95 reason=fwt_unload_failed
echo W3_FWT_CTRL_ONLY_UNLOADED
trap - EXIT INT TERM;rollback;echo W3_FWT_CTRL_ONLY_PASS
