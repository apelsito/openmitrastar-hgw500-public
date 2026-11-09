#ifndef OPENMITRASTAR_QDRV_COMPAT_H
#define OPENMITRASTAR_QDRV_COMPAT_H

#include <asm/cacheflush.h>
#include <asm/board/gpio.h>
#include <asm/hardware.h>
#include <common/ruby_mem.h>
#include <linux/etherdevice.h>
#include <linux/fs.h>
#include <linux/openmitrastar_bridge.h>

void *heap_sram_alloc(unsigned long size);
void heap_sram_free(void *ptr);
u32 chip_id(void);

#ifndef ARC_DCACHE_LINE_LEN
#define ARC_DCACHE_LINE_LEN ARC_DCACHE_LINE_LENGTH
#endif

/* The OEM linker placed selected hot paths in SRAM. Stage 1 keeps them in text. */
#ifndef __sram_text
#define __sram_text
#endif

/* Stage 1 uses the normal Linux bridge path, not Quantenna's private hooks. */
#undef CONFIG_BRIDGE
#undef CONFIG_BRIDGE_MODULE

/* IPv6 stays enabled in Linux; only qdrv's private NDISC hooks are omitted. */
#ifdef OPENMITRASTAR_QDRV_NO_IPV6_OFFLOAD
#undef CONFIG_IPV6
#endif

#ifndef BR_SUBPORT_MAP
#define BR_SUBPORT_MAP(port) ((port) | 0x8000U)
#endif
#ifndef BR_SUBPORT_UNMAP
#define BR_SUBPORT_UNMAP(port) ((port) & 0x7fffU)
#endif

#ifndef read_new_aux_reg
#define read_new_aux_reg(reg) read_aux_reg(reg)
#endif

/* ARC ioremap() already creates the device mapping expected by this driver. */
#ifndef ioremap_nocache
#define ioremap_nocache ioremap
#endif

#ifndef writel_or
#define writel_or(bits, addr) writel(readl(addr) | (bits), (addr))
#endif
#ifndef writel_and
#define writel_and(bits, addr) writel(readl(addr) & (bits), (addr))
#endif

#ifndef arc_write_uncached_16
#define arc_write_uncached_16(ptr, data) \
	__asm__ __volatile__("stw.di %0, [%1]" : : "r"(data), "r"(ptr))
#endif

#ifndef compare_ether_addr
#define compare_ether_addr(addr1, addr2) (!ether_addr_equal((addr1), (addr2)))
#endif

#ifndef strict_strtoul
#define strict_strtoul kstrtoul
#endif

#ifndef ipv6_addr_copy
#define ipv6_addr_copy(dst, src) (*(dst) = *(src))
#endif

#ifndef __skb_append
#define __skb_append(old, new, list) __skb_queue_after((list), (old), (new))
#endif

#ifndef LL_ALLOCATED_SPACE
#define LL_ALLOCATED_SPACE(dev) \
	((((dev)->hard_header_len + (dev)->needed_headroom + \
	   (dev)->needed_tailroom) & ~(HH_DATA_MOD - 1)) + HH_DATA_MOD)
#endif

int qdrv_compat_open(const char *path, int flags, umode_t mode);
ssize_t qdrv_compat_read(int handle, void *buffer, size_t count);
ssize_t qdrv_compat_write(int handle, const void *buffer, size_t count);
int qdrv_compat_close(int handle);

#ifndef QTN_FLAG_WIFI_DEVICE
#define QTN_FLAG_WIFI_DEVICE          0x80000000U
#define QTN_FLAG_INTRA_BSS_ISOLATE    0x40000000U
#define QTN_FLAG_BSS_ISOLATE          0x20000000U
#endif
#define QTN_FLAG_WIFI_INTRA_BSS \
	(QTN_FLAG_WIFI_DEVICE | QTN_FLAG_INTRA_BSS_ISOLATE)
#define QTN_FLAG_WIFI_BSS_ISOLATE \
	(QTN_FLAG_WIFI_DEVICE | QTN_FLAG_BSS_ISOLATE)
#define QTN_FLAG_IS_INTRA_BSS(flags) \
	(((flags) & QTN_FLAG_WIFI_INTRA_BSS) == QTN_FLAG_WIFI_INTRA_BSS)
#define QTN_FLAG_IS_BSS_ISOLATE(flags) \
	(((flags) & QTN_FLAG_WIFI_BSS_ISOLATE) == QTN_FLAG_WIFI_BSS_ISOLATE)

/* Entropy sampling was removed from request_irq(); no interrupt semantics. */
#ifndef IRQF_SAMPLE_RANDOM
#define IRQF_SAMPLE_RANDOM 0
#endif

#define QTN_SKB_ALLOC_TRACE 0
#define QTN_SKB_ALLOC_TRACE_ARGNAMES(file, func, line)
#define QTN_SKB_ALLOC_TRACE_ARGS
#define QTN_SKB_ALLOC_TRACE_ARGVARS
#define QTN_SKB_ALLOC_TRACE_ARGSRC

static inline void openmitrastar_flush_dcache_range(unsigned long start,
		unsigned long end)
{
	dma_cache_wback(virt_to_phys((void *)start), end - start);
}

static inline void openmitrastar_flush_inv_dcache_range(unsigned long start,
		unsigned long end)
{
	dma_cache_wback_inv(virt_to_phys((void *)start), end - start);
}

static inline void openmitrastar_inv_dcache_range(unsigned long start,
		unsigned long end)
{
	dma_cache_inv(virt_to_phys((void *)start), end - start);
}

#define flush_dcache_range openmitrastar_flush_dcache_range
#define flush_and_inv_dcache_range openmitrastar_flush_inv_dcache_range
#define inv_dcache_range openmitrastar_inv_dcache_range

#endif
