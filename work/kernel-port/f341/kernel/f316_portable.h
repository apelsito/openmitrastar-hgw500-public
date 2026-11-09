/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef OPENMITRASTAR_F316_PORTABLE_H
#define OPENMITRASTAR_F316_PORTABLE_H

#ifdef __KERNEL__
#include <linux/types.h>
#include <linux/stddef.h>
typedef u8 uint8_t;
typedef u16 uint16_t;
typedef u32 uint32_t;
typedef s32 int32_t;
typedef u64 uint64_t;
typedef s64 int64_t;
#ifndef UINT32_MAX
#define UINT32_MAX ((uint32_t)~0U)
#endif
#ifndef UINT16_MAX
#define UINT16_MAX ((uint16_t)~0U)
#endif
#ifndef INT32_MAX
#define INT32_MAX ((int32_t)0x7fffffff)
#endif
#ifndef INT32_MIN
#define INT32_MIN (-INT32_MAX - 1)
#endif
#else
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#endif

#endif
