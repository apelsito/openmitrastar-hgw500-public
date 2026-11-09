#ifndef OPENMITRASTAR_COMPAT_DMA_CACHE_OPS_H
#define OPENMITRASTAR_COMPAT_DMA_CACHE_OPS_H

#include <linux/dma-mapping.h>

#include <asm/cacheflush.h>
#include <asm/io.h>

static __always_inline dma_addr_t
cache_op_before_rx(void *ptr, size_t size, u8 cache_is_cleaned)
{
	phys_addr_t phys = virt_to_phys(ptr);

	if (!cache_is_cleaned)
		dma_cache_inv(phys, size);

	return (dma_addr_t)phys;
}

static __always_inline dma_addr_t cache_op_before_tx(void *ptr, size_t size)
{
	phys_addr_t phys = virt_to_phys(ptr);

	/* The OEM path used DMA_BIDIRECTIONAL here. */
	dma_cache_wback_inv(phys, size);
	return (dma_addr_t)phys;
}

#endif
