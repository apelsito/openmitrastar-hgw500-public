// SPDX-License-Identifier: GPL-2.0-only
/* One-shot Topaz root-complex/iATU telemetry. No ATU configuration writes. */

#include <linux/io.h>
#include <linux/module.h>

#define TOPAZ_PCIE_DBI_BASE 0xe9000000
#define TOPAZ_PCIE_DBI_SIZE 0x1000
#define TOPAZ_SYSCTL_BASE 0xe0000000
#define TOPAZ_SYSCTL_SIZE 0x200
#define TOPAZ_SYSCTL_PCIE_INT_MASK 0x0c0
#define TOPAZ_SYSCTL_PCIE_INT_STATUS 0x17c

#define ATU_VIEWPORT 0x900
#define ATU_CR1      0x904
#define ATU_CR2      0x908
#define ATU_BASE_LO  0x90c
#define ATU_BASE_HI  0x910
#define ATU_LIMIT    0x914
#define ATU_TARGET_LO 0x918
#define ATU_TARGET_HI 0x91c

static void qtn_dump_atu(void __iomem *dbi, u32 viewport, const char *name)
{
	/* Viewport selection changes only the register bank being observed. */
	writel(viewport, dbi + ATU_VIEWPORT);
	readl(dbi + ATU_VIEWPORT);
	pr_info("OMPCIE ATU %s view=%#010x cr1=%#010x cr2=%#010x base=%#010x:%#010x limit=%#010x target=%#010x:%#010x\n",
		name, readl(dbi + ATU_VIEWPORT), readl(dbi + ATU_CR1),
		readl(dbi + ATU_CR2), readl(dbi + ATU_BASE_HI),
		readl(dbi + ATU_BASE_LO), readl(dbi + ATU_LIMIT),
		readl(dbi + ATU_TARGET_HI), readl(dbi + ATU_TARGET_LO));
}

static int __init qtn_topaz_pcie_snapshot_init(void)
{
	void __iomem *dbi;
	void __iomem *sysctl;
	u32 saved;

	dbi = ioremap(TOPAZ_PCIE_DBI_BASE, TOPAZ_PCIE_DBI_SIZE);
	if (!dbi)
		return -ENOMEM;
	sysctl = ioremap(TOPAZ_SYSCTL_BASE, TOPAZ_SYSCTL_SIZE);
	if (!sysctl) {
		iounmap(dbi);
		return -ENOMEM;
	}
	saved = readl(dbi + ATU_VIEWPORT);
	pr_info("OMPCIE sysctl int-mask=%#010x int-status=%#010x intx-mask-bit=%u intx-status-bit=%u\n",
		readl(sysctl + TOPAZ_SYSCTL_PCIE_INT_MASK),
		readl(sysctl + TOPAZ_SYSCTL_PCIE_INT_STATUS),
		!!(readl(sysctl + TOPAZ_SYSCTL_PCIE_INT_MASK) & BIT(11)),
		!!(readl(sysctl + TOPAZ_SYSCTL_PCIE_INT_STATUS) & BIT(11)));
	pr_info("OMPCIE snapshot begin dbi=%#x saved_view=%#010x cmd=%#010x link=%#010x\n",
		TOPAZ_PCIE_DBI_BASE, saved, readl(dbi + 0x4),
		readl(dbi + 0x80));
	qtn_dump_atu(dbi, 0x80000000, "inbound0");
	qtn_dump_atu(dbi, 0x00000000, "outbound0");
	qtn_dump_atu(dbi, 0x00000001, "outbound1");
	writel(saved, dbi + ATU_VIEWPORT);
	readl(dbi + ATU_VIEWPORT);
	pr_info("OMPCIE snapshot end restored_view=%#010x\n",
		readl(dbi + ATU_VIEWPORT));
	iounmap(sysctl);
	iounmap(dbi);
	return 0;
}

static void __exit qtn_topaz_pcie_snapshot_exit(void)
{
}

module_init(qtn_topaz_pcie_snapshot_init);
module_exit(qtn_topaz_pcie_snapshot_exit);

MODULE_AUTHOR("OpenMitraStar project");
MODULE_DESCRIPTION("One-shot Topaz PCIe iATU snapshot");
MODULE_LICENSE("GPL");
