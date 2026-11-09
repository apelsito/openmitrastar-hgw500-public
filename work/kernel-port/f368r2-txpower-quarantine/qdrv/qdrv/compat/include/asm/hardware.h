#ifndef OPENMITRASTAR_ASM_HARDWARE_H
#define OPENMITRASTAR_ASM_HARDWARE_H

#include <linux/compiler_types.h>
#include <linux/dma-mapping.h>

#include <asm/io.h>

#define IO_ADDRESS(address) ((unsigned long)(address))
#define BB2_IO_ADDRESS(address) IO_ADDRESS(address)
#define PHYS_IO_ADDRESS(address) (address)

static inline dma_addr_t plat_kernel_addr_to_dma(struct device *dev,
						 void *ptr)
{
	return (dma_addr_t)virt_to_phys(ptr);
}

#endif
