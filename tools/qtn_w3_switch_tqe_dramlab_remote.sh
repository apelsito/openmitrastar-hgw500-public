#!/bin/sh
set -eu
root=${1:-/tmp/w3-qtn-dramlab}
gate=${2:-/tmp/W3_SWITCH_TQE_DRAMLAB_GATE.env}
value() { sed -n "s/^$1=//p" "$gate" | head -n 1; }
stop() { code=$1; shift; echo "W3_DRAMLAB_STOP code=$code $*"; exit "$code"; }

test "$(value W3_SWITCH_TQE_DRAMLAB_APPROVED)" = 1 || stop 81 reason=lab_not_approved
test "$(value W3_PAIR_APPROVED)" = 1 || stop 81 reason=pair_not_approved
test "$(value W3_HBM_ONLY_PROVEN)" = 1 || stop 81 reason=hbm_not_proven
test "$(value W3_CONGEST_ONLY_PROVEN)" = 1 || stop 81 reason=congest_not_proven
test "$(value W3_PRODUCTION_SRAM_READY)" = 0 || stop 81 reason=lab_must_not_claim_production_sram
test "$(value W3_HARDWARE_ACTIVE_APPROVED)" = 0 || stop 81 reason=broader_gate_must_remain_zero
test "$(uname -r)" = "$(value W3_KERNEL_RELEASE)" || stop 82 reason=kernel_mismatch
for forbidden in hbm topaz_congest_queue switch_tqe fwt_ctrl qdrv wlan gpio temp_sens temp_sensor; do grep -Eq "^${forbidden} " /proc/modules && stop 82 reason=dirty_state module="$forbidden"; done

rollback() { set +e; rmmod switch_tqe 2>/dev/null; rmmod topaz_congest_queue 2>/dev/null; rmmod hbm 2>/dev/null; for m in fwt_if switch_vlan dmautil iputil qtn_platform_support runtime_compat board_compat qtn_pm_qos_compat; do rmmod "$m" 2>/dev/null; done; echo W3_DRAMLAB_ROLLBACK_COMPLETE; }
trap rollback EXIT INT TERM
load_module() { m=$1; shift; if [ "$#" -gt 0 ]; then "$root/ram_insmod" "$root/$m" "$*"; else "$root/ram_insmod" "$root/$m"; fi; }

load_module qtn_pm_qos_compat.ko
load_module board_compat.ko board_id=65535 emac0=1 emac1=1 wifi_hw=7 rfic=4 calstate=3 ext_lna_gain=12 ext_lna_bypass_gain=-5 tx_power_cal=0 min_tx_power=7 max_tx_power=21 allow_dram_sram_fallback=1
load_module runtime_compat.ko
load_module qtn_platform_support.ko
load_module iputil.ko
load_module dmautil.ko
load_module switch_vlan.ko
load_module fwt_if.ko
load_module hbm.ko w3_hbm_lifecycle_enable=1
load_module topaz_congest_queue.ko
echo W3_DRAMLAB_BASELINE_PASS
irq_count() { awk '/(^|[[:space:]])tqe([[:space:]]|$)/ { for (i=2;i<=NF;i++) if ($i ~ /^[0-9]+$/) n+=$i } END { print n+0 }' /proc/interrupts; }
irq_before=$(irq_count)
load_module switch_tqe.ko w3_switch_tqe_only_enable=1
grep -Eq '^switch_tqe ' /proc/modules || stop 83 reason=switch_absent
test -d /sys/class/net/tqe || stop 83 reason=tqe_netdev_absent
for marker in \
 'OMSRAM stage=request' \
 'OMSRAM stage=allocated backend=dram-lab' \
 'OMDMA stage=request' \
 'OMDMA stage=alloc-ok' \
 'OMDMA stage=aligned' \
 'OMDMA stage=ioremap-ok' \
 'OMTQE stage=desc-allocated' \
 'OMTQE stage=ring-programmed' \
 'OMTQE stage=ready'; do dmesg | grep -q "$marker" || stop 83 reason=marker_absent marker="$marker"; done
! grep -Eq '^(fwt_ctrl|qdrv|wlan|gpio|temp_sens|temp_sensor) ' /proc/modules || stop 83 reason=forbidden_module_loaded
sleep 3
irq_after=$(irq_count)
irq_delta=$((irq_after - irq_before))
test "$irq_delta" -ge 0 && test "$irq_delta" -le 64 || stop 83 reason=irq_storm delta="$irq_delta"
! dmesg | tail -n 240 | grep -Eq 'BUG:|Oops:|Kernel panic|DMA.*(error|fault)|use-after-free' || stop 83 reason=fatal_kernel_marker
echo "W3_SWITCH_TQE_DRAMLAB_LOADED irq_before=$irq_before irq_after=$irq_after irq_delta=$irq_delta"
dmesg | tail -n 220
rmmod switch_tqe
for marker in 'OMTQE stage=desc-cleanup' 'OMDMA stage=iounmap' 'OMDMA stage=free raw=' 'backend=dram' 'OMTQE stage=desc-cleanup-complete' 'OMTQE stage=exit-complete'; do dmesg | grep -q "$marker" || stop 84 reason=cleanup_marker_absent marker="$marker"; done
! grep -Eq '^switch_tqe ' /proc/modules || stop 84 reason=switch_unload_failed
test ! -d /sys/class/net/tqe || stop 84 reason=tqe_netdev_survived
echo W3_SWITCH_TQE_DRAMLAB_UNLOADED
trap - EXIT INT TERM
rollback
echo W3_SWITCH_TQE_DRAMLAB_PASS
