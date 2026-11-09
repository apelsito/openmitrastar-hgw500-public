// SPDX-License-Identifier: GPL-2.0-only
/* One-shot RAM-only Legacy INTx mask-off discriminator. */

#include <linux/bitops.h>
#include <linux/io.h>
#include <linux/module.h>

#define TOPAZ_SYSCTL_BASE 0xe0000000
#define TOPAZ_SYSCTL_SIZE 0x200
#define TOPAZ_PCIE_INT_MASK 0x0c0
#define TOPAZ_PCIE_LEGACY_INTX BIT(11)

static int __init qtn_topaz_pcie_intx_off_init(void)
{
	void __iomem *sysctl;
	u32 before;
	u32 after;

	sysctl = ioremap(TOPAZ_SYSCTL_BASE, TOPAZ_SYSCTL_SIZE);
	if (!sysctl)
		return -ENOMEM;
	before = readl(sysctl + TOPAZ_PCIE_INT_MASK);
	writel(before & ~TOPAZ_PCIE_LEGACY_INTX,
	       sysctl + TOPAZ_PCIE_INT_MASK);
	after = readl(sysctl + TOPAZ_PCIE_INT_MASK);
	pr_info("OMPCIE_INTX_OFF_PASS before=%#010x after=%#010x bit11=%u rollback=reboot\n",
		before, after, !!(after & TOPAZ_PCIE_LEGACY_INTX));
	iounmap(sysctl);
	return after & TOPAZ_PCIE_LEGACY_INTX ? -EIO : 0;
}

static void __exit qtn_topaz_pcie_intx_off_exit(void) { }
module_init(qtn_topaz_pcie_intx_off_init);
module_exit(qtn_topaz_pcie_intx_off_exit);
MODULE_LICENSE("GPL");
