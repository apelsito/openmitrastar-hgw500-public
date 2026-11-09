#!/bin/sh
set -eu
root=${1:-/tmp/w3-qtn-reflect};gate=${2:-/tmp/W3_FWT_REFLECT_PROBE_GATE.env}
value(){ sed -n "s/^$1=//p" "$gate"|head -n1; };stop(){ c=$1;shift;echo "W3_REFLECT_STOP code=$c $*";exit "$c"; }
test "$(value W3_FWT_REFLECT_PROBE_APPROVED)" = 1||stop 111 reason=not_approved
test "$(value W3_FWT_TDES_PROBE_REJECTED)" = 1||stop 111 reason=tdes_not_rejected
test "$(value W3_HARDWARE_ACTIVE_APPROVED)" = 0||stop 111 reason=broader_gate
for m in hbm topaz_congest_queue switch_tqe fwt_ctrl qdrv wlan;do grep -Eq "^$m " /proc/modules&&stop 112 reason=dirty module=$m;done
rollback(){ set +e;rmmod fwt_ctrl 2>/dev/null;rmmod switch_tqe 2>/dev/null;rmmod topaz_congest_queue 2>/dev/null;rmmod hbm 2>/dev/null;for m in fwt_if switch_vlan dmautil iputil qtn_platform_support runtime_compat board_compat qtn_pm_qos_compat;do rmmod $m 2>/dev/null;done;echo W3_REFLECT_ROLLBACK_COMPLETE;};trap rollback EXIT INT TERM
load(){ m=$1;shift;if [ $# -gt 0 ];then "$root/ram_insmod" "$root/$m" "$*";else "$root/ram_insmod" "$root/$m";fi; }
load qtn_pm_qos_compat.ko;load board_compat.ko board_id=65535 emac0=1 emac1=1 wifi_hw=7 rfic=4 calstate=3 ext_lna_gain=12 ext_lna_bypass_gain=-5 tx_power_cal=0 min_tx_power=7 max_tx_power=21 allow_dram_sram_fallback=1;load runtime_compat.ko;load qtn_platform_support.ko;load iputil.ko;load dmautil.ko;load switch_vlan.ko;load fwt_if.ko;load hbm.ko w3_hbm_lifecycle_enable=1;load topaz_congest_queue.ko;load switch_tqe.ko w3_switch_tqe_only_enable=1
load fwt_ctrl.ko w3_fwt_ctrl_only_enable=1 w3_fwt_reflect_probe_only=1
grep -Eq '^fwt_ctrl ' /proc/modules||stop 113 reason=probe_absent
for marker in 'OMFWTREF stage=reflect-program' 'OMFWTREF stage=result' 'restore_ok=1';do dmesg|grep -q "$marker"||stop 113 reason=marker_absent marker="$marker";done
! dmesg|grep -q 'OMFWT stage=table-cleared-hash-enabled'||stop 113 reason=unexpected_fwt_write
! dmesg|grep -q 'OMFWT stage=hooks-registered'||stop 113 reason=unexpected_hooks
! grep -Eq '^(qdrv|wlan) ' /proc/modules||stop 113 reason=forbidden_loaded
dmesg|tail -n240;rmmod fwt_ctrl;dmesg|grep -q 'OMFWTPREQ stage=module-exit' || stop 114 reason=exit_marker_absent
trap - EXIT INT TERM;rollback;echo W3_FWT_REFLECT_PROBE_PASS
