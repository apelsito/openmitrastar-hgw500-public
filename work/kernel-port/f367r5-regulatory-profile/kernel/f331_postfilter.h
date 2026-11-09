/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef F331_POSTFILTER_H
#define F331_POSTFILTER_H
#ifdef __KERNEL__
#include <linux/types.h>
typedef u16 uint16_t;
typedef u32 uint32_t;
typedef s32 int32_t;
#else
#include <stdint.h>
#include <stdbool.h>
#endif
#define F331_VALID_COUNTS (1U<<0)
#define F331_VALID_LAST_DETECTION (1U<<1)
#define F331_VALID_LSR_METRICS (1U<<2)
#define F331_VALID_RATE (1U<<3)
#define F331_VALID_CONFIG (1U<<4)
#define F331_VALID_CANDIDATE (1U<<5)
#define F331_VALID_ALL 0x3fU
enum { F331_OK=0, F331_UNKNOWN=-1, F331_BAD_CONTEXT=-2, F331_BAD_ARGUMENT=-3 };
struct f331_config {
 uint32_t max_pulse, max_lsr, max_fh, min_detect;
 uint32_t ssr_max, forbidden_min, forbidden_max, korea_min, korea_max;
 uint32_t fh_pri_min, fh_pri_max, fh_pw_min, fh_pw_max;
 uint32_t pri_neighbor, pw_neighbor, lsr_pw_diff, lsr_count_diff;
 uint32_t max_rate; int32_t max_instant;
 bool lsr_enabled, rate_enabled, no_reject;
};
struct f331_observation {
 uint32_t valid; /* All six inputs explicitly valid; missing is never zero. */
 uint32_t generation, channel, bandwidth;
 uint32_t total_count, current_window_count;
 uint32_t pri[3], width;
 uint32_t lsr_pulse_count, lsr_max_pw, lsr_min_pw, lsr_min_count, lsr_max_count;
 uint32_t rate_samples[10]; int32_t instant_rate;
 bool candidate, lsr_detected, callback_registered;
};
struct f331_state {
 uint16_t history[240], short_index, long_index;
 uint32_t short_sum, long_sum, rejected, last_width, last_pri[3];
 int32_t bad_timer; bool good, bad_detection, initialized, lsr_enabled;
 uint32_t generation, channel, bandwidth;
};
struct f331_decision {
 bool history_reject, history_applied, lsr_history_reject, rate_reject;
 bool suppressed, bypassed, callback_condition;
 bool callback_authority; /* Always false: no function pointer or qdrv call. */
 bool fh_candidate, matching_bad_detection;
};
int f331_begin(struct f331_state*,uint32_t generation,uint32_t channel,uint32_t bandwidth,bool lsr);
int f331_step(struct f331_state*,const struct f331_config*,const struct f331_observation*,struct f331_decision*);
struct f331_rate_state {
 uint32_t samples[10]; uint16_t index; int32_t last,max;
};
/* Poll counter is the OEM signed 32-bit .bss+0xc; reset is not implicit.
 * Sample is an externally synchronized qdrv tx_pkts value in packets/second.
 */
int f331_rate_observe(struct f331_rate_state*,int32_t poll_counter,bool sample_valid,int32_t tx_packets_per_second,bool *updated);
int f331_rate_from_muc(uint32_t sample_packets,uint32_t sample_seconds,int32_t *rate);
#endif
