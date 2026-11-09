/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef F350_UAPI_H
#define F350_UAPI_H
#include <linux/types.h>
#include <linux/ioctl.h>
#define F350_ABI 1u
#define F350_OBSERVE 1u
#define F350_LOAD 2u
#define F350_SAVE 3u
#define F350_INSPECT 4u
struct f350_request {
 __u32 abi,operation,length,flags;
 __s32 status,backend_status,journal_status;
 __u32 id,control;
 __u8 status_register,security_register,common_bp0,exact_part_verified;
 __u32 quarantined,claimed,sequence_lo,sequence_hi,record_length,slot;
 __u32 phase,failure_phase,commit_visible,protection_restored,witnesses_unchanged;
 __u8 payload[4096];
};
#define F350_IOCTL _IOWR('J',0x50,struct f350_request)
#endif
