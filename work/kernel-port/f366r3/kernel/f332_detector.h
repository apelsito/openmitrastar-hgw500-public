/* Facade ABI for exact OEM classifier bytes; no callback or hardware action. */
#ifndef F332_DETECTOR_H
#define F332_DETECTOR_H
#ifdef __KERNEL__
#include <linux/types.h>
typedef u32 uint32_t;
typedef s32 int32_t;
typedef u8 uint8_t;
#else
#include <stdint.h>
#endif
struct f332_pulse {uint32_t start,stop,max_power;uint8_t tagged,reserved[3];};
struct f332_zc {int32_t samples[49][112];uint8_t accurate,reserved[3];};
struct f332_detection {
 uint32_t generation,channel,bandwidth,fault;
 uint8_t candidate,configuration[300],statistics[700];
};
int f332_detect_begin(uint32_t generation,uint32_t channel,uint32_t bandwidth,uint32_t legacy_ticks);
int f332_detect_step(uint32_t generation,const struct f332_pulse *processed,unsigned total,unsigned current_count,
 const int32_t *zc_indices,const struct f332_zc *zc,int poll_due,uint32_t legacy_ticks,struct f332_detection *result);
int f332_detect_reset(uint32_t generation);
int f332_detect_snapshot(uint32_t generation,struct f332_detection *result);
int f332_detect_end(uint32_t generation);
int f332_detect_environment(uint32_t generation,unsigned ocac_enabled,uint32_t scan_channel,unsigned weather);
#endif
