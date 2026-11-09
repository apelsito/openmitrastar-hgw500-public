// SPDX-License-Identifier: GPL-2.0
/* Optional client-list query replacement while OpenMitraStar FWT is isolated. */

#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/types.h>

int fwt_db_get_macs_behind_node(const uint8_t index, uint32_t *num_entries,
		uint32_t max_req, uint32_t *flags, uint8_t *buf)
{
	if (num_entries)
		*num_entries = 0;
	if (flags)
		*flags = 0;
	pr_info_ratelimited("OMWLAN stage=fwt-client-list result=unsupported\n");
	return -EOPNOTSUPP;
}
