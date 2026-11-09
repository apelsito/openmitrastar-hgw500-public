// SPDX-License-Identifier: GPL-2.0-only
#ifndef F338_PIPELINE_H
#define F338_PIPELINE_H
#include "f316_portable.h"
#include "f331_postfilter.h"
#include "f332_detector.h"
#include "f338_uapi.h"
enum f332_backend_status {F332_BACKEND_SEQUENCE_EMITTED=0,F332_BACKEND_CANCELLED=1};
struct f332_backend {void*context;int(*epoch_current)(void*,uint32_t);int(*reset_counter)(void*,uint32_t,uint32_t,int32_t*,int32_t*);};
struct f332_frame {
 uint32_t generation,channel,bandwidth,legacy_ticks;
 const struct f332_pulse*raw;unsigned raw_count;const struct f332_zc*zc;
 int32_t seconds,microseconds,tx_bytes_per_second;
 bool raw_valid,zc_association_valid,rate_valid,callback_registered;
 bool ocac_filter,ocac_weather;uint32_t ocac_scan_channel;
};
struct f332_pipeline_result {
 uint32_t poll_counter,total_count,current_window_count,flushes,reset_requests,reset_sequences_emitted;
 bool candidate_detected,postfilter_applied,callback_condition,callback_authority,detector_polled,rate_sampled,hardware_reset_acknowledged;
 struct f331_decision postfilter;
};
struct f332_pipeline {
 uint32_t generation,channel,bandwidth,poll_counter,timestamp_base;
 bool initialized,fault,rate_ready,config_ready;
 struct f332_backend backend;
 struct f331_config config;struct f331_state postfilter;struct f331_rate_state rate;
 struct f332_detection detection;
};
int f332_pipeline_begin(struct f332_pipeline*,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,int,const struct f332_backend*);
int f332_pipeline_end(struct f332_pipeline*);
int f338_pipeline_make_job(struct f332_pipeline*,const struct f332_frame*,struct f338_job*,struct f332_pipeline_result*);
int f338_pipeline_finish(struct f332_pipeline*,const struct f332_frame*,const struct f338_reply*,struct f332_pipeline_result*);
#endif
