// SPDX-License-Identifier: GPL-2.0-only
#ifndef F332_HARDWARE_H
#define F332_HARDWARE_H
#include "f333_acquisition.h"
#include "f332_detector.h"
#include "f332_ocac.h"
struct f332_hw_profile{uint32_t win_size,win_per_pulse,hw_width_min,hw_width_max;bool tag_enabled;};
struct f332_capture {
 struct f333_raw raw[256];
 struct f332_zc zc;
 struct f333_raw_meta raw_meta;
 struct f333_zc_meta zc_meta;
 bool raw_valid,zc_valid;
 bool ocac_filter,ocac_weather;
 uint32_t ocac_scan_channel;
};
int f332_provider_current(uint32_t generation);
int f332_hw_open(uint32_t generation,bool allowed,uint32_t bandwidth,const struct f332_hw_profile*,bool bootstrap,uint32_t *timestamp_base);
int f332_hw_capture(uint32_t generation,struct f332_capture*,const struct f332_ocac_state*);
int f332_hw_reset(void*,uint32_t generation,uint32_t request_id,int32_t *seconds,int32_t *microseconds);
int f332_hw_point(uint32_t *point);
bool f332_hw_ready(void);
bool f332_hw_dirty(void);
bool f332_hw_duty_acquire(uint32_t generation);
void f332_hw_duty_release(void);
void f332_hw_cleanup_unarmed(void);
void f332_hw_retire(void); /* Software IO admission only; no quiesce claim. */
#endif
