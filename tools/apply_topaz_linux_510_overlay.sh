#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
src=${1:-${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}}
overlay="$root/work/kernel-port/linux-5.10"

test -f "$src/Makefile"

cp "$overlay/drivers/irqchip/irq-qtn-topaz.c" "$src/drivers/irqchip/"
cp "$overlay/drivers/irqchip/Makefile" "$src/drivers/irqchip/Makefile"
cp "$overlay/drivers/irqchip/Kconfig" "$src/drivers/irqchip/Kconfig"

cp "$overlay/drivers/net/mdio/mdio-qtn-topaz-ro.c" "$src/drivers/net/mdio/"
cp "$overlay/drivers/net/mdio/Kconfig.qtn-topaz" "$src/drivers/net/mdio/"
cp "$overlay/drivers/net/mdio/Makefile.qtn-topaz" "$src/drivers/net/mdio/"
grep -q 'Kconfig.qtn-topaz' "$src/drivers/net/mdio/Kconfig" ||
	printf '\nsource "drivers/net/mdio/Kconfig.qtn-topaz"\n' >> "$src/drivers/net/mdio/Kconfig"
grep -q 'Makefile.qtn-topaz' "$src/drivers/net/mdio/Makefile" ||
	printf '\ninclude $(srctree)/drivers/net/mdio/Makefile.qtn-topaz\n' >> "$src/drivers/net/mdio/Makefile"

mkdir -p "$src/drivers/net/ethernet/qtn"
cp "$overlay/drivers/net/ethernet/qtn/qtn-topaz-emac-skeleton.c" \
	"$src/drivers/net/ethernet/qtn/"
cp "$overlay/drivers/net/ethernet/qtn/qtn-topaz-emac.c" \
	"$src/drivers/net/ethernet/qtn/"
cp "$overlay/drivers/net/ethernet/qtn/Kconfig" \
	"$src/drivers/net/ethernet/qtn/"
cp "$overlay/drivers/net/ethernet/qtn/Makefile" \
	"$src/drivers/net/ethernet/qtn/"
grep -q 'drivers/net/ethernet/qtn/Kconfig' "$src/drivers/net/ethernet/Kconfig" ||
	printf '\nsource "drivers/net/ethernet/qtn/Kconfig"\n' >> "$src/drivers/net/ethernet/Kconfig"
grep -q '^obj-y += qtn/' "$src/drivers/net/ethernet/Makefile" ||
	printf '\nobj-y += qtn/\n' >> "$src/drivers/net/ethernet/Makefile"

cp "$overlay/drivers/misc/qtn-topaz-pcie-ro.c" "$src/drivers/misc/"
cp "$overlay/drivers/misc/qtn-topaz-ethernet-layout-test.c" "$src/drivers/misc/"
cp "$overlay/drivers/misc/qtn-topaz-recovery.c" "$src/drivers/misc/"
cp "$overlay/drivers/misc/qtn-topaz-early-wdt.c" "$src/drivers/misc/"
cp "$overlay/drivers/misc/openmitrastar-rtl-unaligned-selftest.c" \
	"$src/drivers/misc/"
cp "$overlay/drivers/misc/Kconfig.qtn-topaz" "$src/drivers/misc/"
cp "$overlay/drivers/misc/Makefile.qtn-topaz" "$src/drivers/misc/"
grep -q 'Kconfig.qtn-topaz' "$src/drivers/misc/Kconfig" ||
	printf '\nsource "drivers/misc/Kconfig.qtn-topaz"\n' >> "$src/drivers/misc/Kconfig"
grep -q 'Makefile.qtn-topaz' "$src/drivers/misc/Makefile" ||
	printf '\ninclude $(srctree)/drivers/misc/Makefile.qtn-topaz\n' >> "$src/drivers/misc/Makefile"

mkdir -p "$src/include/linux/soc/qtn"
cp "$overlay/include/linux/soc/qtn/topaz-ethernet.h" \
	"$src/include/linux/soc/qtn/"
cp "$overlay/include/linux/openmitrastar_qtn_skb.h" "$src/include/linux/"
cp "$overlay/include/linux/openmitrastar_bridge.h" "$src/include/linux/"

cp "$overlay/arch/arc/Kconfig.openmitrastar" "$src/arch/arc/"
cp "$overlay/arch/arc/kernel/reset.c" "$src/arch/arc/kernel/reset.c"
cp "$overlay/arch/arc/kernel/intc-compact.c" \
	"$src/arch/arc/kernel/intc-compact.c"
if ! grep -q '^config OPENMITRASTAR_QDRV_COMPAT' "$src/arch/arc/Kconfig" &&
   ! grep -q 'Kconfig.openmitrastar' "$src/arch/arc/Kconfig"; then
	printf '\nsource "arch/arc/Kconfig.openmitrastar"\n' >> \
		"$src/arch/arc/Kconfig"
fi

if ! grep -q '^config OPENMITRASTAR_BOOT_TRACE' "$src/arch/arc/Kconfig"; then
	patch -d "$src" -p1 --forward < "$overlay/boot-trace-kconfig-topaz.patch"
fi

if ! grep -q '^config OPENMITRASTAR_MMU_ENTRY_PROBE' \
	"$src/arch/arc/Kconfig"; then
	patch -d "$src" -p1 --forward < "$overlay/mmu-entry-probe-kconfig-topaz.patch"
fi

if ! grep -q 'Native Topaz qdrv packet contract' "$src/include/linux/skbuff.h" ||
   ! grep -q 'Native Quantenna qdrv per-interface policy bits' \
		"$src/include/linux/netdevice.h" ||
   ! grep -q 'openmitrastar_br_fdb_fillbuf' "$src/net/bridge/br_fdb.c" ||
   ! grep -q 'openmitrastar_br_ap_isolate_should_forward' \
		"$src/net/bridge/br_forward.c" ||
   ! grep -q 'Quantenna appends private unicast/broadcast counters' \
		"$src/net/core/dev.c"; then
	patch -d "$src" -p1 --forward < "$overlay/qdrv-core-compat.patch"
fi

mkdir -p "$src/arch/arc/plat-topaz"
cp "$overlay/arch/arc/plat-topaz/Kconfig" "$src/arch/arc/plat-topaz/"
grep -q 'arch/arc/plat-topaz/Kconfig' "$src/arch/arc/Kconfig" ||
	sed -i '/source "arch\/arc\/plat-hsdk\/Kconfig"/a source "arch/arc/plat-topaz/Kconfig"' \
		"$src/arch/arc/Kconfig"

cp "$overlay/drivers/pci/controller/pcie-qtn-topaz.c" \
	"$src/drivers/pci/controller/"
cp "$overlay/drivers/pci/controller/Kconfig.qtn-topaz" \
	"$src/drivers/pci/controller/"
cp "$overlay/drivers/pci/controller/Makefile.qtn-topaz" \
	"$src/drivers/pci/controller/"
grep -q 'Kconfig.qtn-topaz' "$src/drivers/pci/controller/Kconfig" ||
	printf '\nsource "drivers/pci/controller/Kconfig.qtn-topaz"\n' >> \
		"$src/drivers/pci/controller/Kconfig"
grep -q 'Makefile.qtn-topaz' "$src/drivers/pci/controller/Makefile" ||
	printf '\ninclude $(srctree)/drivers/pci/controller/Makefile.qtn-topaz\n' >> \
		"$src/drivers/pci/controller/Makefile"

for dts in topaz_mitrastar_stage0.dts topaz_mitrastar_storage.dts \
	topaz_mitrastar_recovery.dts topaz_mitrastar_ramssh.dts; do
	cp "$overlay/arch/arc/boot/dts/$dts" "$src/arch/arc/boot/dts/"
done
cp "$overlay/arch/arc/kernel/head.S" "$src/arch/arc/kernel/"

if ! grep -q 'Continue head.S stages 8..11' "$src/arch/arc/kernel/setup.c"; then
	patch -d "$src" -p1 --forward < "$overlay/watchdog-boot-trace-topaz.patch"
fi

if ! grep -q 'qtn_topaz_start_kernel_wdt_stage' "$src/init/main.c"; then
	patch -d "$src" -p1 --forward < "$overlay/start-kernel-topaz-wdt.patch"
fi

if ! grep -q 'No-op outside Topaz diagnostic builds' "$src/init/main.c"; then
	patch -d "$src" -p1 --forward < "$overlay/trace-gate-noop-topaz.patch"
fi

if ! grep -q 'defined(CONFIG_OPENMITRASTAR_BOOT_TRACE)' "$src/init/main.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/boot-trace-post-setup-arch-watchdog-topaz.patch"
fi

if ! grep -Eq 'range != (10|12|13) && range != 9' "$src/init/main.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/boot-trace-start-kernel-entry-topaz.patch"
fi

if ! grep -q 'wdt\[1\] = range' "$src/init/main.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/boot-trace-start-kernel-range-topaz.patch"
fi

if ! grep -q 'qtn_topaz_setup_arch_wdt_stage' "$src/arch/arc/kernel/setup.c"; then
	patch -d "$src" -p1 --forward < "$overlay/setup-arch-topaz-wdt.patch"
fi

if ! sed -n '/qtn_topaz_setup_arch_wdt_stage/,/^}/p' \
	"$src/arch/arc/kernel/setup.c" | grep -q 'wdt\[1\] = range'; then
	patch -d "$src" -p1 --forward < \
		"$overlay/boot-trace-setup-arch-stages-topaz.patch"
fi

if ! grep -q 'qtn_topaz_setup_processor_wdt_stage' "$src/arch/arc/kernel/setup.c"; then
	patch -d "$src" -p1 --forward < "$overlay/setup-processor-topaz-wdt.patch"
fi

if ! grep -q 'qtn_topaz_timer_wdt_pet' "$src/drivers/clocksource/arc_timer.c"; then
	patch -d "$src" -p1 --forward < "$overlay/arc-timer-topaz-wdt.patch"
fi

if ! grep -q 'deferring ARC Timer1 clocksource registration' \
	"$src/drivers/clocksource/arc_timer.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/timer1-clocksource-register-bypass-topaz.patch"
fi

if ! grep -q 'OMTRACE timer_probe stage' \
	"$src/drivers/clocksource/timer-probe.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/timer-probe-progress-topaz.patch"
fi

if ! grep -q 'OMTRACE start_kernel after time_init' "$src/init/main.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/post-time-init-progress-topaz.patch"
fi

if ! grep -q 'OMTRACE ARC IRQ handoff' "$src/arch/arc/kernel/irq.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/late-irq-handoff-topaz.patch"
fi

if ! grep -q 'pgd=%08x->%08x' "$src/arch/arc/kernel/irq.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/late-refill-pgd-handoff-topaz.patch"
fi

if ! grep -q 'OMTRACE USER_SIGILL' "$src/arch/arc/kernel/traps.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/user-sigill-trace-topaz.patch"
fi

if ! grep -q 'mitrastar,hgw-500bna-qcv2' "$src/arch/arc/plat-sim/platform.c"; then
	patch -d "$src" -p1 --forward < "$overlay/topaz-machine-compat.patch"
fi

if ! grep -q 'Warm Linux-to-Linux handoff\|A RAM handoff disables PID' \
	"$src/arch/arc/mm/tlb.c"; then
	patch -d "$src" -p1 --forward < "$overlay/warm-handoff-tlb-flush.patch"
fi

if ! grep -q 'RAM trampoline already blanked every JTLB\|A RAM handoff disables PID' \
	"$src/arch/arc/mm/tlb.c"; then
	patch -d "$src" -p1 --forward < "$overlay/trampoline-owns-tlb-flush-topaz.patch"
fi

if ! grep -q 'A RAM handoff disables PID in the high untranslated region' \
	"$src/arch/arc/mm/tlb.c"; then
	patch -d "$src" -p1 --forward < "$overlay/cold-mmu-handoff-topaz.patch"
fi

if ! grep -q 'qtn_topaz_mmu_wdt_stage' "$src/arch/arc/mm/tlb.c"; then
	patch -d "$src" -p1 --forward < "$overlay/mmu-pid-canaries-topaz.patch"
fi

if ! grep -q 'Install the new refill PGD before enabling PID' \
	"$src/arch/arc/mm/tlb.c"; then
	patch -d "$src" -p1 --forward < "$overlay/mmu-scratch-before-pid-topaz.patch"
fi

if ! grep -q 'Topaz OEM MMUv2 uses' "$src/arch/arc/include/asm/mmu.h"; then
	patch -d "$src" -p1 --forward < "$overlay/topaz-mmu-pid.patch"
fi

if ! grep -q 'Preserve an already-active OEM MMU' \
	"$src/arch/arc/mm/tlb.c"; then
	patch -d "$src" -p1 --forward < "$overlay/preserve-inherited-mmu-topaz.patch"
fi

if ! grep -q 'First observable operation after arc_mmu_init' \
	"$src/arch/arc/kernel/setup.c"; then
	patch -d "$src" -p1 --forward < "$overlay/watchdog-first-return-canary-topaz.patch"
fi

if ! grep -q 'Keep the Topaz RAM-handoff MMU path stackless' \
	"$src/arch/arc/mm/tlb.c"; then
	patch -d "$src" -p1 --forward < "$overlay/stackless-mmu-init-topaz.patch"
fi

if ! grep -q 'MMU-internal watchdog trace stages' \
	"$src/arch/arc/mm/tlb.c"; then
	patch -d "$src" -p1 --forward < "$overlay/watchdog-mmu-trace-topaz.patch"
fi

if ! grep -q '!defined(CONFIG_OPENMITRASTAR_BOOT_TRACE)' \
	"$src/arch/arc/mm/tlb.c"; then
	patch -d "$src" -p1 --forward < "$overlay/boot-trace-skip-mmu-mumbojumbo.patch"
fi

if ! grep -q 'Skip warm-handoff MMU validation' \
	"$src/arch/arc/mm/tlb.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/boot-trace-skip-mmu-validation-topaz.patch"
fi

if ! grep -q 'Topaz OEM MMUv2 invalidates uTLBs' \
	"$src/arch/arc/mm/tlb.c"; then
	patch -d "$src" -p1 --forward < "$overlay/topaz-oem-tlbwrite-flush.patch"
fi

if ! grep -q 'CONFIG_OPENMITRASTAR_MMU_ENTRY_PROBE' \
	"$src/arch/arc/mm/tlb.c"; then
	patch -d "$src" -p1 --forward < "$overlay/mmu-entry-probe-topaz.patch"
fi

if ! grep -q 'qtn_topaz_tlb_flush_wdt' \
	"$src/arch/arc/mm/tlb.c"; then
	patch -d "$src" -p1 --forward < "$overlay/tlb-flush-watchdog-trace-topaz.patch"
fi

if ! grep -q 'Keep live OEM translations until 5.10 owns' \
	"$src/arch/arc/mm/tlb.c"; then
	patch -d "$src" -p1 --forward < "$overlay/warm-handoff-skip-tlb-flush-topaz.patch"
fi

if ! grep -q 'Defer SCRATCH_DATA0 replacement during the warm handoff' \
	"$src/arch/arc/mm/tlb.c"; then
	patch -d "$src" -p1 --forward < "$overlay/defer-mmu-scratch-topaz.patch"
fi

if ! grep -q 'ARC_USE_SCRATCH_REG.*OPENMITRASTAR_BOOT_TRACE' \
	"$src/arch/arc/mm/tlb.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/boot-trace-defer-mmu-scratch-topaz.patch"
fi

if ! grep -q 'Keep I-cache disabled for warm RAM handoff' \
	"$src/arch/arc/kernel/head.S"; then
	patch -d "$src" -p1 --forward < "$overlay/keep-l1-disabled-topaz.patch"
fi

if ! grep -q 'Preserve the live OEM vector, cache and DSP state' \
	"$src/arch/arc/kernel/head.S"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/boot-trace-skip-cpu-early-setup-topaz.patch"
fi

if sed -n '/qtn_topaz_setup_arch_wdt_stage/,/^}/p' \
	"$src/arch/arc/kernel/setup.c" | grep -q 'wdt\[1\] = 10'; then
	patch -d "$src" -p1 --forward < "$overlay/monotonic-late-watchdog-topaz.patch"
fi

if ! grep -q '1: b 1b' "$src/arch/arc/kernel/setup.c"; then
	patch -d "$src" -p1 --forward < "$overlay/halt-after-mmu-return-topaz.patch"
fi

if ! grep -q 'ARC700 has L1 only' "$src/arch/arc/mm/cache.c"; then
	patch -d "$src" -p1 --forward < "$overlay/cache-dma-callbacks-topaz.patch"
fi

if ! grep -q 'Topaz ARC700/MMUv2 has one fixed' "$src/arch/arc/mm/cache.c"; then
	patch -d "$src" -p1 --forward < "$overlay/cache-line-callback-topaz.patch"
fi

if ! grep -q 'qtn_topaz_cache_wdt_stage' "$src/arch/arc/mm/cache.c"; then
	patch -d "$src" -p1 --forward < "$overlay/cache-init-topaz-wdt.patch"
fi

if ! grep -q 'qtn_topaz_cache_wdt_stage(13)' "$src/arch/arc/mm/cache.c"; then
	patch -d "$src" -p1 --forward < "$overlay/cache-return-topaz-wdt.patch"
fi

if ! grep -q 'keep the call and return in one I-cache line' \
	"$src/arch/arc/mm/cache.c"; then
	patch -d "$src" -p1 --forward < "$overlay/cache-return-line-topaz.patch"
fi

if ! grep -q 'static __always_inline void __init arc_cache_init_master' \
	"$src/arch/arc/mm/cache.c"; then
	patch -d "$src" -p1 --forward < "$overlay/cache-master-inline-topaz.patch"
fi

if ! grep -q 'do not re-probe AUX cache state' "$src/arch/arc/mm/cache.c"; then
	patch -d "$src" -p1 --forward < "$overlay/cache-warm-handoff-skip-topaz.patch"
fi

if ! grep -q '0x43000000U | range' "$src/arch/arc/mm/cache.c"; then
	patch -d "$src" -p1 --forward < "$overlay/cache-spare-breadcrumb-topaz.patch"
fi

if ! grep -Eq 'L1 state is inherited from OEM|Preserve the live OEM L1 state' \
	"$src/arch/arc/kernel/setup.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/setup-processor-warm-cache-skip-topaz.patch"
fi

if ! grep -q 'Preserve the live OEM L1 state during the warm RAM handoff' \
	"$src/arch/arc/kernel/setup.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/boot-trace-warm-cache-skip-topaz.patch"
fi

if ! grep -q 'Preserve the live OEM processor state and continue setup_arch' \
	"$src/arch/arc/kernel/setup.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/boot-trace-bypass-setup-processor-final-topaz.patch"
fi

if ! grep -q 'qtn_topaz_setup_processor_wdt_stage(12); /\* return boundary \*/' \
	"$src/arch/arc/kernel/setup.c"; then
	patch -d "$src" -p1 --forward < "$overlay/return-boundary-timing-topaz.patch"
fi

if ! grep -q '0x53000000U | range\|keep C boot unperturbed' \
	"$src/init/main.c"; then
	patch -d "$src" -p1 --forward < "$overlay/sram-stage-breadcrumb-topaz.patch"
fi

if ! sed -n '/qtn_topaz_setup_arch_wdt_stage/,/^}/p' \
	"$src/arch/arc/kernel/setup.c" | \
	grep -q '0x41000000U | range\|keep C boot unperturbed'; then
	patch -d "$src" -p1 --forward < "$overlay/setup-arch-sram-tag-fix.patch"
fi

if ! grep -q 'keep C boot unperturbed' "$src/init/main.c"; then
	patch -d "$src" -p1 --forward < "$overlay/disable-c-wdt-stages-topaz.patch"
fi

if ! grep -q 'wdt\[1\] = 8\|keep C boot unperturbed' "$src/init/main.c"; then
	patch -d "$src" -p1 --forward < "$overlay/targeted-boot-canaries-topaz.patch"
fi

if ! grep -q 'Loader stack is intentionally detached' \
	"$src/init/main.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/boot-trace-skip-init-stack-magic-topaz.patch"
fi

if ! grep -q 'range != 10 && range != 9' "$src/init/main.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/boot-trace-start-kernel-helper13-topaz.patch"
fi

if ! grep -q 'qtn_topaz_start_kernel_wdt_stage(10);' "$src/init/main.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/boot-trace-start-kernel-call13-topaz.patch"
fi

if ! grep -q 'qtn_start_kernel_body:' "$src/init/main.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/boot-trace-start-kernel-body-label-topaz.patch"
fi

if grep -q 'st r0, \[r24, 24\]' "$src/init/main.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/cold-boot-trace-label-only-topaz.patch"
fi

if ! grep -q 'Boot tracing must not re-arm' "$src/init/main.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/cold-boot-disable-trace-wdt-topaz.patch"
fi

if ! grep -q 'skipping generic atomic coherent pool on Topaz' \
	"$src/kernel/dma/pool.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/skip-atomic-dma-pool-topaz.patch"
fi

# The rtlwifi sources below are the reviewed Linux 5.10.260 Topaz target
# versions.  Copying them before marker-gated patches makes the overlay
# idempotent even when an interrupted build left a partially applied .rej.
cp "$overlay/drivers/net/wireless/realtek/rtlwifi/pci.c" \
	"$src/drivers/net/wireless/realtek/rtlwifi/pci.c"
cp "$overlay/drivers/net/wireless/realtek/rtlwifi/wifi.h" \
	"$src/drivers/net/wireless/realtek/rtlwifi/wifi.h"
cp "$overlay/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c" \
	"$src/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"
cp "$overlay/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.h" \
	"$src/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.h"

if ! grep -q 'buffer_desc_stride' \
	"$src/drivers/net/wireless/realtek/rtlwifi/pci.h"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-mitrastar-tx2-pci-header.patch"
fi
if ! grep -q 'txbd_compact32' \
	"$src/drivers/net/wireless/realtek/rtlwifi/pci.h"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-mitrastar-tx2-pci-mode.patch"
fi

if ! grep -q 'hgw500_tx_pbp_256' \
	"$src/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/hw.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtl8192ee-mitrastar-tx26-pbp-width-override.patch"
fi

if ! grep -q 'OMRTL stage=probe-enter' \
	"$src/drivers/net/wireless/realtek/rtlwifi/pci.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-probe-trace-topaz.patch"
fi

if ! grep -q 'get_unaligned_le16(&hwinfo\[0\])' \
	"$src/drivers/net/wireless/realtek/rtlwifi/efuse.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-arc-unaligned-efuse-topaz.patch"
fi

if ! grep -q 'OMRTL92 stage=module-init-enter' \
	"$src/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/sw.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtl8192ee-module-init-trace-topaz.patch"
fi

if ! grep -q 'dev_addr\[ETH_ALEN\] __aligned(2)' \
	"$src/drivers/net/wireless/realtek/rtlwifi/wifi.h"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-arc-align-efuse-dev-addr-topaz.patch"
fi

if ! grep -q 'OMRTL stage=op-start-enter' \
	"$src/drivers/net/wireless/realtek/rtlwifi/core.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-runtime-trace-topaz.patch"
fi

if ! grep -q 'OMRTL stage=tx-enter' \
	"$src/drivers/net/wireless/realtek/rtlwifi/core.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-tx-trace-topaz.patch"
fi

if ! grep -q 'OMRTL stage=irq-line-hold' \
	"$src/drivers/net/wireless/realtek/rtlwifi/pci.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-pci-irq-lifecycle-topaz.patch"
fi

if ! grep -q 'OMRTL stage=irq-line-noautoen' \
	"$src/drivers/net/wireless/realtek/rtlwifi/pci.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-pci-irq-noautoen-topaz.patch"
fi

if ! grep -Eq 'OMRTL stage=irq-deferred-(handled|acked)' \
	"$src/drivers/net/wireless/realtek/rtlwifi/pci.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-pci-managed-deferred-handled-topaz.patch"
fi

if ! grep -q 'OMRTL stage=irq-deferred-acked' \
	"$src/drivers/net/wireless/realtek/rtlwifi/pci.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-pci-managed-deferred-ack-topaz.patch"
fi

if ! grep -q 'OMRTL stage=beacon-irq-window protected' \
	"$src/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/hw.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-rtl8192ee-topaz-beacon-irq-window.patch"
fi

if ! grep -q 'OMRTLTX6 stage=txbd-system-width' \
	"$src/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/hw.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-mitrastar-tx6-global-txbd-width.patch"
fi

if ! grep -q 'OMRTL92 stage=tx-poll-beacon-trigger' \
	"$src/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-rtl8192ee-topaz-beacon-poll.patch"
fi

if ! grep -q 'OMRTLTXCLOSE id=' \
	"$src/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-mitrastar-tx-close-diag.patch"
fi

cp "$overlay/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/fw.c" \
	"$src/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/fw.c"

if ! grep -q 'OMRTL stage=ap-swcrypto-fallback accepted' \
	"$src/drivers/net/wireless/realtek/rtlwifi/core.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-mitrastar-ap-swcrypto.patch"
fi

if ! grep -q 'OMRTLAMPDU stage=tx-start-rejected' \
	"$src/drivers/net/wireless/realtek/rtlwifi/core.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-mitrastar-tx-ampdu-lab.patch"
fi

if ! grep -q 'OMRTLACK stage=policy-active' \
	"$src/drivers/net/wireless/realtek/rtlwifi/base.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-mitrastar-honest-tx-ack-lab.patch"
fi

if ! grep -q 'OMRTL92 stage=fw-warm-preclean reason=residual-ready' \
	"$src/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/fw.c"; then
	patch -d "$src" -p1 --forward < \
		"$overlay/rtlwifi-mitrastar-warm-preclean-topaz.patch"
fi
