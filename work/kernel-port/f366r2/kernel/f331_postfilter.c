/* SPDX-License-Identifier: GPL-2.0-only
 * Recovered from OEM 43c0..4c06 plus 4c80..4cb0. See PROVENANCE.tsv.
 * Portable decision/state mathematics, never executes a callback or MMIO.
 */
#include "f331_postfilter.h"
#ifdef __KERNEL__
#include <linux/string.h>
#else
#include <string.h>
#endif
static uint32_t distance(uint32_t a,uint32_t b){return a<b?b-a:a-b;}
static int32_t tick(int32_t timer,uint32_t n){return (int32_t)((uint32_t)timer-n);}
int f331_rate_from_muc(uint32_t packets,uint32_t seconds,int32_t *rate)
{
 if(!rate||!seconds)return F331_BAD_ARGUMENT;
 *rate=(int32_t)(packets/seconds);return 0;
}
int f331_rate_observe(struct f331_rate_state*s,int32_t poll,bool valid,int32_t sample,bool *updated)
{
 if(!s||!updated||s->index>=10)return F331_BAD_ARGUMENT;
 *updated=false;
 if(poll%20)return 0;
 if(!valid)return F331_UNKNOWN;
 s->last=sample;s->samples[s->index]=(uint32_t)sample;
 if(sample>s->max)s->max=sample;
 if(++s->index==10)s->index=0;
 *updated=true;return 0;
}
int f331_begin(struct f331_state*s,uint32_t gen,uint32_t channel,uint32_t bandwidth,bool lsr)
{
 if(!s||!gen||!channel||channel>196||(bandwidth!=20&&bandwidth!=40&&bandwidth!=80))return F331_BAD_ARGUMENT;
 memset(s,0,sizeof(*s));s->generation=gen;s->channel=channel;s->bandwidth=bandwidth;
 s->lsr_enabled=lsr;s->short_index=lsr?220:0;s->good=true;s->initialized=true;return 0;
}
int f331_step(struct f331_state*s,const struct f331_config*c,const struct f331_observation*i,struct f331_decision*d)
{
 bool fh,valid_candidate,low_load,match=true,special_bad;
 uint32_t old_short,old_long=0,window=0;
 unsigned a,b,n;
 if(!s||!c||!i||!d)return F331_BAD_ARGUMENT;
 memset(d,0,sizeof(*d));
 if(i->valid!=F331_VALID_ALL)return F331_UNKNOWN;
 if(!s->initialized||!i->generation||i->generation!=s->generation||i->channel!=s->channel||i->bandwidth!=s->bandwidth||c->lsr_enabled!=s->lsr_enabled)return F331_BAD_CONTEXT;
 if(s->short_index>=(c->lsr_enabled?240U:20U)||s->long_index>=240U||i->current_window_count>65535U)return F331_BAD_ARGUMENT;
 /* 43c0..44b6: capture BOTH old entries before the sole write. */
 old_short=s->history[s->short_index];
 if(c->lsr_enabled)old_long=s->history[s->long_index];
 if(c->lsr_enabled){
  s->history[s->long_index]=(uint16_t)i->current_window_count;
  s->long_sum+=i->current_window_count-old_long;
  if(++s->long_index>=240)s->long_index=0;
 }else s->history[s->short_index]=(uint16_t)i->current_window_count;
 s->short_sum+=i->current_window_count-old_short;
 if(++s->short_index>=(c->lsr_enabled?240U:20U))s->short_index=0;
 /* 44b6..454c: FH-shaped candidate is a history escape, not a new detection. */
 fh=s->short_sum<=c->max_fh&&!i->pri[1]&&i->pri[0]>=c->fh_pri_min&&i->pri[0]<=c->fh_pri_max&&i->width>=c->fh_pw_min&&i->width<=c->fh_pw_max;
 valid_candidate=i->candidate&&(s->short_sum<=c->max_pulse||fh);
 d->fh_candidate=fh;
 /* 454c..46d0: unsigned ADD and comparisons match ARC wrap semantics. */
 d->lsr_history_reject=c->lsr_enabled&&i->lsr_detected&&
  (s->long_sum>=i->lsr_pulse_count+c->max_lsr||
   i->lsr_max_pw<i->lsr_min_pw+c->lsr_pw_diff||
   i->lsr_max_count<i->lsr_min_count+c->lsr_count_diff);
 /* 46d0..47f6: total output count, NOT current-window history count. */
 special_bad=i->candidate&&!i->pri[1]&&
  (i->total_count>c->max_fh||
   (i->total_count>c->ssr_max&&!fh)||
   !((i->pri[0]<=c->forbidden_min||i->pri[0]>=c->korea_min)&&
     (i->pri[0]<=c->korea_max||i->pri[0]>=c->forbidden_max)));
 if(special_bad){s->good=false;s->bad_timer=9;goto remember;}
 low_load=s->short_sum<=c->min_detect;
 if(s->good){
  if(low_load||valid_candidate)goto final;
  s->good=false;s->bad_timer=9;s->bad_detection=i->candidate;
  if(i->candidate)goto remember;
  goto final;
 }
 /* 48ea..4a58: match all nonzero old PRIs against all three new slots.
  * This deliberately is not a one-to-one set matcher. Duplicates matter. */
 if(!i->candidate){if(i->current_window_count>=14)s->bad_timer=24;}
 else if(s->bad_detection){
  if(!(fh&&!s->last_pri[1]&&s->last_pri[0]>=c->fh_pri_min&&s->last_pri[0]<=c->fh_pri_max&&s->last_width>=c->fh_pw_min&&s->last_width<=c->fh_pw_max)){
   uint32_t old_count=0,new_count=0,matches=0;
   match=distance(s->last_width,i->width)<=c->pw_neighbor;
   if(match){
    for(a=0;a<3;a++){
     if(s->last_pri[a]){old_count++;for(b=0;b<3;b++)if(distance(s->last_pri[a],i->pri[b])<=c->pri_neighbor)matches++;}
     if(i->pri[a])new_count++;
    }
    match=old_count==new_count&&old_count==matches;
   }
  }
 }
 d->matching_bad_detection=match;
 /* 4a58..4aac: nine/twenty-four are POLL COUNTS, not seconds. */
 if(low_load||valid_candidate){
  if(!i->candidate)s->bad_timer=tick(s->bad_timer,1);
  else if(match)s->bad_timer=tick(s->bad_timer,2);
  else if(s->bad_detection)s->bad_timer=24;
  else s->bad_timer=tick(s->bad_timer,1);
 }else{
  if(!i->candidate)s->bad_timer=9;
  else if(!match)s->bad_timer=24;
  else s->bad_timer=tick(s->bad_timer,1);
 }
 if(s->bad_timer<1){s->good=true;s->bad_detection=false;d->history_reject=i->candidate;goto final;}
 if(i->candidate)goto remember;
 s->bad_detection=false;goto final;
remember:
 s->bad_detection=true;s->last_width=i->width;
 for(n=0;n<3;n++)s->last_pri[n]=i->pri[n];
 d->history_reject=true;
final:
 d->history_applied=i->candidate;
 if(!i->candidate)return 0;
 /* 4b40 unsigned modular sum; 4b7e signed instantaneous comparison. */
 if(c->rate_enabled){
  for(n=0;n<10;n++)window+=i->rate_samples[n];
  d->rate_reject=window>c->max_rate||i->instant_rate>c->max_instant;
 }
 d->suppressed=d->history_reject||d->rate_reject||d->lsr_history_reject;
 d->bypassed=d->suppressed&&c->no_reject;
 if(d->suppressed&&!c->no_reject)s->rejected++;
 else d->callback_condition=i->callback_registered;
 return 0;
}
