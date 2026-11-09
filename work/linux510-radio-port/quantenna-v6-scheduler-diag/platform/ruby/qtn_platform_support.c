// SPDX-License-Identifier: GPL-2.0
/* Board-owned settings required by qdrv but absent from mainline ARC. */

#include <linux/module.h>
#include <linux/dma-mapping.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/workqueue.h>

#include <asm/hardware.h>

#include <common/ruby_platform.h>
#include <qtn/qdrv_sch.h>
#include <qtn/skb_recycle.h>
#include <qtn/topaz_shared_params.h>

#include <qtn_platform_support.h>

static struct platform_device *qtn_dma_pdev;

struct device *qtn_platform_dma_device(void)
{
	return qtn_dma_pdev ? &qtn_dma_pdev->dev : NULL;
}
EXPORT_SYMBOL(qtn_platform_dma_device);

static int __init qtn_platform_support_init(void)
{
	int ret;

	if (!of_machine_is_compatible("mitrastar,hgw-500bna-qcv2"))
		return 0;
	qtn_dma_pdev = platform_device_alloc("openmitrastar-qtn-dma",
		PLATFORM_DEVID_NONE);
	if (!qtn_dma_pdev)
		return -ENOMEM;
	qtn_dma_pdev->dev.coherent_dma_mask = DMA_BIT_MASK(32);
	qtn_dma_pdev->dev.dma_mask = &qtn_dma_pdev->dev.coherent_dma_mask;
	ret = platform_device_add(qtn_dma_pdev);
	if (ret)
		goto put_device;
	ret = dma_set_mask(&qtn_dma_pdev->dev, DMA_BIT_MASK(32));
	if (ret)
		goto unregister_device;
	ret = dma_set_coherent_mask(&qtn_dma_pdev->dev, DMA_BIT_MASK(32));
	if (ret)
		goto unregister_device;
	pr_info("OMQTNPLAT stage=dma-device-ready name=%s mask=32\n",
		dev_name(&qtn_dma_pdev->dev));
	return 0;

unregister_device:
	platform_device_unregister(qtn_dma_pdev);
	qtn_dma_pdev = NULL;
	return ret;
put_device:
	platform_device_put(qtn_dma_pdev);
	qtn_dma_pdev = NULL;
	return ret;
}

static void __exit qtn_platform_support_exit(void)
{
	if (qtn_dma_pdev) {
		platform_device_unregister(qtn_dma_pdev);
		qtn_dma_pdev = NULL;
	}
}

struct shared_params *soc_shared_params;
EXPORT_SYMBOL(soc_shared_params);

struct qtn_skb_recycle_list __qtn_skb_recycle_list;
EXPORT_SYMBOL(__qtn_skb_recycle_list);

u32 chip_id(void)
{
	return readl((void __iomem *)IO_ADDRESS(RUBY_SYS_CTL_CSR));
}
EXPORT_SYMBOL(chip_id);

int pm_queue_work(struct delayed_work *dwork, unsigned long delay)
{
	return mod_delayed_work(system_wq, dwork, delay);
}
EXPORT_SYMBOL(pm_queue_work);

int pm_flush_work(struct delayed_work *dwork)
{
	return cancel_delayed_work_sync(dwork);
}
EXPORT_SYMBOL(pm_flush_work);

__sram_data uint8_t qdrv_sch_tos2ac[] = {
	QDRV_BAND_AC_BE,
	QDRV_BAND_AC_BK,
	QDRV_BAND_AC_BK,
	QDRV_BAND_AC_BE,
	QDRV_BAND_AC_VI,
	QDRV_BAND_AC_VI,
	QDRV_BAND_AC_VO,
	QDRV_BAND_AC_VO,
};
EXPORT_SYMBOL(qdrv_sch_tos2ac);

__sram_data uint8_t qdrv_sch_dscp2dot1p[] = {
	0, 0, 0, 0, 0, 0, 0, 0,
	1, 1, 1, 1, 1, 1, 1, 1,
	2, 2, 2, 2, 2, 2, 2, 2,
	3, 3, 3, 3, 3, 3, 3, 3,
	4, 4, 4, 4, 4, 4, 4, 4,
	5, 5, 5, 5, 5, 5, 5, 5,
	6, 6, 6, 6, 6, 6, 6, 6,
	7, 7, 7, 7, 7, 7, 7, 7,
};
EXPORT_SYMBOL(qdrv_sch_dscp2dot1p);

__sram_data uint8_t
qdrv_sch_dscp2tid[QTN_MAX_BSS_VAPS][IP_DSCP_MAPPING_SIZE];
EXPORT_SYMBOL(qdrv_sch_dscp2tid);

__sram_data uint16_t qdrv_sch_vlan2index[QTN_MAX_BSS_VAPS] = {
	[0 ... QTN_MAX_BSS_VAPS - 1] = VLANID_INDEX_INITVAL,
};
EXPORT_SYMBOL(qdrv_sch_vlan2index);

__sram_data uint8_t qdrv_vap_vlan_max;
EXPORT_SYMBOL(qdrv_vap_vlan_max);

unsigned int global_auc_config = SHARED_PARAMS_AUC_CONFIG_ASSERT_EN;
module_param_named(auc_config, global_auc_config, uint, 0644);
MODULE_PARM_DESC(auc_config, "Quantenna AuC shared-parameter flags");
EXPORT_SYMBOL(global_auc_config);

module_init(qtn_platform_support_init);
module_exit(qtn_platform_support_exit);

MODULE_DESCRIPTION("OpenMitraStar Quantenna shared platform support");
MODULE_LICENSE("GPL");
