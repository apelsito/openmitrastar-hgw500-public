// SPDX-License-Identifier: GPL-2.0
/*
 * OpenMitraStar fail-closed replacements for optional qdrv FWT acceleration.
 *
 * The OEM FWT module declares itself proprietary.  Linux refuses to let a
 * GPL module that uses GPL-only kernel symbols import from that provider.
 * These module-local definitions keep qdrv control/core loadable without
 * claiming or enabling the unavailable acceleration contract.
 */

#include <linux/dma-mapping.h>
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/types.h>

#include <qtn/topaz_fwt_sw.h>

dma_addr_t ipmac_hash_bus;

static void omqdrv_fwt_unavailable(const char *operation)
{
	pr_info_ratelimited("OMQDRV stage=fwt-compat operation=%s result=disabled\n",
		operation);
}

void fwt_sw_register_node(uint16_t node_num)
{
	omqdrv_fwt_unavailable("register-node");
}

void fwt_sw_unregister_node(uint16_t node_num)
{
	omqdrv_fwt_unavailable("unregister-node");
}

void fwt_sw_reset(void)
{
	omqdrv_fwt_unavailable("reset");
}

void fwt_sw_4addr_callback_set(fwt_sw_4addr_callback_t callback, void *token)
{
	omqdrv_fwt_unavailable("4addr-callback");
}

int fwt_sw_update_uc_ipmac(const uint8_t *mac_be, const uint8_t *ip,
		uint16_t type)
{
	omqdrv_fwt_unavailable("update-ipmac");
	return -EOPNOTSUPP;
}

void fwt_sw_remove_uc_ipmac(const uint8_t *ip, uint16_t type)
{
	omqdrv_fwt_unavailable("remove-ipmac");
}
