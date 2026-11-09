// SPDX-License-Identifier: GPL-2.0-only
#include "f338_pipeline.h"
#ifdef __KERNEL__
#include <linux/string.h>
#include <linux/errno.h>
#else
#include <string.h>
#include <errno.h>
#endif
static uint32_t le32(const uint8_t*b,unsigned n)
{return (uint32_t)b[n]|(uint32_t)b[n+1]<<8|(uint32_t)b[n+2]<<16|(uint32_t)b[n+3]<<24;}
static void configuration(struct f332_pipeline*p,const uint8_t*c)
{
 struct f331_config*d=&p->config;
 d->max_pulse=le32(c,156);d->max_lsr=le32(c,160);d->max_fh=le32(c,164);d->min_detect=le32(c,168);
 d->ssr_max=le32(c,92);d->forbidden_min=le32(c,100);d->forbidden_max=le32(c,96);
 d->korea_min=le32(c,292);d->korea_max=le32(c,296);
 d->fh_pri_min=le32(c,124);d->fh_pri_max=le32(c,128);d->fh_pw_min=le32(c,140);d->fh_pw_max=le32(c,144);
 d->pri_neighbor=le32(c,104);d->pw_neighbor=le32(c,108);d->lsr_pw_diff=le32(c,176);d->lsr_count_diff=le32(c,180);
 d->lsr_enabled=!!c[214];d->rate_enabled=!!c[219];d->max_rate=le32(c,220);d->max_instant=(int32_t)le32(c,224);d->no_reject=false;
}
int f332_pipeline_begin(struct f332_pipeline*p,uint32_t gen,uint32_t chan,uint32_t bw,uint32_t base,uint32_t ticks,int tag,const struct f332_backend*b)
{
 struct f331_rate_state saved;uint32_t poll;bool keep,rate;(void)ticks;
 if(!p||!b||!b->epoch_current||!b->reset_counter||!gen||p->initialized||tag)return -EINVAL;
 keep=!!p->generation;saved=p->rate;poll=p->poll_counter;rate=p->rate_ready;
 memset(p,0,sizeof(*p));p->generation=gen;p->channel=chan;p->bandwidth=bw;p->timestamp_base=base;p->backend=*b;
 if(keep){p->rate=saved;p->poll_counter=poll;p->rate_ready=rate;}
 if(!b->epoch_current(b->context,gen))return -ESTALE;
 p->initialized=true;return 0;
}
int f332_pipeline_end(struct f332_pipeline*p)
{if(!p||!p->initialized)return -EINVAL;p->initialized=false;p->fault=true;return 0;}
int f338_pipeline_make_job(struct f332_pipeline*p,const struct f332_frame*f,struct f338_job*j,struct f332_pipeline_result*r)
{
 bool sampled=false;unsigned n;int rc;
 if(!p||!f||!j||!r)return -EINVAL;
 memset(r,0,sizeof(*r));
 if(!p->initialized||p->fault)return -EIO;
 if(f->generation!=p->generation||f->channel!=p->channel||f->bandwidth!=p->bandwidth||!p->backend.epoch_current(p->backend.context,p->generation))return -ESTALE;
 if(f->raw_count>128||(f->raw_count&&!f->raw)||!f->zc||!f->raw_valid||!f->zc_association_valid||!f->rate_valid)return -ENODATA;
 rc=f331_rate_observe(&p->rate,(int32_t)p->poll_counter,f->rate_valid,f->tx_bytes_per_second,&sampled);if(rc)return -ENODATA;
 p->rate_ready|=sampled;if(!p->rate_ready)return -ENODATA;
 r->rate_sampled=sampled;++p->poll_counter;r->poll_counter=p->poll_counter;r->detector_polled=p->poll_counter%50==0;
 memset(j,0,sizeof(*j));j->h.magic=F338_MAGIC;j->h.abi=F338_ABI;j->h.size=sizeof(*j);j->h.generation=p->generation;
 j->channel=p->channel;j->bandwidth=p->bandwidth;j->scan_channel=f->ocac_scan_channel;
 j->flags=(f->ocac_filter?F338_JOB_OCAC:0)|(f->ocac_weather?F338_JOB_WEATHER:0)|(r->detector_polled?F338_JOB_POLL_DETECTOR:0);
 j->raw_count=f->raw_count;j->legacy_ticks=f->legacy_ticks;j->timestamp_base=p->timestamp_base;j->poll_counter=p->poll_counter;
 j->real_seconds=f->seconds;j->real_microseconds=f->microseconds;j->tx_bytes_per_second=p->rate.last;j->zc_accurate=f->zc->accurate;
 for(n=0;n<f->raw_count;n++){j->raw[n].start=f->raw[n].start;j->raw[n].stop=f->raw[n].stop;j->raw[n].max_power=f->raw[n].max_power;j->raw[n].tagged=f->raw[n].tagged;}
 memcpy(j->zc,f->zc->samples,sizeof(j->zc));return 0;
}
int f338_pipeline_finish(struct f332_pipeline*p,const struct f332_frame*f,const struct f338_reply*wire,struct f332_pipeline_result*r)
{
 struct f331_observation input;unsigned n;int rc;
 if(!p||!f||!wire||!r||!p->initialized||p->fault)return -EIO;
 if(wire->h.generation!=p->generation||!p->backend.epoch_current(p->backend.context,p->generation))return -ESTALE;
 if(wire->status!=F338_WIRE_OK||wire->total_count>256||wire->current_window_count>128||wire->current_window_count>wire->total_count||wire->candidate>1||wire->flushes!=(wire->candidate?2U:0U))return -EPROTO;
 /* Immutable profile except OEM per-poll LSR output byte215. Configuration
  * and detector statistics are explicit service results, never missing0. */
 if(p->config_ready){for(n=0;n<300;n++)if(n!=215&&p->detection.configuration[n]!=wire->configuration[n])return -EPROTO;}
 else{
  if(wire->configuration[214]>1||wire->configuration[215]>1||wire->configuration[219]>1)return -EPROTO;
  configuration(p,wire->configuration);rc=f331_begin(&p->postfilter,p->generation,p->channel,p->bandwidth,p->config.lsr_enabled);if(rc)return -EIO;p->config_ready=true;
 }
 memcpy(p->detection.configuration,wire->configuration,300);memcpy(p->detection.statistics,wire->statistics,700);p->detection.candidate=wire->candidate;
 r->total_count=wire->total_count;r->current_window_count=wire->current_window_count;r->candidate_detected=wire->candidate;r->flushes=wire->flushes;r->reset_sequences_emitted=wire->reset_sequences;r->reset_requests=wire->reset_sequences;
 memset(&input,0,sizeof(input));input.valid=F331_VALID_ALL;input.generation=p->generation;input.channel=p->channel;input.bandwidth=p->bandwidth;
 input.total_count=wire->total_count;input.current_window_count=wire->current_window_count;input.candidate=wire->candidate;input.callback_registered=f->callback_registered;input.lsr_detected=!!wire->configuration[215];
 for(n=0;n<3;n++)input.pri[n]=le32(wire->statistics,684+4*n);
 input.width=le32(wire->statistics,696);input.lsr_pulse_count=le32(wire->statistics,84);input.lsr_max_pw=le32(wire->statistics,92);input.lsr_min_pw=le32(wire->statistics,96);input.lsr_min_count=le32(wire->statistics,100);input.lsr_max_count=le32(wire->statistics,104);
 for(n=0;n<10;n++)input.rate_samples[n]=p->rate.samples[n];
 input.instant_rate=p->rate.last;
 rc=f331_step(&p->postfilter,&p->config,&input,&r->postfilter);if(rc)return -EIO;
 r->postfilter_applied=true;r->callback_condition=r->postfilter.callback_condition;r->callback_authority=false;return 0;
}
