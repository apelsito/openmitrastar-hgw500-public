#!/bin/sh

# RAM-only, detached direct-EMAC -> switch_emac handoff.
# A local timer is armed before the direct driver is unbound.  Only a fresh
# SSH session may create the commit sentinel; otherwise the direct EMAC is
# rebound automatically.

set -eu
trap '' 1

root=${1:-/tmp/w3-switch-emac}
gate=${2:-/tmp/W3_SWITCH_EMAC_HANDOFF_GATE.env}
state=${3:-/run/openmitrastar/switch-emac-handoff}

value()
{
	sed -n "s/^$1=//p" "$gate" | head -n 1
}

log()
{
	printf '%s\n' "$*" >/dev/console 2>/dev/null || printf '%s\n' "$*"
}

traffic_snapshot()
{
	tag=$1
	for dev in eth1_emac0 eth1_emac1 br0 tqe; do
		base=/sys/class/net/$dev
		if [ -e "$base" ]; then
			carrier=$(cat "$base/carrier" 2>/dev/null || echo na)
			oper=$(cat "$base/operstate" 2>/dev/null || echo na)
			rx=$(cat "$base/statistics/rx_packets" 2>/dev/null || echo na)
			tx=$(cat "$base/statistics/tx_packets" 2>/dev/null || echo na)
			rxe=$(cat "$base/statistics/rx_errors" 2>/dev/null || echo na)
			txe=$(cat "$base/statistics/tx_errors" 2>/dev/null || echo na)
			log "W3_SWITCH_EMAC stage=traffic-snapshot tag=$tag dev=$dev carrier=$carrier oper=$oper rx=$rx tx=$tx rxerr=$rxe txerr=$txe"
		fi
	done
	grep -E '^ *5:|^ *21:' /proc/interrupts | while IFS= read -r line; do
		log "W3_SWITCH_EMAC stage=irq-snapshot tag=$tag value=$line"
	done
}

stop()
{
	code=$1
	shift
	current_status=$(cat "$status_file" 2>/dev/null || echo pre-state)
	log "W3_SWITCH_EMAC_STOP code=$code status=$current_status module=${current_module:-none} module_index=${module_index:-0} $*"
	exit "$code"
}

approved=$(value W3_SWITCH_EMAC_HANDOFF_APPROVED)
release=$(value W3_KERNEL_RELEASE)
management_ip=$(value W3_MANAGEMENT_IPV4)
management_netmask=$(value W3_MANAGEMENT_NETMASK)
management_gateway=$(value W3_MANAGEMENT_GATEWAY)
host_ip=$(value W3_HOST_IPV4)
rollback_seconds=$(value W3_ROLLBACK_SECONDS)
target=mitrastar,hgw-500bna-qcv2
direct_driver=/sys/bus/platform/drivers/qtn-topaz-emac
direct_device=e8000000.ethernet
commit_file=$state/commit
rollback_lock=$state/rollback.lock
status_file=$state/status
preload_pid_file=$state/preload-rollback.pid
skip_ioss_reset_pulse=$(value W3_SKIP_IOSS_RESET_PULSE)
preserve_direct_emac=$(value W3_PRESERVE_DIRECT_EMAC)
tqe_ring_entries=$(value W3_TQE_RING_ENTRIES)
current_module=none
module_index=0
module_total=15
if [ "$skip_ioss_reset_pulse" = 1 ]; then
	# The non-bonded Linux 5.10 profile owns its optional FWT clients locally:
	# qdrv/wlan carry fail-closed compatibility shims and switch_emac compiles
	# out the proprietary remapper.  Loading fwt_ctrl here would require the
	# IOSS reset pulse that this path explicitly forbids.
	module_total=14
fi
rollback_armed=0
fatal_pattern='MuC:.*exception|MuC exception|MuC has halted|forcing reboot|Kernel panic|Oops:|BUG:|Unable to handle|EV_TLB|EV_ProtV'

test "$approved" = 1 || stop 91 reason=handoff_not_approved
test "$(value W3_PAIR_APPROVED)" = 1 || stop 91 reason=pair_not_approved
test "$(value W3_IOSS_ONLY_PROVEN)" = 1 || stop 91 reason=ioss_not_proven
if [ "$skip_ioss_reset_pulse" = 0 ]; then
	test "$(value W3_FWT_CTRL_REVERSIBLE_ARTIFACT_READY)" = 1 || stop 91 reason=fwt_artifact_not_ready
fi
test "$(value W3_HARDWARE_ACTIVE_APPROVED)" = 0 || stop 91 reason=broader_gate_must_remain_zero
test "$(uname -r)" = "$release" || stop 92 reason=kernel_mismatch actual="$(uname -r)" expected="$release"
grep -aq "$target" /proc/device-tree/compatible || stop 92 reason=target_mismatch
test "$rollback_seconds" -ge 30 && test "$rollback_seconds" -le 180 || stop 92 reason=rollback_window_invalid
case "$skip_ioss_reset_pulse" in 0|1) ;; *) stop 92 reason=ioss_policy_invalid value="$skip_ioss_reset_pulse" ;; esac
case "$preserve_direct_emac" in 0|1) ;; *) stop 92 reason=direct_policy_invalid value="$preserve_direct_emac" ;; esac
case "$tqe_ring_entries" in 256|512) ;; *) stop 92 reason=tqe_ring_invalid value="$tqe_ring_entries" ;; esac
test "$preserve_direct_emac" = 0 || test "$skip_ioss_reset_pulse" = 1 || stop 92 reason=direct_requires_no_ioss
test -d "$direct_driver" || stop 92 reason=direct_driver_absent
test -e "/sys/bus/platform/devices/$direct_device" || stop 92 reason=direct_device_absent
test -e /sys/class/net/eth0 || stop 92 reason=direct_eth0_absent
if [ -e /sys/class/net/br0 ]; then
	had_br0=1
	test -e /sys/class/net/br0/brif/eth0 || stop 92 reason=eth0_not_in_br0
	test ! -e /sys/class/net/br0/brif/tqe || stop 92 reason=tqe_already_in_bridge
	if [ -e /sys/class/net/br0/brif/wlan0 ]; then
		had_wlan0=1
	else
		had_wlan0=0
	fi
else
	had_br0=0
	had_wlan0=0
fi

for dirty in switch_emac fwt_ctrl switch_tqe topaz_congest_queue hbm emac_lib dpi; do
	grep -Eq "^${dirty} " /proc/modules && stop 92 reason=dirty_module module="$dirty"
done

mkdir -p "$state"
rm -rf "$rollback_lock"
rm -f "$commit_file"
old_mac=$(cat /sys/class/net/eth0/address)
printf '%s\n' "$old_mac" >"$state/direct-mac"
printf '%s\n' "$had_br0" >"$state/had-br0"
printf '%s\n' "$had_wlan0" >"$state/had-wlan0"
printf '%s\n' preparing >"$status_file"
log "W3_SWITCH_EMAC stage=preflight-pass target=$target direct=$direct_device mac=$old_mac had_br0=$had_br0 had_wlan0=$had_wlan0"
log "W3_SWITCH_EMAC stage=runtime-begin ioss_reset_policy=$(test "$skip_ioss_reset_pulse" = 1 && echo skip || echo explicit-pulse) module_total=$module_total rollback=target-local"

load_module()
{
	file=$1
	shift
	test -r "$root/$file" || stop 93 reason=module_missing module="$file"
	test "$rollback_armed" = 1 || stop 93 reason=rollback_not_armed module="$file"
	module_index=$((module_index + 1))
	current_module=${file%.ko}
	log "W3_SWITCH_EMAC stage=module-load-enter index=$module_index total=$module_total module=$current_module"
	if [ "$#" -gt 0 ]; then
		"$root/ram_insmod" "$root/$file" "$*" || stop 93 reason=module_load_failed module="$current_module"
	else
		"$root/ram_insmod" "$root/$file" || stop 93 reason=module_load_failed module="$current_module"
	fi
	grep -Eq "^${current_module} " /proc/modules || stop 93 reason=module_not_registered module="$current_module"
	log "W3_SWITCH_EMAC stage=module-load-pass index=$module_index total=$module_total module=$current_module"
}

unload_quantenna()
{
	for module in switch_emac fwt_ctrl switch_tqe topaz_congest_queue hbm dpi emac_lib fwt_if switch_vlan dmautil iputil runtime_compat board_compat qtn_platform_support qtn_pm_qos_compat; do
		rmmod "$module" >/dev/null 2>&1 || true
	done
}

restore_direct_network()
{
	if [ "$preserve_direct_emac" = 1 ] && [ -e /sys/class/net/eth0 ]; then
		unload_quantenna
		printf '%s\n' rolled-back >"$status_file"
		log "W3_SWITCH_EMAC stage=rollback-complete mode=direct-preserved direct=eth0 bridge=br0 ip=$management_ip"
		return 0
	fi
	if [ -e /sys/class/net/eth0 ]; then
		brctl delif br0 eth0 >/dev/null 2>&1 || true
		ifconfig eth0 0.0.0.0 down >/dev/null 2>&1 || true
	fi

	unload_quantenna

	if [ ! -e /sys/class/net/eth0 ]; then
		printf '%s\n' "$direct_device" >"$direct_driver/bind" 2>/dev/null || true
	fi

	tries=0
	while [ ! -e /sys/class/net/eth0 ] && [ "$tries" -lt 15 ]; do
		sleep 1
		tries=$((tries + 1))
	done

	if [ ! -e /sys/class/net/eth0 ]; then
		printf '%s\n' rollback-rebind-failed >"$status_file"
		log "W3_SWITCH_EMAC stage=rollback-failed reason=direct-rebind"
		return 1
	fi

	ifconfig eth0 down >/dev/null 2>&1 || true
	ifconfig eth0 hw ether "$old_mac" >/dev/null 2>&1 || true
	if [ "$had_br0" = 1 ]; then
		ifconfig eth0 0.0.0.0 up >/dev/null 2>&1 || true
		brctl addif br0 eth0 >/dev/null 2>&1 || true
		ifconfig br0 hw ether "$old_mac" >/dev/null 2>&1 || true
		ifconfig br0 "$management_ip" netmask "$management_netmask" up >/dev/null 2>&1 || true
		route del default >/dev/null 2>&1 || true
		route add default gw "$management_gateway" dev br0 >/dev/null 2>&1 || true
	else
		brctl delif br0 eth0 >/dev/null 2>&1 || true
		ifconfig br0 0.0.0.0 down >/dev/null 2>&1 || true
		brctl delbr br0 >/dev/null 2>&1 || true
		ifconfig eth0 "$management_ip" netmask "$management_netmask" up >/dev/null 2>&1 || true
		route del default >/dev/null 2>&1 || true
		route add default gw "$management_gateway" dev eth0 >/dev/null 2>&1 || true
	fi
	printf '%s\n' rolled-back >"$status_file"
	log "W3_SWITCH_EMAC stage=rollback-complete direct=eth0 bridge=br0 ip=$management_ip"
	return 0
}

rollback()
{
	reason=${1:-unspecified}
	mkdir "$rollback_lock" 2>/dev/null || return 0
	log "W3_SWITCH_EMAC stage=rollback-start reason=$reason"
	restore_direct_network || true
}

trap 'rollback signal-or-exit' 0 2 15

# Load every dependency that does not own the EMAC first.  The Q1 runtime path
# explicitly skips every reset probe; the legacy gated experiment remains
# available only when W3_SKIP_IOSS_RESET_PULSE=0.
printf '%s\n' preloading >"$status_file"
(
	sleep 75
	case "$(cat "$status_file" 2>/dev/null || true)" in
	preloading|preparing) rollback preload-deadline ;;
	esac
) </dev/null >/dev/console 2>&1 &
preload_pid=$!
printf '%s\n' "$preload_pid" >"$preload_pid_file"
rollback_armed=1
log "W3_SWITCH_EMAC stage=preload-rollback-armed seconds=75 pid=$preload_pid"

fatal_before=$(dmesg | grep -Eic "$fatal_pattern" || true)
load_module qtn_pm_qos_compat.ko
load_module qtn_platform_support.ko
if [ "$skip_ioss_reset_pulse" = 1 ]; then
	ioss_asserted_before=$(dmesg | grep -c 'OMFWT1B target=ioss stage=asserted' || true)
	log "W3_SWITCH_EMAC stage=ioss-reset-policy mode=skip asserted_before=$ioss_asserted_before reason=preserve-uart-direct-emac"
	load_module board_compat.ko \
		board_id=65535 emac0=1 emac1=1 phy0=1 phy1=3 rgmii_timing=2172813954 \
		wifi_hw=7 rfic=4 calstate=3 ext_lna_gain=12 ext_lna_bypass_gain=-5 \
		tx_power_cal=0 min_tx_power=7 max_tx_power=21 allow_dram_sram_fallback=1
	for probe in w3_fwt_rxp_quiesce_probe_enable w3_fwt_netss_ioss_pulse_probe_enable w3_fwt_netss_only_probe_enable w3_fwt_ioss_only_probe_enable; do
		test "$(cat "/sys/module/board_compat/parameters/$probe")" = 0 || stop 94 reason=unexpected_reset_probe_enabled probe="$probe"
	done
	ioss_asserted_after=$(dmesg | grep -c 'OMFWT1B target=ioss stage=asserted' || true)
	test "$ioss_asserted_after" = "$ioss_asserted_before" || stop 94 reason=ioss_pulse_observed before="$ioss_asserted_before" after="$ioss_asserted_after"
	log "W3_SWITCH_EMAC stage=ioss-reset-skipped asserted_before=$ioss_asserted_before asserted_after=$ioss_asserted_after board_compat=loaded"
else
	log "W3_SWITCH_EMAC stage=ioss-reset-policy mode=explicit-pulse"
	load_module board_compat.ko \
		board_id=65535 emac0=1 emac1=1 phy0=1 phy1=3 rgmii_timing=2172813954 \
		wifi_hw=7 rfic=4 calstate=3 ext_lna_gain=12 ext_lna_bypass_gain=-5 \
		tx_power_cal=0 min_tx_power=7 max_tx_power=21 allow_dram_sram_fallback=1 \
		w3_fwt_ioss_only_probe_enable=1
	dmesg | grep -q 'OMFWT1B target=ioss stage=complete rc=0' || stop 94 reason=ioss_marker_absent
fi
load_module runtime_compat.ko
load_module iputil.ko
load_module dmautil.ko
load_module switch_vlan.ko
load_module fwt_if.ko
load_module hbm.ko w3_hbm_lifecycle_enable=1 w3_hbm_timer_reclaim_enable=0
test "$(cat /sys/module/hbm/parameters/w3_hbm_timer_reclaim_enable)" = 0 || stop 94 reason=hbm_timer_reclaim_not_disabled
load_module topaz_congest_queue.ko
load_module emac_lib.ko
load_module dpi.ko
load_module switch_tqe.ko "w3_switch_tqe_only_enable=1 w3_rx_ring_entries=$tqe_ring_entries"
dmesg | grep -q 'OMTQE stage=ready' || stop 94 reason=tqe_not_ready
if [ "$skip_ioss_reset_pulse" = 1 ]; then
	test ! -e /sys/module/fwt_ctrl || stop 94 reason=fwt_ctrl_loaded_on_no_ioss_path
	log "OMFWTBYPASS stage=active policy=no-ioss provider=qdrv-wlan-local-shims switch_emac=nonbonded-remapper-compiled-out acceleration=disabled"
else
	load_module fwt_ctrl.ko w3_fwt_ctrl_only_enable=1
	dmesg | grep -q 'OMFWT stage=ready' || stop 94 reason=fwt_not_ready
fi
test -e /sys/class/net/tqe || stop 94 reason=tqe_netdev_absent
test ! -e /sys/class/net/br0/brif/tqe || stop 94 reason=tqe_in_bridge
test -e /sys/class/net/eth0 || stop 94 reason=direct_emac_lost_before_handoff
fatal_after=$(dmesg | grep -Eic "$fatal_pattern" || true)
test "$fatal_after" = "$fatal_before" || stop 94 reason=new_fatal_kernel_marker before="$fatal_before" after="$fatal_after"
kill "$preload_pid" >/dev/null 2>&1 || true
rm -f "$preload_pid_file"
rollback_armed=0
printf '%s\n' preload-complete >"$status_file"
log "W3_SWITCH_EMAC stage=preload-rollback-disarmed modules=ready"
log "W3_SWITCH_EMAC stage=preload-complete modules=$module_index ioss_reset_policy=$(test "$skip_ioss_reset_pulse" = 1 && echo skipped || echo explicit-pulse) fwt_ctrl=$(test "$skip_ioss_reset_pulse" = 1 && echo bypassed || echo ready) direct_eth0=present"

# This independent process remains runnable even if the handoff command blocks.
(
	sleep "$rollback_seconds"
	if [ ! -e "$commit_file" ]; then
		rollback deadline
	fi
) </dev/null >/dev/console 2>&1 &
rollback_pid=$!
printf '%s\n' "$rollback_pid" >"$state/rollback.pid"
rollback_armed=1
printf '%s\n' rollback-armed >"$status_file"
log "W3_SWITCH_EMAC stage=rollback-armed seconds=$rollback_seconds pid=$rollback_pid"

if [ "$preserve_direct_emac" = 1 ]; then
	log "W3_SWITCH_EMAC stage=direct-preserve-enter device=$direct_device interface=eth0"
	load_module switch_emac.ko "bonding=0 w3_force_lhost=0 w3_symbols_only=1"
	test "$module_index" = "$module_total" || stop 96 reason=module_order_incomplete actual="$module_index" expected="$module_total"
	test -e /sys/class/net/eth0 || stop 96 reason=direct_eth0_lost
	test -e /sys/class/net/br0/brif/eth0 || stop 96 reason=direct_eth0_bridge_lost
	test ! -e /sys/class/net/eth1_emac0 || stop 96 reason=unexpected_emac0_netdev
	test ! -e /sys/class/net/eth1_emac1 || stop 96 reason=unexpected_emac1_netdev
	test "$(cat /sys/module/switch_emac/parameters/w3_symbols_only)" = Y || stop 96 reason=symbols_only_gate_missing
	dmesg | grep -q 'OMEMACSW stage=symbols-only-ready .*direct_emac=preserved' || stop 96 reason=symbols_only_marker_missing
	printf '%s\n' direct-preserved >"$state/management-mode"
	printf '%s\n' awaiting-host-commit >"$status_file"
	log "W3_SWITCH_EMAC stage=awaiting-host-commit mode=direct-preserved interface=eth0 bridge=br0 ip=$management_ip wlan0_preserved=$had_wlan0"
	elapsed=0
	while [ "$elapsed" -le "$rollback_seconds" ]; do
		if [ -e "$commit_file" ]; then
			kill "$rollback_pid" >/dev/null 2>&1 || true
			printf '%s\n' committed >"$status_file"
			trap - 0 2 15
			log "W3_SWITCH_EMAC stage=committed source=new-ssh mode=direct-preserved interface=eth0 bridge=br0"
			exit 0
		fi
		sleep 1
		elapsed=$((elapsed + 1))
	done
	rollback commit-timeout
	trap - 0 2 15
	exit 99
fi

# Product RAM without an external PSK starts with L3 on eth0 and no br0.
# Do not cycle the direct EMAC before the causal IOSS/FWT sequence: that
# down/up was proven to return FWT to states 14/15.  Create br0 only after
# FWT is ready and rollback is armed, immediately before the ownership cut.
if [ "$had_br0" = 0 ]; then
	brctl addbr br0 || stop 95 reason=br0_create_failed
	ifconfig eth0 0.0.0.0 down
	brctl addif br0 eth0 || stop 95 reason=br0_add_direct_failed
	ifconfig eth0 0.0.0.0 up
	ifconfig br0 hw ether "$old_mac"
	ifconfig br0 "$management_ip" netmask "$management_netmask" up
	route del default >/dev/null 2>&1 || true
	route add default gw "$management_gateway" dev br0 >/dev/null 2>&1 || true
	log "W3_SWITCH_EMAC stage=baseline-bridge-created bridge=br0 direct=eth0 ip=$management_ip"
fi

# No module may touch the EMAC until the direct owner has stopped and unbound.
brctl delif br0 eth0
ifconfig eth0 0.0.0.0 down
printf '%s\n' "$direct_device" >"$direct_driver/unbind"
test ! -e /sys/class/net/eth0 || stop 95 reason=direct_unbind_failed
log "W3_SWITCH_EMAC stage=direct-unbound device=$direct_device"

load_module switch_emac.ko bonding=0 w3_force_lhost=1
test "$module_index" = "$module_total" || stop 96 reason=module_order_incomplete actual="$module_index" expected="$module_total"
dmesg | grep -q 'OMEMACSW stage=lhost-forced enabled=1' || stop 96 reason=lhost_route_not_forced

tries=0
while [ ! -e /sys/class/net/eth1_emac1 ] && [ "$tries" -lt 15 ]; do
	sleep 1
	tries=$((tries + 1))
done
test -e /sys/class/net/eth1_emac1 || stop 96 reason=emac1_absent
test -e /sys/class/net/eth1_emac0 || stop 96 reason=emac0_absent

# Vendor numbering is inverted relative to the direct-driver label: the proven
# e8000000 management MAC is switch_emac eth1_emac1 / TQE port1 / PHY3.
ifconfig eth1_emac0 0.0.0.0 down
ifconfig eth1_emac1 0.0.0.0 down
ifconfig eth1_emac1 hw ether "$old_mac"
brctl addif br0 eth1_emac1
ifconfig eth1_emac1 0.0.0.0 up
ifconfig br0 hw ether "$old_mac"
ifconfig br0 "$management_ip" netmask "$management_netmask" up
route del default >/dev/null 2>&1 || true
route add default gw "$management_gateway" dev br0 >/dev/null 2>&1 || true

test -e /sys/class/net/br0/brif/eth1_emac1 || stop 97 reason=bridge_emac1_absent
test ! -e /sys/class/net/br0/brif/tqe || stop 97 reason=tqe_in_bridge
test "$(cat /sys/class/net/eth1_emac0/operstate)" = down || stop 97 reason=emac0_not_down
if [ "$had_wlan0" = 1 ]; then
	test -e /sys/class/net/br0/brif/wlan0 || stop 97 reason=wlan0_not_preserved
fi
traffic_snapshot pre-ping
ping -c 3 -W 2 "$host_ip" >/dev/null 2>&1 || log "W3_SWITCH_EMAC stage=host-ping-pending interface=eth1_emac1 phy=3"

printf '%s\n' awaiting-host-commit >"$status_file"
log "W3_SWITCH_EMAC stage=awaiting-host-commit interface=eth1_emac1 source=e8000000 phy=3 bridge=br0 ip=$management_ip wlan0_preserved=$had_wlan0 hbm_timer_reclaim=0"

(
	seq=0
	while [ "$seq" -lt 8 ] && [ "$(cat "$status_file" 2>/dev/null || true)" = awaiting-host-commit ]; do
		traffic_snapshot "wait-$seq"
		seq=$((seq + 1))
		sleep 8
	done
) </dev/null >/dev/console 2>&1 &
diag_pid=$!

elapsed=0
while [ "$elapsed" -le "$rollback_seconds" ]; do
	if [ -e "$commit_file" ]; then
		kill "$rollback_pid" >/dev/null 2>&1 || true
		kill "$diag_pid" >/dev/null 2>&1 || true
		printf '%s\n' committed >"$status_file"
		trap - 0 2 15
		log "W3_SWITCH_EMAC stage=committed source=new-ssh interface=eth1_emac1 bridge=br0"
		exit 0
	fi
	if [ "$(cat "$status_file" 2>/dev/null || true)" = rolled-back ]; then
		kill "$diag_pid" >/dev/null 2>&1 || true
		trap - 0 2 15
		exit 98
	fi
	sleep 1
	elapsed=$((elapsed + 1))
done

rollback commit-timeout
kill "$diag_pid" >/dev/null 2>&1 || true
trap - 0 2 15
exit 99
