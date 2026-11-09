// SPDX-License-Identifier: GPL-2.0
/*
 * Read-only board and bootcfg compatibility for the Linux 5.10 port.
 *
 * The OEM bootcfg driver can modify MTD.  This replacement deliberately
 * exposes only immutable module parameters and never opens an MTD device.
 */

#include <linux/errno.h>
#include <linux/delay.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/netdevice.h>
#include <linux/of.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/types.h>

#include <asm/board/board_config.h>
#include <qtn/bootcfg.h>

#ifdef OPENMITRASTAR_QDRV_V89_PAIR
#include <qtn/mproc_sync.h>
#include <qtn/topaz_fwt_cpuif.h>
#include <ruby_platform.h>
#include <topaz_emac.h>
#endif

#define OPENMITRASTAR_UNSET_INT (-2147483647 - 1)
#define OPENMITRASTAR_BOOTCFG_VALUE_LEN 32

static int board_id = -1;
static int board_emac0 = OPENMITRASTAR_UNSET_INT;
static int board_emac1 = OPENMITRASTAR_UNSET_INT;
static int board_phy0 = 1;
static int board_phy1 = 3;
static unsigned int board_rgmii_timing = 0x81828282U;
static int board_wifi_hw = OPENMITRASTAR_UNSET_INT;
static int board_rfic = OPENMITRASTAR_UNSET_INT;
static bool slow_ethernet;
static int napi_budget = 128;
static unsigned int short_range_scan_count;
static bool allow_dram_sram_fallback;
static bool dram_sram_fallback_active;

#ifdef OPENMITRASTAR_QDRV_V89_PAIR
static int w3_fwt_rxp_quiesce_probe_enable;
module_param(w3_fwt_rxp_quiesce_probe_enable, int, 0400);
MODULE_PARM_DESC(w3_fwt_rxp_quiesce_probe_enable,
	"Explicit MitraStar-only EMAC0 RXP quiesce/FWT arbitration probe");
static int w3_fwt_netss_ioss_pulse_probe_enable;
module_param(w3_fwt_netss_ioss_pulse_probe_enable, int, 0400);
MODULE_PARM_DESC(w3_fwt_netss_ioss_pulse_probe_enable,
	"Explicit MitraStar-only NETSS+IOSS reset-pulse/FWT arbitration probe");
static int w3_fwt_netss_only_probe_enable;
module_param(w3_fwt_netss_only_probe_enable, int, 0400);
MODULE_PARM_DESC(w3_fwt_netss_only_probe_enable,
	"Explicit MitraStar-only NETSS bit7 pulse/FWT arbitration probe");
static int w3_fwt_ioss_only_probe_enable;
module_param(w3_fwt_ioss_only_probe_enable, int, 0400);
MODULE_PARM_DESC(w3_fwt_ioss_only_probe_enable,
	"Explicit MitraStar-only IOSS bit5 pulse/FWT arbitration probe");
#endif

module_param(board_id, int, 0400);
module_param_named(emac0, board_emac0, int, 0400);
module_param_named(emac1, board_emac1, int, 0400);
module_param_named(phy0, board_phy0, int, 0400);
module_param_named(phy1, board_phy1, int, 0400);
module_param_named(rgmii_timing, board_rgmii_timing, uint, 0400);
module_param_named(wifi_hw, board_wifi_hw, int, 0400);
module_param_named(rfic, board_rfic, int, 0400);
module_param(slow_ethernet, bool, 0400);
module_param(napi_budget, int, 0400);
module_param_named(scancnt, short_range_scan_count, uint, 0400);
module_param(allow_dram_sram_fallback, bool, 0400);

MODULE_PARM_DESC(board_id, "OEM Quantenna hardware configuration ID");
MODULE_PARM_DESC(emac0, "OEM BOARD_CFG_EMAC0 value");
MODULE_PARM_DESC(emac1, "OEM BOARD_CFG_EMAC1 value");
MODULE_PARM_DESC(phy0, "OEM BOARD_CFG_PHY0_ADDR value (HGW-500 default: 1)");
MODULE_PARM_DESC(phy1, "OEM BOARD_CFG_PHY1_ADDR value (HGW-500 default: 3)");
MODULE_PARM_DESC(rgmii_timing,
	"OEM BOARD_CFG_RGMII_TIMING value (HGW-500 default: 0x81828282)");
MODULE_PARM_DESC(wifi_hw, "OEM BOARD_CFG_WIFI_HW value");
MODULE_PARM_DESC(rfic, "OEM BOARD_CFG_RFIC value");
MODULE_PARM_DESC(slow_ethernet, "Enable the OEM slow-Ethernet workaround");
MODULE_PARM_DESC(napi_budget, "Read-only NAPI budget (OEM default: 128)");
MODULE_PARM_DESC(scancnt, "Short-range scan count, clamped to 0..255");
MODULE_PARM_DESC(allow_dram_sram_fallback,
		"Laboratory-only DRAM replacement for the missing Topaz SRAM heap");

#define DECLARE_BOOTCFG_INT(_name) \
	static int bootcfg_##_name = OPENMITRASTAR_UNSET_INT; \
	module_param_named(_name, bootcfg_##_name, int, 0400); \
	MODULE_PARM_DESC(_name, "Read-only OEM bootcfg value for " #_name)

DECLARE_BOOTCFG_INT(dev_mode);
DECLARE_BOOTCFG_INT(calstate);
DECLARE_BOOTCFG_INT(power_recheck);
DECLARE_BOOTCFG_INT(post_mask);
DECLARE_BOOTCFG_INT(ext_lna_gain);
DECLARE_BOOTCFG_INT(ext_lna_bypass_gain);
DECLARE_BOOTCFG_INT(tx_power_cal);
DECLARE_BOOTCFG_INT(min_tx_power);
DECLARE_BOOTCFG_INT(max_tx_power);
DECLARE_BOOTCFG_INT(bond_opt);
DECLARE_BOOTCFG_INT(dm_txpower_factor);
DECLARE_BOOTCFG_INT(dm_aci_factor);
DECLARE_BOOTCFG_INT(dm_cci_factor);
DECLARE_BOOTCFG_INT(dm_dfs_factor);
DECLARE_BOOTCFG_INT(dm_beacon_factor);

struct openmitrastar_bootcfg_entry {
	const char *name;
	const int *value;
};

#define BOOTCFG_ENTRY(_name) { #_name, &bootcfg_##_name }

static const struct openmitrastar_bootcfg_entry bootcfg_entries[] = {
	BOOTCFG_ENTRY(dev_mode),
	BOOTCFG_ENTRY(calstate),
	BOOTCFG_ENTRY(power_recheck),
	BOOTCFG_ENTRY(post_mask),
	BOOTCFG_ENTRY(ext_lna_gain),
	BOOTCFG_ENTRY(ext_lna_bypass_gain),
	BOOTCFG_ENTRY(tx_power_cal),
	BOOTCFG_ENTRY(min_tx_power),
	BOOTCFG_ENTRY(max_tx_power),
	BOOTCFG_ENTRY(bond_opt),
	BOOTCFG_ENTRY(dm_txpower_factor),
	BOOTCFG_ENTRY(dm_aci_factor),
	BOOTCFG_ENTRY(dm_cci_factor),
	BOOTCFG_ENTRY(dm_dfs_factor),
	BOOTCFG_ENTRY(dm_beacon_factor),
};

int qtn_get_hw_config_id(void)
{
	return board_id;
}
EXPORT_SYMBOL(qtn_get_hw_config_id);

int soc_id(void)
{
	return 1;
}
EXPORT_SYMBOL(soc_id);

int qtn_get_spi_protect_config(void)
{
	/* No SPI write path exists in this compatibility module. */
	return 0;
}
EXPORT_SYMBOL(qtn_get_spi_protect_config);

int get_board_config(int board_config_param, int *board_config_value)
{
	const int *value;

	if (!board_config_value)
		return -EINVAL;

	/* Keep callers deterministic even when an OEM value was not supplied. */
	*board_config_value = 0;

	switch (board_config_param) {
	case BOARD_CFG_EMAC0:
		value = &board_emac0;
		break;
	case BOARD_CFG_EMAC1:
		value = &board_emac1;
		break;
	case BOARD_CFG_PHY0_ADDR:
		value = &board_phy0;
		break;
	case BOARD_CFG_PHY1_ADDR:
		value = &board_phy1;
		break;
	case BOARD_CFG_RGMII_TIMING:
		*board_config_value = (int)board_rgmii_timing;
		return 0;
	case BOARD_CFG_WIFI_HW:
		value = &board_wifi_hw;
		break;
	case BOARD_CFG_RFIC:
		value = &board_rfic;
		break;
	default:
		return -ENOENT;
	}

	if (*value == OPENMITRASTAR_UNSET_INT)
		return -ENOENT;

	*board_config_value = *value;
	return 0;
}
EXPORT_SYMBOL(get_board_config);

int board_slow_ethernet(void)
{
	return slow_ethernet;
}
EXPORT_SYMBOL(board_slow_ethernet);

int board_napi_budget(void)
{
	return clamp_val(napi_budget, 1, 1024);
}
EXPORT_SYMBOL(board_napi_budget);

int get_all_board_params(char *buffer)
{
	if (!buffer)
		return -EINVAL;

	return scnprintf(buffer, PAGE_SIZE,
			"board_id\t%d\n"
			"emac0\t%d\n"
			"emac1\t%d\n"
			"phy0\t%d\n"
			"phy1\t%d\n"
			"rgmii_timing\t0x%08x\n"
			"wifi_hw\t%d\n"
			"rfic\t%d\n",
			board_id, board_emac0, board_emac1,
			board_phy0, board_phy1, (u32)board_rgmii_timing,
			board_wifi_hw, board_rfic);
}
EXPORT_SYMBOL(get_all_board_params);

char *bootcfg_get_var(const char *variable, char *storage)
{
	size_t i;

	if (!variable || !storage)
		return NULL;

	for (i = 0; i < ARRAY_SIZE(bootcfg_entries); i++) {
		const struct openmitrastar_bootcfg_entry *entry =
			&bootcfg_entries[i];

		if (strcmp(variable, entry->name) != 0)
			continue;
		if (*entry->value == OPENMITRASTAR_UNSET_INT)
			return NULL;

		scnprintf(storage, OPENMITRASTAR_BOOTCFG_VALUE_LEN,
				"=%d", *entry->value);
		return storage;
	}

	return NULL;
}
EXPORT_SYMBOL(bootcfg_get_var);

int bootcfg_create(const char *filename, u32 size)
{
	/* The Linux 5.10 laboratory profile never creates flash-backed state. */
	return -EROFS;
}
EXPORT_SYMBOL(bootcfg_create);

void *heap_sram_alloc(unsigned long size)
{
	void *ptr;

	pr_info("OMSRAM stage=request bytes=%lu requested=%u active=%u\n",
		size, allow_dram_sram_fallback, dram_sram_fallback_active);
	if (!dram_sram_fallback_active) {
		pr_info("OMSRAM stage=denied reason=no-topaz-sram-allocator\n");
		return NULL;
	}

	ptr = kmalloc(size, GFP_KERNEL);
	pr_info("OMSRAM stage=allocated backend=dram-lab bytes=%lu ptr=%px\n",
		size, ptr);
	return ptr;
}
EXPORT_SYMBOL(heap_sram_alloc);

void heap_sram_free(void *ptr)
{
	if (dram_sram_fallback_active) {
		pr_info("OMSRAM stage=free backend=dram-lab ptr=%px\n", ptr);
		kfree(ptr);
	}
}
EXPORT_SYMBOL(heap_sram_free);

#ifndef OPENMITRASTAR_SWITCH_EMAC_PORT
uint32_t qtn_eth_rx_lost_get(struct net_device *dev)
{
	/* No legacy EMAC telemetry is present in the radio-only build. */
	return 0;
}
EXPORT_SYMBOL(qtn_eth_rx_lost_get);
#endif

u_int8_t get_bootcfg_scancnt(void)
{
	return min_t(unsigned int, short_range_scan_count, 255);
}
EXPORT_SYMBOL(get_bootcfg_scancnt);

#ifdef OPENMITRASTAR_QDRV_V89_PAIR
#define OMFWT_RXP_EMAC0_BASE	0xe8000000U
#define OMFWT_RXP_CTRL_ADDR	(OMFWT_RXP_EMAC0_BASE + TOPAZ_EMAC_RXP_CTRL)
#define OMFWT_RXP_EXPECTED	0x00000021U

static int w3_fwt_rxp_quiesce_probe(void)
{
	u32 before;
	u32 quiesced;
	u32 fwt_pre;
	u32 fwt_post;
	u32 fwt_released;
	u32 restored;
	int grant_rc;
	int ret = 0;

	before = qtn_mproc_sync_mem_read(OMFWT_RXP_CTRL_ADDR);
	pr_info("OMFWTRXP stage=snapshot addr=%#x before=%#x expected=%#x expected_match=%u\n",
		OMFWT_RXP_CTRL_ADDR, before, OMFWT_RXP_EXPECTED,
		before == OMFWT_RXP_EXPECTED);

	qtn_mproc_sync_mem_write_wmb(OMFWT_RXP_CTRL_ADDR, 0);
	quiesced = qtn_mproc_sync_mem_read(OMFWT_RXP_CTRL_ADDR);
	pr_info("OMFWTRXP stage=quiesced wrote=0 readback=%#x ok=%u\n",
		quiesced, quiesced == 0);
	if (quiesced != 0) {
		ret = -EIO;
		goto restore;
	}

	fwt_pre = __topaz_fwt_cpu_access_rd();
	grant_rc = __topaz_fwt_cpu_access_start_wait();
	fwt_post = __topaz_fwt_cpu_access_rd();
	pr_info("OMFWTRXP stage=arbitration pre_raw=%#x pre_state=%u pre_req=%u rc=%d post_raw=%#x post_state=%u post_req=%u\n",
		fwt_pre, MS(fwt_pre, TOPAZ_FWT_CPU_ACCESS_STATE),
		!!(fwt_pre & TOPAZ_FWT_CPU_ACCESS_REQ), grant_rc, fwt_post,
		MS(fwt_post, TOPAZ_FWT_CPU_ACCESS_STATE),
		!!(fwt_post & TOPAZ_FWT_CPU_ACCESS_REQ));

	/* Timeout paths also leave REQ asserted; release before restoring EMAC0. */
	__topaz_fwt_cpu_access_stop();
	fwt_released = __topaz_fwt_cpu_access_rd();
	pr_info("OMFWTRXP stage=arbitration-released raw=%#x state=%u req=%u\n",
		fwt_released, MS(fwt_released, TOPAZ_FWT_CPU_ACCESS_STATE),
		!!(fwt_released & TOPAZ_FWT_CPU_ACCESS_REQ));

restore:
	qtn_mproc_sync_mem_write_wmb(OMFWT_RXP_CTRL_ADDR, before);
	restored = qtn_mproc_sync_mem_read(OMFWT_RXP_CTRL_ADDR);
	pr_info("OMFWTRXP stage=restored value=%#x readback=%#x ok=%u\n",
		before, restored, restored == before);
	if (restored != before)
		return -EIO;

	return ret;
}

#define OMFWT_NI_RESET_MASK	(RUBY_SYS_CTL_RESET_NETSS | \
				 RUBY_SYS_CTL_RESET_IOSS)
#define OMFWT_NI_WAIT_MS	50U

static int w3_fwt_netss_ioss_pulse_probe(void)
{
	u32 vec_before;
	u32 mask_before;
	u32 vec_asserted;
	u32 mask_asserted;
	u32 vec_released;
	u32 mask_released;
	u32 fwt_pre;
	u32 fwt_post;
	u32 fwt_released;
	int grant_rc;

	BUILD_BUG_ON(OMFWT_NI_RESET_MASK != 0x000000a0U);
	BUILD_BUG_ON(OMFWT_NI_RESET_MASK & RUBY_SYS_CTL_RESET_ENET0);

	mask_before = qtn_mproc_sync_mem_read(RUBY_SYS_CTL_CPU_VEC_MASK);
	vec_before = qtn_mproc_sync_mem_read(RUBY_SYS_CTL_CPU_VEC);
	pr_info("OMFWTNI stage=snapshot vec=%#x mask=%#x pulse=%#x vec_ready=%u mask_ready=%u\n",
		vec_before, mask_before, OMFWT_NI_RESET_MASK,
		(vec_before & OMFWT_NI_RESET_MASK) == OMFWT_NI_RESET_MASK,
		mask_before == 0);
	if (mask_before != 0 ||
		(vec_before & OMFWT_NI_RESET_MASK) != OMFWT_NI_RESET_MASK) {
		pr_err("OMFWTNI stage=precondition-refused vec=%#x mask=%#x\n",
			vec_before, mask_before);
		return -EBUSY;
	}

	/* Exact OEM pulse for NETSS+IOSS only; ENET0 remains released. */
	qtn_mproc_sync_mem_write_wmb(RUBY_SYS_CTL_CPU_VEC_MASK,
		OMFWT_NI_RESET_MASK);
	qtn_mproc_sync_mem_write_wmb(RUBY_SYS_CTL_CPU_VEC, 0);
	mask_asserted = qtn_mproc_sync_mem_read(RUBY_SYS_CTL_CPU_VEC_MASK);
	vec_asserted = qtn_mproc_sync_mem_read(RUBY_SYS_CTL_CPU_VEC);
	pr_info("OMFWTNI stage=asserted vec=%#x mask=%#x bits_cleared=%u enet0_unchanged=%u\n",
		vec_asserted, mask_asserted,
		(vec_asserted & OMFWT_NI_RESET_MASK) == 0,
		(vec_asserted & RUBY_SYS_CTL_RESET_ENET0) ==
		(vec_before & RUBY_SYS_CTL_RESET_ENET0));

	mdelay(OMFWT_NI_WAIT_MS);
	qtn_mproc_sync_mem_write_wmb(RUBY_SYS_CTL_CPU_VEC,
		OMFWT_NI_RESET_MASK);
	qtn_mproc_sync_mem_write_wmb(RUBY_SYS_CTL_CPU_VEC_MASK, 0);
	vec_released = qtn_mproc_sync_mem_read(RUBY_SYS_CTL_CPU_VEC);
	mask_released = qtn_mproc_sync_mem_read(RUBY_SYS_CTL_CPU_VEC_MASK);
	pr_info("OMFWTNI stage=released vec=%#x mask=%#x vec_restored=%u mask_cleared=%u wait_ms=%u\n",
		vec_released, mask_released, vec_released == vec_before,
		mask_released == mask_before, OMFWT_NI_WAIT_MS);
	if (mask_asserted != OMFWT_NI_RESET_MASK ||
		(vec_asserted & OMFWT_NI_RESET_MASK) != 0 ||
		(vec_asserted & RUBY_SYS_CTL_RESET_ENET0) !=
		(vec_before & RUBY_SYS_CTL_RESET_ENET0) ||
		vec_released != vec_before || mask_released != mask_before) {
		pr_err("OMFWTNI stage=release-unsafe expected_vec=%#x expected_mask=%#x\n",
			vec_before, mask_before);
		return -EIO;
	}

	fwt_pre = __topaz_fwt_cpu_access_rd();
	grant_rc = __topaz_fwt_cpu_access_start_wait();
	fwt_post = __topaz_fwt_cpu_access_rd();
	pr_info("OMFWTNI stage=arbitration pre_raw=%#x pre_state=%u pre_req=%u rc=%d post_raw=%#x post_state=%u post_req=%u\n",
		fwt_pre, MS(fwt_pre, TOPAZ_FWT_CPU_ACCESS_STATE),
		!!(fwt_pre & TOPAZ_FWT_CPU_ACCESS_REQ), grant_rc, fwt_post,
		MS(fwt_post, TOPAZ_FWT_CPU_ACCESS_STATE),
		!!(fwt_post & TOPAZ_FWT_CPU_ACCESS_REQ));
	__topaz_fwt_cpu_access_stop();
	fwt_released = __topaz_fwt_cpu_access_rd();
	pr_info("OMFWTNI stage=arbitration-released raw=%#x state=%u req=%u\n",
		fwt_released, MS(fwt_released, TOPAZ_FWT_CPU_ACCESS_STATE),
		!!(fwt_released & TOPAZ_FWT_CPU_ACCESS_REQ));
	pr_info("OMFWTNI stage=complete rc=%d\n", grant_rc);

	/* A denied grant is the experiment result, not a module-load failure. */
	return 0;
}

#define OMFWT_NETSS_ONLY_MASK	RUBY_SYS_CTL_RESET_NETSS
#define OMFWT_IOSS_ONLY_MASK	RUBY_SYS_CTL_RESET_IOSS
#define OMFWT_SINGLE_WAIT_MS	50U

static int w3_fwt_single_reset_pulse_probe(u32 reset_mask,
					    const char *target)
{
	u32 other_mask;
	u32 vec_before;
	u32 mask_before;
	u32 vec_asserted;
	u32 mask_asserted;
	u32 vec_released;
	u32 mask_released;
	u32 fwt_pre;
	u32 fwt_post;
	u32 fwt_released;
	int grant_rc;

	BUILD_BUG_ON(OMFWT_NETSS_ONLY_MASK != 0x00000080U);
	BUILD_BUG_ON(OMFWT_IOSS_ONLY_MASK != 0x00000020U);
	BUILD_BUG_ON((OMFWT_NETSS_ONLY_MASK | OMFWT_IOSS_ONLY_MASK) &
		RUBY_SYS_CTL_RESET_ENET0);
	if (reset_mask != OMFWT_NETSS_ONLY_MASK &&
		reset_mask != OMFWT_IOSS_ONLY_MASK)
		return -EINVAL;
	other_mask = reset_mask == OMFWT_NETSS_ONLY_MASK ?
		OMFWT_IOSS_ONLY_MASK : OMFWT_NETSS_ONLY_MASK;

	mask_before = qtn_mproc_sync_mem_read(RUBY_SYS_CTL_CPU_VEC_MASK);
	vec_before = qtn_mproc_sync_mem_read(RUBY_SYS_CTL_CPU_VEC);
	pr_info("OMFWT1B target=%s stage=snapshot vec=%#x mask=%#x pulse=%#x selected_ready=%u\n",
		target, vec_before, mask_before, reset_mask,
		(vec_before & reset_mask) == reset_mask);
	if (mask_before != 0 || (vec_before & reset_mask) != reset_mask) {
		pr_err("OMFWT1B target=%s stage=precondition-refused vec=%#x mask=%#x\n",
			target, vec_before, mask_before);
		return -EBUSY;
	}

	qtn_mproc_sync_mem_write_wmb(RUBY_SYS_CTL_CPU_VEC_MASK, reset_mask);
	qtn_mproc_sync_mem_write_wmb(RUBY_SYS_CTL_CPU_VEC, 0);
	mask_asserted = qtn_mproc_sync_mem_read(RUBY_SYS_CTL_CPU_VEC_MASK);
	vec_asserted = qtn_mproc_sync_mem_read(RUBY_SYS_CTL_CPU_VEC);
	pr_info("OMFWT1B target=%s stage=asserted vec=%#x mask=%#x selected_cleared=%u other_unchanged=%u enet0_unchanged=%u\n",
		target, vec_asserted, mask_asserted,
		(vec_asserted & reset_mask) == 0,
		(vec_asserted & other_mask) == (vec_before & other_mask),
		(vec_asserted & RUBY_SYS_CTL_RESET_ENET0) ==
		(vec_before & RUBY_SYS_CTL_RESET_ENET0));

	mdelay(OMFWT_SINGLE_WAIT_MS);
	qtn_mproc_sync_mem_write_wmb(RUBY_SYS_CTL_CPU_VEC, reset_mask);
	qtn_mproc_sync_mem_write_wmb(RUBY_SYS_CTL_CPU_VEC_MASK, 0);
	vec_released = qtn_mproc_sync_mem_read(RUBY_SYS_CTL_CPU_VEC);
	mask_released = qtn_mproc_sync_mem_read(RUBY_SYS_CTL_CPU_VEC_MASK);
	pr_info("OMFWT1B target=%s stage=released vec=%#x mask=%#x vec_restored=%u mask_restored=%u wait_ms=%u\n",
		target, vec_released, mask_released,
		vec_released == vec_before, mask_released == mask_before,
		OMFWT_SINGLE_WAIT_MS);
	if (mask_asserted != reset_mask ||
		(vec_asserted & reset_mask) != 0 ||
		(vec_asserted & other_mask) != (vec_before & other_mask) ||
		(vec_asserted & RUBY_SYS_CTL_RESET_ENET0) !=
		(vec_before & RUBY_SYS_CTL_RESET_ENET0) ||
		vec_released != vec_before || mask_released != mask_before) {
		pr_err("OMFWT1B target=%s stage=release-unsafe expected_vec=%#x expected_mask=%#x\n",
			target, vec_before, mask_before);
		return -EIO;
	}

	fwt_pre = __topaz_fwt_cpu_access_rd();
	grant_rc = __topaz_fwt_cpu_access_start_wait();
	fwt_post = __topaz_fwt_cpu_access_rd();
	pr_info("OMFWT1B target=%s stage=arbitration pre_raw=%#x pre_state=%u pre_req=%u rc=%d post_raw=%#x post_state=%u post_req=%u\n",
		target, fwt_pre, MS(fwt_pre, TOPAZ_FWT_CPU_ACCESS_STATE),
		!!(fwt_pre & TOPAZ_FWT_CPU_ACCESS_REQ), grant_rc, fwt_post,
		MS(fwt_post, TOPAZ_FWT_CPU_ACCESS_STATE),
		!!(fwt_post & TOPAZ_FWT_CPU_ACCESS_REQ));
	__topaz_fwt_cpu_access_stop();
	fwt_released = __topaz_fwt_cpu_access_rd();
	pr_info("OMFWT1B target=%s stage=arbitration-released raw=%#x state=%u req=%u\n",
		target, fwt_released,
		MS(fwt_released, TOPAZ_FWT_CPU_ACCESS_STATE),
		!!(fwt_released & TOPAZ_FWT_CPU_ACCESS_REQ));
	pr_info("OMFWT1B target=%s stage=complete rc=%d\n", target, grant_rc);
	return 0;
}
#endif

static int __init board_compat_init(void)
{
#ifdef OPENMITRASTAR_QDRV_V89_PAIR
	bool target_ok;
	unsigned int probe_count;

	target_ok = of_machine_is_compatible("mitrastar,hgw-500bna-qcv2");
	pr_info("OMSRAM stage=gate-parse requested=%u target_ok=%u profile=v89\n",
		allow_dram_sram_fallback, target_ok);
	if (allow_dram_sram_fallback && !target_ok) {
		pr_err("OMSRAM stage=gate-refused requested=1 reason=target-mismatch\n");
		return -EPERM;
	}
	dram_sram_fallback_active = allow_dram_sram_fallback && target_ok;
	if (dram_sram_fallback_active)
		pr_info("OMSRAM stage=gate-pass backend=dram-lab target=mitrastar,hgw-500bna-qcv2\n");

	probe_count = !!w3_fwt_rxp_quiesce_probe_enable +
		!!w3_fwt_netss_ioss_pulse_probe_enable +
		!!w3_fwt_netss_only_probe_enable +
		!!w3_fwt_ioss_only_probe_enable;
	if (probe_count == 0)
		return 0;
	if (probe_count != 1)
		return -EINVAL;
	pr_info("OMFWTPROBE stage=gate-parse rxp=%d netss_ioss=%d netss=%d ioss=%d target_ok=%u\n",
		w3_fwt_rxp_quiesce_probe_enable,
		w3_fwt_netss_ioss_pulse_probe_enable,
		w3_fwt_netss_only_probe_enable,
		w3_fwt_ioss_only_probe_enable, target_ok);
	if (!target_ok ||
		(w3_fwt_rxp_quiesce_probe_enable != 1 &&
		 w3_fwt_netss_ioss_pulse_probe_enable != 1 &&
		 w3_fwt_netss_only_probe_enable != 1 &&
		 w3_fwt_ioss_only_probe_enable != 1)) {
		pr_err("OMFWTPROBE stage=gate-refused rxp=%d netss_ioss=%d netss=%d ioss=%d target_ok=%u\n",
			w3_fwt_rxp_quiesce_probe_enable,
			w3_fwt_netss_ioss_pulse_probe_enable,
			w3_fwt_netss_only_probe_enable,
			w3_fwt_ioss_only_probe_enable, target_ok);
		return -EPERM;
	}
	pr_info("OMFWTPROBE stage=gate-pass target=mitrastar,hgw-500bna-qcv2\n");
	if (w3_fwt_rxp_quiesce_probe_enable == 1) {
		pr_info("OMFWTRXP stage=gate-pass target=mitrastar,hgw-500bna-qcv2\n");
		return w3_fwt_rxp_quiesce_probe();
	}
	if (w3_fwt_netss_ioss_pulse_probe_enable == 1) {
		pr_info("OMFWTNI stage=gate-pass target=mitrastar,hgw-500bna-qcv2\n");
		return w3_fwt_netss_ioss_pulse_probe();
	}
	if (w3_fwt_netss_only_probe_enable == 1)
		return w3_fwt_single_reset_pulse_probe(
			OMFWT_NETSS_ONLY_MASK, "netss");
	return w3_fwt_single_reset_pulse_probe(
		OMFWT_IOSS_ONLY_MASK, "ioss");
#else
	if (allow_dram_sram_fallback) {
		pr_err("OMSRAM stage=gate-refused requested=1 reason=profile-mismatch\n");
		return -EPERM;
	}
	return 0;
#endif
}
module_init(board_compat_init);

MODULE_DESCRIPTION("OpenMitraStar read-only Quantenna board compatibility");
MODULE_LICENSE("GPL");
