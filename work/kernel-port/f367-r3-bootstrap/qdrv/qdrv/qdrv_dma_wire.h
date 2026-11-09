#ifndef _QDRV_DMA_WIRE_H
#define _QDRV_DMA_WIRE_H

#include <linux/dma-mapping.h>
#include <linux/errno.h>

#include <common/ruby_mem.h>

static inline int qdrv_dma_handle_to_wire(dma_addr_t original_dma,
		size_t bytes, u32 *wire_bus)
{
	u32 wire;

	if (!wire_bus || !bytes || upper_32_bits(original_dma))
		return -ERANGE;
	wire = (u32)(unsigned long)virt_to_bus(
		(void *)(unsigned long)original_dma);
	if (!wire || wire >= RUBY_MAX_DRAM_SIZE ||
	    bytes > RUBY_MAX_DRAM_SIZE - wire)
		return -ERANGE;
	*wire_bus = wire;
	return 0;
}

#endif
