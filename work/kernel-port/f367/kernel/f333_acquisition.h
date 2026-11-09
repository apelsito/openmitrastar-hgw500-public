/* SPDX-License-Identifier: GPL-2.0-only */
/* New portable source; no OEM binary bytes. Caller owns hardware access. */
#ifndef F333_ACQUISITION_H
#define F333_ACQUISITION_H
#ifdef __KERNEL__
#include <linux/types.h>
typedef u32 f333_u32;typedef s32 f333_s32;typedef u8 f333_u8;
#else
#include <stdint.h>
typedef uint32_t f333_u32;typedef int32_t f333_s32;typedef uint8_t f333_u8;
#endif
enum f333_space {F333_BANK_HIGH=0,F333_BANK_LOW=1,F333_ZC_RAM=2};
enum f333_status {F333_OK=0,F333_ZC_NOT_ACCURATE=1,F333_INVALID=-1,F333_READ_FAILED=-2,F333_CAPACITY=-3};
typedef int (*f333_read_word)(void *,enum f333_space,unsigned,f333_u32 *);
struct f333_raw {f333_u32 start,stop,max_power;f333_u8 tagged,pad[3];};
struct f333_snapshot {
    f333_u32 start,current_ptr,zc_start_bytes,win_per_pulse;
    int tag_enabled,ocac_filter,software_zc_accurate;
    const f333_u8 *ocac_mask; /* 256 entries when ocac_filter is true. */
};
struct f333_raw_meta {
    f333_u32 available,captured_count,preprocess_count,words_read;
    int complete;
};
struct f333_zc_meta {
    f333_u32 considered_rows,captured_rows,next_cursor,valid_samples,invalid_samples,words_read;
    int source_accurate,complete;
};
enum f333_consume_kind {F333_CONSUME_WRITE=0,F333_OCAC_COUNT_ZERO=1,
    F333_ZC_ACCURATE_ONE=2,F333_ZC_CURSOR_ZERO=3,F333_OCAC_MASK_CLEAR=4};
struct f333_consume_action {enum f333_consume_kind kind;f333_u32 address,value;};
/* Declarative only. Caller must hold BB owner1 for the complete sequence and
 * publish software state only as part of a verified successful consume. */
unsigned f333_get_consume_plan(const struct f333_consume_action **);
void f333_decode_pair(f333_u32 high,f333_u32 low,int tag_enabled,struct f333_raw *);
int f333_capture_raw(const struct f333_snapshot *,f333_read_word,void *,
                     struct f333_raw *,unsigned,struct f333_raw_meta *);
int f333_capture_zc(const struct f333_snapshot *,f333_read_word,void *,
                    f333_s32 (*)[112],unsigned,struct f333_zc_meta *);
#endif
