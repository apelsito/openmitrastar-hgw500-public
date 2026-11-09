// SPDX-License-Identifier: GPL-2.0-only
/* RAM-only Topaz legacy INTx gate for a targeted PCIe validation. */

#include <linux/bitops.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/string.h>

#define TOPAZ_SYSCTL_BASE 0xe0000000
#define TOPAZ_SYSCTL_SIZE 0x200
#define TOPAZ_PCIE_INT_MASK 0x0c0
#define TOPAZ_PCIE_INT_STATUS 0x17c
#define TOPAZ_PCIE_LEGACY_INTX BIT(11)

static char acknowledge[48];
module_param_string(acknowledge, acknowledge, sizeof(acknowledge), 0400);
MODULE_PARM_DESC(acknowledge,
	"Must equal OPENMITRASTAR_RAM_ONLY_INTX to alter the volatile mask");

static void __iomem *sysctl;
static u32 saved_mask;

static int __init qtn_topaz_pcie_intx_gate_init(void)
{
	u32 before_status;
	u32 after_mask;

	if (strcmp(acknowledge, "OPENMITRASTAR_RAM_ONLY_INTX")) {
		pr_err("OMPCIE_INTX_REFUSED missing RAM-only acknowledgement\n");
		return -EPERM;
	}

	sysctl = ioremap(TOPAZ_SYSCTL_BASE, TOPAZ_SYSCTL_SIZE);
	if (!sysctl)
		return -ENOMEM;

	saved_mask = readl(sysctl + TOPAZ_PCIE_INT_MASK);
	before_status = readl(sysctl + TOPAZ_PCIE_INT_STATUS);
	writel(saved_mask | TOPAZ_PCIE_LEGACY_INTX,
	       sysctl + TOPAZ_PCIE_INT_MASK);
	after_mask = readl(sysctl + TOPAZ_PCIE_INT_MASK);
	if (!(after_mask & TOPAZ_PCIE_LEGACY_INTX)) {
		iounmap(sysctl);
		sysctl = NULL;
		return -EIO;
	}

	pr_info("OMPCIE_INTX_PASS saved_mask=%#010x before_status=%#010x after_mask=%#010x after_status=%#010x rollback=reboot-or-rmmod\n",
		saved_mask, before_status, after_mask,
		readl(sysctl + TOPAZ_PCIE_INT_STATUS));
	return 0;
}

static void __exit qtn_topaz_pcie_intx_gate_exit(void)
{
	if (!sysctl)
		return;
	writel(saved_mask, sysctl + TOPAZ_PCIE_INT_MASK);
	pr_info("OMPCIE_INTX_ROLLBACK restored_mask=%#010x status=%#010x\n",
		readl(sysctl + TOPAZ_PCIE_INT_MASK),
		readl(sysctl + TOPAZ_PCIE_INT_STATUS));
	iounmap(sysctl);
}

module_init(qtn_topaz_pcie_intx_gate_init);
module_exit(qtn_topaz_pcie_intx_gate_exit);

MODULE_AUTHOR("OpenMitraStar project");
MODULE_DESCRIPTION("RAM-only Topaz PCIe legacy INTx mask gate");
MODULE_LICENSE("GPL");
