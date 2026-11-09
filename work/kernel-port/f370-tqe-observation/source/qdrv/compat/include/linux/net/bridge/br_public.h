#ifndef OPENMITRASTAR_BR_PUBLIC_H
#define OPENMITRASTAR_BR_PUBLIC_H

#include <linux/printk.h>

/*
 * Quantenna's 2.6.35 bridge hooks were private kernel extensions.  Linux
 * 5.10 has no public equivalent; declarations are added here as each caller
 * is moved to a supported bridge/FDB API.  Keep this header intentionally
 * inert so an accidental legacy hook cannot be linked into a test module.
 */

static inline void br_vlan_set_promisc(int enable)
{
	pr_warn_once("qdrv: private bridge VLAN promiscuous hook is unavailable\n");
}

#endif
