#!/bin/sh
set -eu

# Read-only preflight plus compatibility-only module ladder.  The script has no
# qdrv start, clearsram, HBM, TQE, GPIO, sensor, RF or flash operation.  Even
# after an approved host/firmware contract it stops before the first MMIO wave.

gate_file=${1:-/etc/openmitrastar/W3_RUNTIME_GATE.env}
module_root_override=${QTN_MODULE_ROOT:-}
expected_release=${QTN_EXPECTED_RELEASE:-5.10.260-openmitrastar-radio}

gate_value()
{
	key=$1
	sed -n "s/^${key}=//p" "$gate_file" | head -n 1
}

stop()
{
	code=$1
	shift
	echo "W3_STOP code=$code $*"
	exit "$code"
}

test -r "$gate_file" || stop 40 "reason=missing_gate_file path=$gate_file"

approved=$(gate_value W3_PAIR_APPROVED)
hardware_approved=$(gate_value W3_HARDWARE_ACTIVE_APPROVED)
gate_release=$(gate_value W3_KERNEL_RELEASE)
host_build=$(gate_value W3_HOST_BUILD)
firmware_build=$(gate_value W3_FIRMWARE_BUILD)
host_version=$(gate_value W3_HOST_VERSION)
firmware_version=$(gate_value W3_FIRMWARE_VERSION)
overlap_class=$(gate_value W3_OVERLAP_CLASS)
reason=$(gate_value W3_STOP_REASON)
[ -z "$gate_release" ] || expected_release=$gate_release
module_root=${module_root_override:-/lib/modules/$expected_release/extra/quantenna}

echo "W3_GATE approved=$approved host=$host_build firmware=$firmware_build overlap=$overlap_class"

test "$(uname -r)" = "$expected_release" || \
	stop 40 "reason=wrong_kernel actual=$(uname -r) expected=$expected_release"

if grep -q 'System RAM' /proc/iomem; then
	grep -Eq '^8493a000-87ffffff[[:space:]]*:[[:space:]]*System RAM$' /proc/iomem || \
		stop 40 "reason=linux_ram_window_mismatch source=iomem"
else
	awk '
		$1 == "Node" { normal=($4 == "Normal"); next }
		normal && $1 == "start_pfn:" { start=$2; next }
		normal && $1 == "spanned" { spanned=$2; next }
		normal && $1 == "present" { present=$2; next }
		END { exit !(start == 271517 && spanned == 7011 && present == 7011) }
	' /proc/zoneinfo || stop 40 "reason=linux_ram_window_mismatch source=zoneinfo"
fi

if grep -Eq '^(qdrv|wlan|hbm|switch_tqe|fwt_ctrl|gpio|temp_sens) ' /proc/modules; then
	stop 40 "reason=dirty_quantenna_state"
fi

test "$approved" = 1 || stop 41 "reason=$reason"
test "$host_version" = "$firmware_version" || stop 41 "reason=gate_claim_inconsistent"
test "$overlap_class" = OEM_QUIRK_PROVEN || stop 41 "reason=overlap_not_allowlisted"

test "${W3_ALLOW_COMPAT_MODULES:-}" = OPENMITRASTAR_W3_COMPAT_ONLY || \
	stop 40 "reason=compat_load_ack_missing"

load_compat()
{
	name=$1
	path=$2
	shift 2
	test -r "$path" || stop 40 "reason=missing_module module=$name"
	insmod "$path" "$@" || stop 40 "reason=insmod_failed module=$name"
	grep -Eq "^${name} " /proc/modules || stop 40 "reason=module_absent module=$name"
	echo "W3_COMPAT_PASS module=$name"
}

load_compat qtn_pm_qos_compat "$module_root/platform/ruby/qtn_pm_qos_compat.ko"
load_compat board_compat "$module_root/platform/ruby/board_compat.ko" \
	board_id=65535 emac0=1 emac1=1 wifi_hw=7 rfic=4 \
	calstate=3 ext_lna_gain=12 ext_lna_bypass_gain=-5 \
	tx_power_cal=0 min_tx_power=7 max_tx_power=21 \
	allow_dram_sram_fallback=0
load_compat runtime_compat "$module_root/platform/ruby/runtime_compat.ko"
load_compat qtn_platform_support "$module_root/platform/ruby/qtn_platform_support.ko"
load_compat iputil "$module_root/platform/ruby/iputil.ko"
load_compat dmautil "$module_root/platform/ruby/dmautil.ko"
load_compat switch_vlan "$module_root/platform/topaz/switch_vlan.ko"
load_compat fwt_if "$module_root/platform/topaz/fwt_if.ko"

# Deliberate terminal gate.  The next wave starts with MMIO-active modules;
# it belongs in a separately acknowledged UART-first experiment.
test "$hardware_approved" = 1 || \
	stop 42 "reason=hardware_active_not_approved next=platform/topaz/hbm.ko"
stop 42 "reason=pre_mmio_checkpoint next=platform/topaz/hbm.ko"
