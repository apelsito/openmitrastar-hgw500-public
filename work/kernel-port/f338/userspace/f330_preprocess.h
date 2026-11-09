/* Exact OEM preprocessor, explicit deferred hardware reset transaction. */
#ifndef F330_PREPROCESS_H
#define F330_PREPROCESS_H
#ifdef __KERNEL__
#include <linux/types.h>
#include <linux/stddef.h>
typedef u32 uint32_t;
typedef s32 int32_t;
typedef u8 uint8_t;
#else
#include <stdint.h>
#include <stddef.h>
#endif
struct f330_raw { uint32_t start,stop,max_power; uint8_t tagged,pad[3]; };
enum f330_status { F330_OK=0,F330_RESET_REQUIRED=1,F330_INVALID=-1,F330_ABI_FAULT=-2,F330_STALE=-3,F330_BUSY=-4 };
struct f330_result {
    uint32_t total_count,current_window_count,history_count_before,history_count_after;
    uint32_t poll_before,poll_after,reset_before,reset_after,timestamp_before,timestamp_after;
    uint32_t read, left, tag, merge, width, power;
    uint32_t request_id,bb_enters,bb_leaves,counter_writes,abi_fault;
    uint8_t committed,reset_requested;
    struct f330_raw pulses[256];
    int32_t zc_source_index[128];
};
int f330_begin(uint32_t generation,uint32_t timestamp_base,int tag_enabled);
int f330_prepare(uint32_t generation,const struct f330_raw *,unsigned,
                 int32_t clock_sec,int32_t clock_usec,struct f330_result *);
/* Trusted backend supplies actual completion timestamp only after its two
 * counter writes under BB ownership have been verified. No backend here. */
int f330_confirm_reset(uint32_t generation,uint32_t request_id,int confirmed,
                      int32_t actual_sec,int32_t actual_usec,
                      struct f330_result *committed_result);
#ifdef F330_TEST
void f330_test_poll_count(uint32_t);
#endif
extern unsigned char f330_oem_bss[];
extern struct f330_raw *f330_oem_history_pointer;
extern volatile uint32_t f330_recorded_counter_writes[2];
#endif
