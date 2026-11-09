#ifndef OPENMITRASTAR_COMPAT_QTN_BR_TYPES_H
#define OPENMITRASTAR_COMPAT_QTN_BR_TYPES_H

/*
 * Linux 5.10 changed struct br_ip from one multicast address (`u`) to
 * source/destination fields.  qdrv's firmware ABI still carries the old
 * layout, so keep it under the legacy name while isolating the kernel type.
 */
#define br_ip openmitrastar_linux_br_ip
#include <linux/if_bridge.h>
#undef br_ip

struct br_ip {
	union {
		__be32 ip4;
#if IS_ENABLED(CONFIG_IPV6)
		struct in6_addr ip6;
#endif
	} u;
	__be16 proto;
};

#endif
