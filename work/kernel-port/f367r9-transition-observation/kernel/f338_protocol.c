// SPDX-License-Identifier: GPL-2.0-only
#include "f338_protocol.h"
#ifdef __KERNEL__
#include <linux/string.h>
#else
#include <string.h>
#endif
static int header(const struct f338_header*h,f338_u32 size)
{return h&&h->magic==F338_MAGIC&&h->abi==F338_ABI&&h->size==size;}
static int same(const struct f338_protocol*s,const struct f338_header*h)
{return h->session==s->session&&h->sequence==s->sequence&&h->generation==s->generation;}
int f338_validate_job(const struct f338_job*j)
{
 unsigned n;
 if(!j||!header(&j->h,sizeof(*j))||!j->h.generation||!j->channel||j->channel>196||
  (j->bandwidth!=20&&j->bandwidth!=40&&j->bandwidth!=80)||j->scan_channel>196||
  (j->flags&~15U)||j->raw_count>F338_RAW_MAX||j->zc_accurate>1||j->real_seconds<0||
  j->real_microseconds<0||j->real_microseconds>=1000000)return F338_PROTO_INVALID;
 for(n=0;n<j->raw_count;n++)if(j->raw[n].tagged>1)return F338_PROTO_INVALID;
 return 0;
}
int f338_protocol_attach(struct f338_protocol*s)
{
 if(!s||s->state!=F338_OFF)return F338_PROTO_BUSY;
 if(s->session==~(f338_u32)0)return F338_PROTO_EXHAUSTED;
 ++s->session;s->sequence=0;s->generation=0;s->reset_count=0;s->reset_pending=0;s->state=F338_IDLE;return 0;
}
void f338_protocol_detach(struct f338_protocol*s,f338_u32 session){if(s&&session==s->session){s->state=F338_OFF;s->reset_pending=0;}}
int f338_protocol_queue(struct f338_protocol*s,struct f338_job*j,f338_u32 now)
{
 if(!s||!j)return F338_PROTO_INVALID;
 if(s->state!=F338_IDLE&&s->state!=F338_REPLY)return F338_PROTO_BUSY;
 if(s->sequence==~(f338_u32)0)return F338_PROTO_EXHAUSTED;
 if(f338_validate_job(j))return F338_PROTO_INVALID;
 j->h.session=s->session;j->h.sequence=++s->sequence;s->generation=j->h.generation;
 s->deadline_ms=now+F338_DEADLINE_MS;s->reset_count=0;s->reset_pending=0;memset(s->resets,0,sizeof(s->resets));s->state=F338_QUEUED;return 0;
}
int f338_protocol_delivered(struct f338_protocol*s,const struct f338_header*h,f338_u32 now)
{
 if(f338_protocol_check_timeout(s,now))return F338_PROTO_TIMEOUT;
 if(!s||!h||s->state!=F338_QUEUED||!same(s,h))return F338_PROTO_STALE;
 s->state=F338_DELIVERED;return 0;
}
int f338_protocol_reply(struct f338_protocol*s,const struct f338_reply*r,f338_u32 now)
{
 if(!s||!r||!header(&r->h,sizeof(*r)))return F338_PROTO_INVALID;
 if(f338_protocol_check_timeout(s,now))return F338_PROTO_TIMEOUT;
 if(s->state!=F338_DELIVERED||!same(s,&r->h)||s->reset_pending)return F338_PROTO_STALE;
 if(r->status>F338_WIRE_CANCELED||r->total_count>256||r->current_window_count>128||r->current_window_count>r->total_count||r->candidate>1||r->flushes>2||r->reset_sequences!=s->reset_count||
  (r->status==F338_WIRE_OK&&r->candidate&&r->flushes!=2))return F338_PROTO_INVALID;
 s->state=F338_REPLY;return 0;
}
int f338_protocol_reset_begin(struct f338_protocol*s,const struct f338_reset*r,struct f338_reset*cached,f338_u32 now)
{
 unsigned n;
 if(!s||!r||!cached||!header(&r->h,sizeof(*r))||!r->request_id)return F338_PROTO_INVALID;
 if(f338_protocol_check_timeout(s,now))return F338_PROTO_TIMEOUT;
 if(s->state!=F338_DELIVERED||!same(s,&r->h))return F338_PROTO_STALE;
 for(n=0;n<s->reset_count;n++)if(s->resets[n].request_id==r->request_id){*cached=s->resets[n];return F338_PROTO_REPLAY;}
 if(s->reset_pending)return F338_PROTO_BUSY;
 if(s->reset_count>=F338_RESET_MAX)return F338_PROTO_INVALID;
 s->reset_pending=r->request_id;return 0;
}
int f338_protocol_reset_end(struct f338_protocol*s,const struct f338_reset*r,f338_u32 now)
{
 if(!s||!r||!header(&r->h,sizeof(*r))||!r->request_id)return F338_PROTO_INVALID;
 if(f338_protocol_check_timeout(s,now))return F338_PROTO_TIMEOUT;
 if(!s||!r||s->state!=F338_DELIVERED||!same(s,&r->h)||s->reset_pending!=r->request_id)return F338_PROTO_STALE;
 if(s->reset_count>=F338_RESET_MAX||r->sequence_emitted!=1||r->actual_seconds<0||r->actual_microseconds<0||r->actual_microseconds>=1000000)return F338_PROTO_INVALID;
 s->resets[s->reset_count++]=*r;s->reset_pending=0;return 0;
}
int f338_protocol_check_timeout(struct f338_protocol*s,f338_u32 now)
{
 if(!s)return F338_PROTO_INVALID;
 if((s->state==F338_QUEUED||s->state==F338_DELIVERED)&&(f338_s32)(now-s->deadline_ms)>=0){s->state=F338_ABORTED;s->reset_pending=0;return F338_PROTO_TIMEOUT;}
 return 0;
}
void f338_protocol_abort(struct f338_protocol*s){if(s&&s->state!=F338_OFF){s->state=F338_ABORTED;s->reset_pending=0;}}
void f338_protocol_cancel(struct f338_protocol*s){if(s&&s->state!=F338_OFF&&s->state!=F338_ABORTED){s->state=F338_IDLE;s->reset_pending=0;s->reset_count=0;}}
