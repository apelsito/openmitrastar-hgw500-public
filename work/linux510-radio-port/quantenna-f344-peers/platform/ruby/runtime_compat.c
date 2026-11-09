// SPDX-License-Identifier: GPL-2.0
/* Linux 5.10 replacements for Quantenna hooks formerly supplied by 2.6.35. */

#include <linux/ktime.h>
#include <linux/module.h>
#include <linux/netdevice.h>

#include <asm/board/troubleshoot.h>
#include <qtn/qtn_debug.h>
#include <qtn/shared_print_buf.h>

unsigned int g_dbg_log_module = BIT(DBG_LM_QDRV - 1);
EXPORT_SYMBOL(g_dbg_log_module);

unsigned int g_dbg_log_level[DBG_LM_MAX] = {
	[0 ... DBG_LM_MAX - 1] = DBG_LL_WARNING,
};
EXPORT_SYMBOL(g_dbg_log_level);

unsigned int g_dbg_log_func[DBG_LM_MAX] = {
	/* Preserve functional/debug flags but keep per-frame dumps opt-in. */
	[0 ... DBG_LM_MAX - 1] = DBG_LF_ALL & ~0x0001f800U,
};
EXPORT_SYMBOL(g_dbg_log_func);

static int __init openmitrastar_runtime_compat_init(void)
{
	pr_info("OMQDRVDBG stage=defaults level=%u func_mask=%#x packet_dump_bits=0\n",
		g_dbg_log_level[DBG_LM_QDRV - 1],
		g_dbg_log_func[DBG_LM_QDRV - 1]);
	return 0;
}
module_init(openmitrastar_runtime_compat_init);

dbg_module_table_t dbg_module_name_entry[] = {
	{ DBG_LM_QDRV, "qdrv" },
	{ DBG_LM_QPCIE, "qpcie" },
	{ DBG_LM_QRADAR, "qradar" },
	{ DBG_LM_QBOOTCFG, "qbootcfg" },
	{ DBG_LM_QADM, "qadm" },
	{ DBG_LM_QWLAN, "qwlan" },
	{ DBG_LM_QMACFW, "qmacfw" },
};
EXPORT_SYMBOL(dbg_module_name_entry);

void (*uc_print_auc_cb)(struct shared_print_consumer *shared_buf);
EXPORT_SYMBOL(uc_print_auc_cb);

static void (*qtn_show_info_callback)(void);

void qtn_show_info_register(void *callback)
{
	WRITE_ONCE(qtn_show_info_callback, callback);
}
EXPORT_SYMBOL(qtn_show_info_register);

void qtn_show_info_unregister(void)
{
	WRITE_ONCE(qtn_show_info_callback, NULL);
}
EXPORT_SYMBOL(qtn_show_info_unregister);

void ruby_cpumon_get_cycles(uint64_t *sleep, uint64_t *awake)
{
	if (sleep)
		*sleep = 0;
	if (awake)
		*awake = ktime_get_mono_fast_ns();
}
EXPORT_SYMBOL(ruby_cpumon_get_cycles);

#ifndef OPENMITRASTAR_SWITCH_EMAC_PORT
void topaz_emac_to_lhost(uint32_t enable)
{
	/* The radio-only profile has no legacy Topaz EMAC instance. */
}
EXPORT_SYMBOL(topaz_emac_to_lhost);

int topaz_emac_get_bonding(void)
{
	return 0;
}
EXPORT_SYMBOL(topaz_emac_get_bonding);
#endif

void arc_set_sram_safe_area(unsigned long start, unsigned long end)
{
}
EXPORT_SYMBOL(arc_set_sram_safe_area);

void arc_save_to_sram_safe_area(int compress_ratio)
{
}
EXPORT_SYMBOL(arc_save_to_sram_safe_area);

void arc_set_troubleshoot_start_hook(
		arc_troubleshoot_start_hook_cbk callback, void *context)
{
}
EXPORT_SYMBOL(arc_set_troubleshoot_start_hook);

MODULE_DESCRIPTION("OpenMitraStar Quantenna Linux 5.10 runtime compatibility");
MODULE_LICENSE("GPL");
