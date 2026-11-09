/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */
/*
 * Copyright (C) 2004, 2007-2010, 2011-2012 Synopsys, Inc. (www.synopsys.com)
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation.
 *
 * vineetg: May 2011
 *  -Support single cycle endian-swap insn in ARC700 4.10
 *
 * vineetg: June 2009
 *  -Better htonl implementation (5 instead of 9 ALU instructions)
 *  -Hardware assisted single cycle bswap (Use Case of ARC custom instrn)
 */

#ifndef __ASM_ARC_SWAB_H
#define __ASM_ARC_SWAB_H

#include <linux/types.h>

/* Compiler target feature: no kernel CONFIG symbol leaks into UAPI. */
#ifdef __Xswape

#define __arch_swab32(x)		\
({					\
	unsigned int tmp = x;		\
	__asm__(			\
	"	swape	%0, %1	\n"	\
	: "=r" (tmp)			\
	: "r" (tmp));			\
	tmp;				\
})

#else

/* Legacy ARC700 software fallback, using only 32-bit shifts and ALU. */
#define __arch_swab32(x)				\
({							\
	__u32 __in = (x), __tmp;			\
	__tmp = (__in << 8) | (__in >> 24);	\
	__in = (__in << 24) | (__in >> 8);	\
	__tmp ^= __in;				\
	__tmp &= 0x00ff00ffU;			\
	__tmp ^ __in;				\
})

#endif /* __Xswape */

#if !defined(__STRICT_ANSI__) || defined(__KERNEL__)
#define __SWAB_64_THRU_32__
#endif

#endif
