// SPDX-License-Identifier: GPL-2.0-only
#include "f332_events.h"
static bool same(const struct f332_token*a,const struct f332_token*b)
{return a&&b&&a->epoch==b->epoch&&a->serial==b->serial&&a->channel==b->channel&&a->bandwidth==b->bandwidth;}
int f332_events_transition(struct f332_events*s,uint64_t*epoch)
{
 if(!s||!epoch)return -1;
 if(s->phase!=F332_DRAINING){
  if(s->epoch==~(uint64_t)0){s->phase=F332_FAULT;s->event=false;return -1;}
  ++s->epoch;s->event=false;s->phase=F332_DRAINING;
 }
 *epoch=s->epoch;
 if(s->capture||s->callback)return 1;
 s->phase=F332_MUTATING;return 0;
}
int f332_events_commit(struct f332_events*s,uint64_t epoch,uint32_t channel,uint32_t bw,bool ready,bool dfs,bool authority)
{
 if(!s||!epoch||epoch!=s->epoch||s->phase!=F332_MUTATING||s->capture||s->callback||!channel||channel>196||(bw!=20&&bw!=40&&bw!=80))return -1;
 if(authority&&(!ready||!dfs))return -1;
 s->channel=channel;s->bandwidth=bw;s->ready=ready;s->dfs=dfs;s->authority=authority;s->event=false;s->phase=ready?F332_ACTIVE:F332_OFF;return 0;
}
int f332_events_capture(struct f332_events*s,struct f332_token*t)
{
 if(!s||!t||s->phase!=F332_ACTIVE||!s->ready||s->capture||s->callback||s->event||s->serial==~(uint64_t)0)return -1;
 t->epoch=s->epoch;t->serial=++s->serial;t->channel=s->channel;t->bandwidth=s->bandwidth;s->capture_token=*t;s->capture=true;return 0;
}
int f332_events_complete(struct f332_events*s,const struct f332_token*t,bool eligible,struct f332_token*out)
{
 if(!s||!t||!out||!s->capture||!same(t,&s->capture_token))return -1;
 s->capture=false;
 if(t->epoch!=s->epoch||s->phase!=F332_ACTIVE)return -1;
 if(!eligible||!s->authority||!s->dfs||s->delivered_epoch==s->epoch)return 0;
 s->event_token=*t;*out=*t;s->event=true;return 1;
}
int f332_events_dispatch(struct f332_events*s,const struct f332_token*t)
{
 if(!s||!t||s->phase!=F332_ACTIVE||!s->event||s->callback||!same(t,&s->event_token)||t->epoch!=s->epoch||!s->authority||!s->dfs||s->delivered_epoch==s->epoch)return -1;
 s->event=false;s->callback=true;s->delivered_epoch=s->epoch;return 0;
}
int f332_events_return(struct f332_events*s,const struct f332_token*t)
{
 if(!s||!t||!s->callback||!same(t,&s->event_token))return -1;
 s->callback=false;return 0;
}
